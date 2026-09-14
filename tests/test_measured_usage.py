"""
Tests for reading real GCP usage out of Cloud Monitoring.

Mocked at two boundaries, matching tests/test_infracost.py: `run_tool` for the
terraform/gcloud shell-outs, and `requests.get` for the Monitoring REST API.
Nothing here touches the network or a real project.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

from deployml.utils.measured_usage import (
    DeployedResource,
    MonitoringError,
    build_resource_map,
    collect_measured_usage,
    human_count,
    query_timeseries,
)
from deployml.utils.usage_profiles import classify_usage_profile

_GB = 1024 ** 3
_TB = 1024 ** 4


# ---------------------------------------------------------------------------
# Canned data helpers
# ---------------------------------------------------------------------------

def _response(payload, status=200):
    return SimpleNamespace(status_code=status, json=lambda: payload)


def _series(resource_labels, value, metric_labels=None):
    """One Monitoring time series collapsed to a single aligned point."""
    return {
        "metric": {"labels": metric_labels or {}},
        "resource": {"labels": resource_labels},
        "points": [{"value": {"doubleValue": float(value)}}],
    }


def _fake_get(by_metric):
    """Serve canned series based on which metric the filter asks for."""
    def _get(url, params=None, headers=None, timeout=None):
        wanted = (params or {}).get("filter", "")
        for metric, series in by_metric.items():
            if metric in wanted:
                return _response({"timeSeries": series})
        return _response({"timeSeries": []})
    return _get


def _resources():
    return [
        DeployedResource("module.experiment_tracking_mlflow.google_cloud_run_service.mlflow",
                         "google_cloud_run_service", "mlflow-server"),
        DeployedResource("module.model_serving_fastapi.google_cloud_run_service.api",
                         "google_cloud_run_service", "fastapi-mlflow-server"),
        DeployedResource("module.artifact_tracking.google_storage_bucket.artifacts",
                         "google_storage_bucket", "mlflow-artifacts-demo"),
        DeployedResource("module.bigquery.google_bigquery_dataset.mlops",
                         "google_bigquery_dataset", "mlops"),
        DeployedResource("module.bigquery.google_bigquery_table.predictions",
                         "google_bigquery_table", "predictions"),
        DeployedResource("module.bigquery.google_bigquery_table.ground_truth",
                         "google_bigquery_table", "ground_truth"),
        DeployedResource("module.cloud_sql_postgres.google_sql_database_instance.pg",
                         "google_sql_database_instance", "mlops-postgres"),
    ]


def _measure(by_metric, days=7.0, resources=None):
    with patch("deployml.utils.measured_usage.access_token", return_value="token"), \
         patch("deployml.utils.measured_usage.requests.get", side_effect=_fake_get(by_metric)):
        return collect_measured_usage("demo-project", resources or _resources(), days)


# ---------------------------------------------------------------------------
# build_resource_map  (terraform address <-> GCP name)
# ---------------------------------------------------------------------------

_SHOW_JSON = {
    "values": {
        "root_module": {
            "resources": [
                {"address": "google_project_service.run", "type": "google_project_service",
                 "values": {"service": "run.googleapis.com"}},
            ],
            "child_modules": [
                {
                    "address": "module.cloud_sql_postgres",
                    "resources": [
                        {"address": "module.cloud_sql_postgres.google_sql_database_instance.pg",
                         "type": "google_sql_database_instance",
                         "values": {"name": "mlops-postgres"}},
                    ],
                    "child_modules": [
                        {
                            "address": "module.bigquery",
                            "resources": [
                                # BigQuery keeps its name under table_id, not name.
                                {"address": "module.bigquery.google_bigquery_table.predictions",
                                 "type": "google_bigquery_table",
                                 "values": {"table_id": "predictions"}},
                            ],
                        }
                    ],
                }
            ],
        }
    }
}


def test_build_resource_map_walks_nested_modules_and_type_specific_names(tmp_path):
    with patch("deployml.utils.measured_usage.run_tool") as mock_run:
        mock_run.return_value = SimpleNamespace(
            returncode=0, stdout=json.dumps(_SHOW_JSON), stderr=""
        )
        result = build_resource_map(tmp_path)
        argv = mock_run.call_args[0][1]

    # Machine-readable form, not the human output of `terraform state show`.
    assert argv == ["show", "-json"]
    by_address = {r.address: r for r in result}
    # Nested child_modules are reached, and google_project_service has no name so it drops.
    assert set(by_address) == {
        "module.cloud_sql_postgres.google_sql_database_instance.pg",
        "module.bigquery.google_bigquery_table.predictions",
    }
    assert by_address["module.bigquery.google_bigquery_table.predictions"].name == "predictions"


def test_build_resource_map_returns_empty_when_state_unreadable(tmp_path):
    with patch("deployml.utils.measured_usage.run_tool") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="no state")
        assert build_resource_map(tmp_path) == []


# ---------------------------------------------------------------------------
# query_timeseries  (request shape + error mapping)
# ---------------------------------------------------------------------------

def test_query_timeseries_sends_window_as_alignment_period():
    from datetime import datetime, timedelta, timezone
    end = datetime(2026, 9, 12, tzinfo=timezone.utc)
    start = end - timedelta(days=7)
    with patch("deployml.utils.measured_usage.requests.get") as mock_get:
        mock_get.return_value = _response({"timeSeries": []})
        query_timeseries("p", "tok", "run.googleapis.com/request_count",
                         start, end, "ALIGN_SUM")
        params = mock_get.call_args.kwargs["params"]
        headers = mock_get.call_args.kwargs["headers"]

    # One aligned point per series, covering the whole window.
    assert params["aggregation.alignmentPeriod"] == f"{7 * 24 * 3600}s"
    assert params["aggregation.perSeriesAligner"] == "ALIGN_SUM"
    assert 'metric.type = "run.googleapis.com/request_count"' == params["filter"]
    # No cross-series reducer: we need resource.labels intact to attribute usage.
    assert "aggregation.crossSeriesReducer" not in params
    assert headers["Authorization"] == "Bearer tok"


def test_query_timeseries_raises_with_a_fix_hint_on_permission_denied():
    from datetime import datetime, timedelta, timezone
    end = datetime(2026, 9, 12, tzinfo=timezone.utc)
    with patch("deployml.utils.measured_usage.requests.get") as mock_get:
        mock_get.return_value = _response({}, status=403)
        try:
            query_timeseries("demo-project", "tok", "run.googleapis.com/request_count",
                             end - timedelta(days=1), end, "ALIGN_SUM")
        except MonitoringError as e:
            assert "monitoring.viewer" in e.hint
            assert "demo-project" in e.hint
        else:
            raise AssertionError("expected MonitoringError")


def test_monitoring_failure_on_the_first_metric_propagates():
    # The first metric acts as the probe: a dead API must surface as one clear
    # error, not as a note attached to every metric.
    with patch("deployml.utils.measured_usage.access_token", return_value="token"), \
         patch("deployml.utils.measured_usage.requests.get") as mock_get:
        mock_get.return_value = _response({}, status=403)
        try:
            collect_measured_usage("demo-project", _resources(), 7.0)
        except MonitoringError:
            pass
        else:
            raise AssertionError("expected MonitoringError")


# ---------------------------------------------------------------------------
# collect_measured_usage  (metric -> infracost key mapping)
# ---------------------------------------------------------------------------

def test_cloud_run_requests_are_scaled_from_the_window_to_a_month():
    usage = _measure({
        "run.googleapis.com/request_count": [
            # Split by response code, as Cloud Run actually reports it.
            _series({"service_name": "mlflow-server"}, 5000, {"response_code_class": "2xx"}),
            _series({"service_name": "mlflow-server"}, 2000, {"response_code_class": "4xx"}),
            _series({"service_name": "fastapi-mlflow-server"}, 700),
            # A service in the project that this stack did not deploy.
            _series({"service_name": "someone-elses-api"}, 999999),
        ],
        "run.googleapis.com/request_latencies": [
            _series({"service_name": "mlflow-server"}, 240),
        ],
    }, days=7.0)

    mlflow = "module.experiment_tracking_mlflow.google_cloud_run_service.mlflow"
    # 7000 requests over 7 days -> 30000 per 30-day month.
    assert usage.resource_usage[mlflow]["monthly_requests"] == 30000.0
    assert usage.resource_usage[mlflow]["average_request_duration_ms"] == 240.0
    assert usage.resource_usage[
        "module.model_serving_fastapi.google_cloud_run_service.api"
    ]["monthly_requests"] == 3000.0
    # Unrelated services must not leak into this deployment's cost.
    assert usage.cloud_run_monthly_requests == 33000.0
    assert "240 ms median" in usage.details[mlflow]


def test_gcs_operations_are_split_into_billing_classes_by_method():
    usage = _measure({
        "run.googleapis.com/request_count": [],
        "storage.googleapis.com/storage/total_bytes": [
            _series({"bucket_name": "mlflow-artifacts-demo"}, 4 * _GB, {"storage_class": "STANDARD"}),
        ],
        "storage.googleapis.com/api/request_count": [
            _series({"bucket_name": "mlflow-artifacts-demo"}, 70, {"method": "storage.objects.insert"}),
            _series({"bucket_name": "mlflow-artifacts-demo"}, 140, {"method": "storage.objects.list"}),
            _series({"bucket_name": "mlflow-artifacts-demo"}, 700, {"method": "storage.objects.get"}),
        ],
    }, days=7.0)

    bucket = "module.artifact_tracking.google_storage_bucket.artifacts"
    entry = usage.resource_usage[bucket]
    assert entry["storage_gb"] == 4.0                      # a level, not scaled
    assert entry["monthly_class_a_operations"] == 900.0     # (70+140) * 30/7
    assert entry["monthly_class_b_operations"] == 3000.0    # 700 * 30/7
    # The approximation is disclosed rather than hidden.
    assert any("class A/B" in note for note in usage.notes)


def test_bigquery_storage_splits_evenly_but_the_total_stays_exact():
    usage = _measure({
        "run.googleapis.com/request_count": [],
        "bigquery.googleapis.com/query/scanned_bytes": [
            _series({"project_id": "demo-project"}, 0.7 * _TB),
        ],
        "bigquery.googleapis.com/storage/stored_bytes": [
            _series({"dataset_id": "mlops"}, 6 * _GB),
        ],
    }, days=7.0)

    tables = [
        "module.bigquery.google_bigquery_table.predictions",
        "module.bigquery.google_bigquery_table.ground_truth",
    ]
    per_table = [usage.resource_usage[t]["monthly_active_storage_gb"] for t in tables]
    assert per_table == [3.0, 3.0]
    # BigQuery prices storage linearly, so an even split gives the exact total.
    assert abs(sum(per_table) - 6.0) < 1e-6
    dataset = "module.bigquery.google_bigquery_dataset.mlops"
    assert abs(usage.resource_usage[dataset]["monthly_queries_tb"] - 3.0) < 1e-3


def test_cloud_sql_uptime_is_recorded_against_its_address():
    usage = _measure({
        "run.googleapis.com/request_count": [],
        "cloudsql.googleapis.com/database/up": [
            _series({"database_id": "demo-project:mlops-postgres"}, 0.5),
        ],
    }, days=7.0)
    assert usage.sql_uptime[
        "module.cloud_sql_postgres.google_sql_database_instance.pg"
    ] == 0.5


def test_cloud_sql_uptime_uses_an_aligner_the_api_accepts():
    # database/up is GAUGE/INT64, not BOOL. ALIGN_FRACTION_TRUE reads like the
    # right choice but the API rejects it with HTTP 400, which degraded the
    # uptime line to a "could not read" note. ALIGN_MEAN over a 0/1 gauge is the
    # same number and is accepted.
    seen = {}

    def _get(url, params=None, headers=None, timeout=None):
        wanted = params["filter"]
        if "database/up" in wanted:
            seen["aligner"] = params["aggregation.perSeriesAligner"]
        return _response({"timeSeries": []})

    with patch("deployml.utils.measured_usage.access_token", return_value="token"), \
         patch("deployml.utils.measured_usage.requests.get", side_effect=_get):
        collect_measured_usage("demo-project", _resources(), 7.0)

    assert seen["aligner"] == "ALIGN_MEAN"


def test_nothing_measured_means_notes_not_invented_numbers():
    usage = _measure({"run.googleapis.com/request_count": []}, days=7.0)
    assert usage.is_empty()
    assert usage.resource_usage == {}
    # Every $0 must come with a reason the display can print.
    assert any("no requests" in note for note in usage.notes)
    assert any("GCS" in note for note in usage.notes)


# ---------------------------------------------------------------------------
# Formatting + profile labelling
# ---------------------------------------------------------------------------

def test_human_count_compacts_large_numbers():
    assert human_count(1_250_000) == "1.2M"
    assert human_count(30_000) == "30.0k"
    assert human_count(42) == "42"


def test_classify_usage_profile_picks_the_nearer_profile_on_a_log_scale():
    assert classify_usage_profile(50_000) == ("light", 1.0)
    assert classify_usage_profile(1_000_000) == ("heavy", 1.0)
    # Crossover is the geometric mean of the two profiles (~224k), not the midpoint.
    assert classify_usage_profile(200_000)[0] == "light"
    assert classify_usage_profile(300_000)[0] == "heavy"
    assert classify_usage_profile(0) == ("light", 0.0)


# ---------------------------------------------------------------------------
# Address contract with infracost
# ---------------------------------------------------------------------------

# The exact addresses infracost reported for the deployml Cloud Run stack, taken
# from a real `infracost scan` of the rendered workspace (it keys each resource by
# its terraform address in the "name" field). Measured usage is pinned to these
# strings via the usage file's `resource_usage` block, so if terraform's address
# and infracost's address ever stop agreeing, the usage file is silently ignored
# and every usage line prices at $0 -- the exact bug measured usage exists to fix.
#
# Note the count indices: `module.experiment_tracking_mlflow[0]` and `mlflow[0]`
# are part of the key. Stripping or normalising them breaks the binding.
_INFRACOST_ADDRESSES = {
    "google_storage_bucket.artifact_tracking_mlflow_artifact",
    "module.bigquery.google_bigquery_dataset.mlops",
    "module.bigquery.google_bigquery_table.drift_metrics",
    "module.bigquery.google_bigquery_table.ground_truth",
    "module.bigquery.google_bigquery_table.offline_features",
    "module.bigquery.google_bigquery_table.predictions",
    "module.cloud_sql_postgres.google_sql_database_instance.postgres",
    "module.experiment_tracking_mlflow[0].google_cloud_run_service.mlflow[0]",
    "module.model_monitoring_grafana[0].google_cloud_run_service.grafana",
    "module.model_serving_fastapi[0].google_cloud_run_service.fastapi",
}

# Shaped like `terraform show -json` output for that same stack: addresses exactly
# as terraform emits them, plus a data source and a free resource that must drop.
_REAL_SHAPE = {
    "values": {
        "root_module": {
            "resources": [
                {"address": "google_storage_bucket.artifact_tracking_mlflow_artifact",
                 "mode": "managed", "type": "google_storage_bucket",
                 "values": {"name": "mlflow-artifacts-deployml-test-dev"}},
            ],
            "child_modules": [
                {"address": "module.bigquery", "resources": [
                    {"address": "module.bigquery.google_bigquery_dataset.mlops",
                     "mode": "managed", "type": "google_bigquery_dataset",
                     "values": {"dataset_id": "mlops"}},
                ] + [
                    {"address": f"module.bigquery.google_bigquery_table.{t}",
                     "mode": "managed", "type": "google_bigquery_table",
                     "values": {"table_id": t}}
                    for t in ("drift_metrics", "ground_truth", "offline_features", "predictions")
                ]},
                {"address": "module.cloud_sql_postgres", "resources": [
                    {"address": "module.cloud_sql_postgres.google_sql_database_instance.postgres",
                     "mode": "managed", "type": "google_sql_database_instance",
                     "values": {"name": "mlflow-postgres-deployml-test-dev"}},
                    # Free resource: enabling an API costs nothing and infracost
                    # marks it is_free, but it still has a name so it lands in the map.
                    {"address": 'module.cloud_sql_postgres.google_project_service.required["cloudkms.googleapis.com"]',
                     "mode": "managed", "type": "google_project_service",
                     "values": {"service": "cloudkms.googleapis.com"}},
                ]},
                {"address": "module.experiment_tracking_mlflow[0]", "resources": [
                    {"address": "module.experiment_tracking_mlflow[0].google_cloud_run_service.mlflow[0]",
                     "mode": "managed", "type": "google_cloud_run_service",
                     "values": {"name": "mlflow-server"}},
                    # Data source, not a billable resource.
                    {"address": "module.experiment_tracking_mlflow[0].data.google_project.current",
                     "mode": "data", "type": "google_project",
                     "values": {"name": "deployml-TEST-DEV"}},
                ]},
                {"address": "module.model_monitoring_grafana[0]", "resources": [
                    {"address": "module.model_monitoring_grafana[0].google_cloud_run_service.grafana",
                     "mode": "managed", "type": "google_cloud_run_service",
                     "values": {"name": "grafana-server"}},
                ]},
                {"address": "module.model_serving_fastapi[0]", "resources": [
                    {"address": "module.model_serving_fastapi[0].google_cloud_run_service.fastapi",
                     "mode": "managed", "type": "google_cloud_run_service",
                     "values": {"name": "fastapi-mlflow-server"}},
                ]},
            ],
        }
    }
}


def test_addresses_match_what_infracost_keys_usage_on(tmp_path):
    with patch("deployml.utils.measured_usage.run_tool") as mock_run:
        mock_run.return_value = SimpleNamespace(
            returncode=0, stdout=json.dumps(_REAL_SHAPE), stderr=""
        )
        addresses = {r.address for r in build_resource_map(tmp_path)}

    # Terraform's addresses are passed through verbatim, count indices included.
    assert _INFRACOST_ADDRESSES <= addresses, (
        "addresses infracost expects are missing: "
        f"{sorted(_INFRACOST_ADDRESSES - addresses)}"
    )
    # The data source dropped; the free API-enablement resource is allowed through
    # because infracost prices it at $0 anyway and it never matches a metric label.
    assert not any(".data." in a for a in addresses)
