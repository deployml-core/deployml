"""Unit tests for src/deployml/utils/infracost.py (v2 rewrite).

Covers:
  1. check_infracost_available  — OS-boundary mock (subprocess)
  2. check_infracost_authenticated — file-system + env var mocks
  3. parse_infracost_scan_data  — pure parsing, no I/O
  4. format_cost_for_confirmation — pure function
"""

import os
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from deployml.utils.infracost import (
    CostAnalysis,
    ResourceCost,
    _classify_category,
    _report_scan_failure,
    _resource_description,
    _row_to_resource_cost,
    display_actual_costs,
    check_infracost_available,
    check_infracost_authenticated,
    display_estimate,
    fetch_resource_costs_detailed,
    format_cost_for_confirmation,
    parse_infracost_scan_data,
)
from deployml.utils.usage_profiles import LIGHT, render_usage_yaml


# ---------------------------------------------------------------------------
# check_infracost_available
# ---------------------------------------------------------------------------

def test_check_infracost_available_returns_true():
    with patch("deployml.utils.infracost.run_tool") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="infracost v2.4.2", stderr="")
        assert check_infracost_available() is True


def test_check_infracost_available_returns_false_when_not_installed():
    with patch("deployml.utils.infracost.run_tool", side_effect=FileNotFoundError):
        assert check_infracost_available() is False


def test_check_infracost_available_returns_false_on_nonzero_returncode():
    with patch("deployml.utils.infracost.run_tool") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="error")
        assert check_infracost_available() is False


# ---------------------------------------------------------------------------
# check_infracost_authenticated
# ---------------------------------------------------------------------------

def test_check_infracost_authenticated_returns_true_with_credentials_file(tmp_path):
    creds_file = tmp_path / ".config" / "infracost" / "credentials.yml"
    creds_file.parent.mkdir(parents=True)
    creds_file.write_text("api_key: test123\n")
    with patch("deployml.utils.infracost.Path.home", return_value=tmp_path):
        # INFRACOST_API_KEY must be absent so we exercise the file-path branch
        env_without_key = {k: v for k, v in os.environ.items() if k != "INFRACOST_API_KEY"}
        with patch.dict(os.environ, env_without_key, clear=True):
            assert check_infracost_authenticated() is True


def test_check_infracost_authenticated_returns_true_with_env_var(tmp_path):
    with patch("deployml.utils.infracost.Path.home", return_value=tmp_path):
        with patch.dict(os.environ, {"INFRACOST_API_KEY": "ic-test-key-abc"}):
            assert check_infracost_authenticated() is True


def test_check_infracost_authenticated_returns_false_when_neither(tmp_path):
    # tmp_path has no credentials.yml and INFRACOST_API_KEY is cleared
    env_without_key = {k: v for k, v in os.environ.items() if k != "INFRACOST_API_KEY"}
    with patch.dict(os.environ, env_without_key, clear=True):
        with patch("deployml.utils.infracost.Path.home", return_value=tmp_path):
            assert check_infracost_authenticated() is False


# ---------------------------------------------------------------------------
# parse_infracost_scan_data  (pure parsing, no subprocess)
# ---------------------------------------------------------------------------

# infracost inspect --json format (fields at top level)
_INSPECT_JSON = {
    "projects": 1,
    "resources": 6,
    "costed_resources": 1,
    "free_resources": 5,
    "monthly_cost": "26.4591683",
    "currency": "USD",
    "project_details": [],
    "failing_policy_list": [],
}

# infracost scan --json format (fields nested under "summary")
_SCAN_JSON = {
    "currency": "USD",
    "summary": {
        "projects": 1,
        "resources": 71,
        "costed_resources": 10,
        "free_resources": 61,
        "total_monthly_cost": "34.55",
    },
    "projects": [],
}


def test_parse_infracost_scan_data_inspect_format_extracts_all_fields():
    result = parse_infracost_scan_data(_INSPECT_JSON)
    assert result is not None
    assert abs(result.total_monthly_cost - 26.4591683) < 0.0001
    assert result.currency == "USD"
    assert result.resources == 6
    assert result.costed_resources == 1
    assert result.free_resources == 5


def test_parse_infracost_scan_data_scan_format_extracts_all_fields():
    # infracost scan --json wraps fields under "summary" with "total_monthly_cost"
    result = parse_infracost_scan_data(_SCAN_JSON)
    assert result is not None
    assert abs(result.total_monthly_cost - 34.55) < 0.001
    assert result.currency == "USD"
    assert result.resources == 71
    assert result.costed_resources == 10
    assert result.free_resources == 61


def test_parse_infracost_scan_data_handles_empty_dict():
    result = parse_infracost_scan_data({})
    assert result is not None
    assert result.total_monthly_cost == 0.0
    assert result.currency == "USD"
    assert result.resources == 0
    assert result.costed_resources == 0
    assert result.free_resources == 0


def test_parse_infracost_scan_data_handles_null_monthly_cost():
    data = {**_INSPECT_JSON, "monthly_cost": None}
    result = parse_infracost_scan_data(data)
    assert result is not None
    assert result.total_monthly_cost == 0.0


def test_parse_infracost_scan_data_handles_invalid_cost_string():
    # float("not-a-number") raises ValueError → function should return None
    data = {**_INSPECT_JSON, "monthly_cost": "not-a-number"}
    result = parse_infracost_scan_data(data)
    assert result is None


def test_parse_infracost_scan_data_handles_zero_cost():
    data = {**_INSPECT_JSON, "monthly_cost": "0", "costed_resources": 0, "free_resources": 6}
    result = parse_infracost_scan_data(data)
    assert result is not None
    assert result.total_monthly_cost == 0.0
    assert result.costed_resources == 0


# ---------------------------------------------------------------------------
# _run_inspect_rows  (argv construction)
# ---------------------------------------------------------------------------

def test_inspect_is_pinned_to_the_scan_file(tmp_path):
    # Guards against regressing to the global-cache form of `infracost inspect`:
    # inspect must be pinned to the scan JSON we pass, via --file. Without it,
    # inspect reads infracost's "most recent scan" and can report a different
    # workspace's costs.
    scan_json = tmp_path / "infracost-scan.json"
    scan_json.write_text("{}")
    with patch("deployml.utils.infracost.run_tool") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="[]", stderr="")
        fetch_resource_costs_detailed(scan_json)
        tool, argv = mock_run.call_args[0][0], mock_run.call_args[0][1]
    # run_tool resolves the tool name to a real path, so the name is passed
    # separately from the args rather than as argv[0].
    assert tool == "infracost"
    assert argv[0] == "inspect"
    assert "--file" in argv
    assert argv[argv.index("--file") + 1] == str(scan_json)


def test_inspect_failure_warns_instead_of_reporting_no_costs(capsys, tmp_path):
    # A failed inspect used to render as "nothing costs money" underneath a
    # non-zero headline total. It must say so instead.
    with patch("deployml.utils.infracost.run_tool") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="boom")
        result = fetch_resource_costs_detailed(tmp_path / "scan.json")
    assert result == []
    assert "per-resource cost breakdown" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# format_cost_for_confirmation  (pure function)
# ---------------------------------------------------------------------------

def test_format_cost_for_confirmation_nonzero_cost():
    result = format_cost_for_confirmation(26.46, "USD")
    assert "$26.46" in result
    assert "USD" in result


def test_format_cost_for_confirmation_zero_cost():
    result = format_cost_for_confirmation(0.0, "USD")
    assert "Variable" in result or "usage-based" in result.lower()


# ---------------------------------------------------------------------------
# usage profiles  (render_usage_yaml)
# ---------------------------------------------------------------------------

def test_render_usage_yaml_is_valid_and_has_profile_keys():
    text = render_usage_yaml(LIGHT)
    data = yaml.safe_load(text)  # must parse as valid YAML
    assert data["version"] == 0.1
    defaults = data["resource_type_default_usage"]
    assert "google_cloud_run_service" in defaults
    assert defaults["google_bigquery_dataset"]["monthly_queries_tb"] == 0.05


# ---------------------------------------------------------------------------
# classification  (_classify_category / _row_to_resource_cost)
# ---------------------------------------------------------------------------

def test_classify_category_fixed_vs_usage():
    assert _classify_category("google_sql_database_instance") == "fixed"
    for usage_type in (
        "google_cloud_run_service",
        "google_bigquery_dataset",
        "google_storage_bucket",
    ):
        assert _classify_category(usage_type) == "usage"


def test_row_to_resource_cost_maps_and_labels():
    row = {
        "cost": "34.55",
        "columns": {"resource": "module.cloud_sql_postgres.google_sql_database_instance.postgres"},
    }
    rc = _row_to_resource_cost(row)
    assert rc.resource_type == "google_sql_database_instance"
    assert rc.category == "fixed"
    assert rc.label == "Cloud SQL"
    assert rc.description == "MLflow's backend database"  # module-specific wins
    assert abs(rc.monthly_cost - 34.55) < 0.001


# ---------------------------------------------------------------------------
# fetch_resource_costs_detailed  (filter zero + sort + classify)
# ---------------------------------------------------------------------------

def test_fetch_resource_costs_detailed_filters_zero_and_sorts(tmp_path):
    rows = [
        {"cost": "0.08", "columns": {"resource": "module.model_serving_fastapi[0].google_cloud_run_service.fastapi"}},
        {"cost": "34.55", "columns": {"resource": "module.cloud_sql_postgres.google_sql_database_instance.pg"}},
        {"cost": "0", "columns": {"resource": "module.bigquery.google_bigquery_table.predictions"}},
    ]
    with patch("deployml.utils.infracost._run_inspect_rows", return_value=rows):
        result = fetch_resource_costs_detailed(tmp_path / "scan.json")
    # zero-cost row dropped, remaining sorted by cost descending
    assert [round(r.monthly_cost, 2) for r in result] == [34.55, 0.08]
    assert result[0].category == "fixed"
    assert result[1].category == "usage"
    assert result[1].description == "FastAPI model server"


# ---------------------------------------------------------------------------
# display_estimate  (lever logic — capture printed output)
# ---------------------------------------------------------------------------

def _rc(addr, rtype, cost, category, label, desc):
    return ResourceCost(addr, rtype, cost, category, label, desc)


def test_display_estimate_fires_lever_when_fixed_dominates(capsys):
    resources = [
        _rc("module.cloud_sql_postgres.google_sql_database_instance.pg",
            "google_sql_database_instance", 34.55, "fixed", "Cloud SQL", "MLflow's backend database"),
        _rc("module.bigquery.google_bigquery_dataset.mlops",
            "google_bigquery_dataset", 0.31, "usage", "BigQuery", "prediction logging & analytics"),
    ]
    analysis = CostAnalysis(34.86, "USD", 71, 10, 61)
    display_estimate(resources, analysis, "light")
    out = capsys.readouterr().out
    assert "ALWAYS-ON" in out and "USAGE-BASED" in out
    assert "Biggest lever" in out
    assert "SQLite" in out


def test_display_estimate_no_lever_when_balanced(capsys):
    resources = [
        _rc("m.google_sql_database_instance.a", "google_sql_database_instance", 10.0, "fixed", "Cloud SQL", "db"),
        _rc("m.google_compute_instance.b", "google_compute_instance", 10.0, "fixed", "Compute Engine VM", "vm"),
        _rc("m.google_storage_bucket.c", "google_storage_bucket", 5.0, "usage", "GCS Bucket", "storage"),
    ]
    analysis = CostAnalysis(25.0, "USD", 30, 3, 27)
    display_estimate(resources, analysis, "light")
    out = capsys.readouterr().out
    assert "Biggest lever" not in out  # top fixed is 40% of total, below the 50% cutoff


# ---------------------------------------------------------------------------
# render_usage_yaml  (per-address measured usage)
# ---------------------------------------------------------------------------

def test_render_usage_yaml_pins_usage_to_terraform_addresses():
    # Measured usage differs per service, so it must key on the address. A type
    # default would charge every Cloud Run service the whole stack's traffic.
    out = render_usage_yaml({}, {
        "module.experiment_tracking_mlflow.google_cloud_run_service.mlflow": {
            "monthly_requests": 30000.0,
        },
        "module.bigquery.google_bigquery_table.predictions[0]": {
            "monthly_active_storage_gb": 1.5,
        },
    })
    data = yaml.safe_load(out)
    assert data["version"] == 0.1
    # An empty profile emits no type defaults, so unmeasured usage stays at zero
    # rather than falling back to a light/heavy guess.
    assert "resource_type_default_usage" not in data
    pinned = data["resource_usage"]
    assert pinned[
        "module.experiment_tracking_mlflow.google_cloud_run_service.mlflow"
    ]["monthly_requests"] == 30000.0
    # Addresses with a count index stay intact through quoting.
    assert "module.bigquery.google_bigquery_table.predictions[0]" in pinned


def test_render_usage_yaml_can_emit_both_sections():
    out = render_usage_yaml(LIGHT, {"module.a.google_storage_bucket.b": {"storage_gb": 2}})
    data = yaml.safe_load(out)
    assert "resource_type_default_usage" in data and "resource_usage" in data


# ---------------------------------------------------------------------------
# _report_scan_failure  (expired-token handling)
# ---------------------------------------------------------------------------

def test_scan_failure_names_the_login_command_for_auth_errors(capsys):
    # check_infracost_authenticated() can only see that a token file exists, so
    # an expired token gets through the pre-flight check and fails here.
    _report_scan_failure("Error: 401 Unauthorized: invalid API key")
    out = capsys.readouterr().out
    assert "infracost auth login" in out


def test_scan_failure_passes_through_non_auth_errors(capsys):
    _report_scan_failure("Error: could not parse main.tf at line 12")
    out = capsys.readouterr().out
    assert "could not parse main.tf" in out
    assert "auth login" not in out


# ---------------------------------------------------------------------------
# _resource_description  (BigQuery queries vs storage)
# ---------------------------------------------------------------------------

def test_bigquery_dataset_and_tables_get_distinct_descriptions():
    # Both live in the `bigquery` module, so a module-level description applied
    # to both and labelled storage rows as query cost.
    dataset = _resource_description(
        "module.bigquery.google_bigquery_dataset.mlops", "google_bigquery_dataset"
    )
    table = _resource_description(
        "module.bigquery.google_bigquery_table.predictions", "google_bigquery_table"
    )
    assert dataset != table
    assert "quer" in dataset
    assert "storage" in table


def test_cloud_run_jobs_are_labelled():
    # Emitted by the teardown / offline_scoring / explainability modules.
    rc = _row_to_resource_cost(
        {"cost": "0.02", "columns": {"resource": "module.teardown.google_cloud_run_v2_job.j"}}
    )
    assert rc.label == "Cloud Run Job"
    assert rc.description == "scheduled batch job"


# ---------------------------------------------------------------------------
# display_actual_costs  (measured view)
# ---------------------------------------------------------------------------

def _measured(**kwargs):
    from deployml.utils.measured_usage import MeasuredUsage
    return MeasuredUsage(**kwargs)


def test_display_actual_costs_shows_measurements_uptime_and_profile_label(capsys):
    sql = "module.cloud_sql_postgres.google_sql_database_instance.pg"
    run = "module.experiment_tracking_mlflow.google_cloud_run_service.mlflow"
    resources = [
        _rc(sql, "google_sql_database_instance", 34.55, "fixed", "Cloud SQL",
            "MLflow's backend database"),
        _rc(run, "google_cloud_run_service", 0.71, "usage", "Cloud Run",
            "MLflow tracking server"),
    ]
    measured = _measured(
        window_days=7.0,
        resource_usage={run: {"monthly_requests": 30000.0}},
        details={run: "30.0k req/mo, 240 ms median"},
        sql_uptime={sql: 0.5},
        notes=["BigQuery streaming inserts were not reported."],
        cloud_run_monthly_requests=30000.0,
    )
    display_actual_costs(
        resources, CostAnalysis(35.26, "USD", 71, 10, 61), measured,
        "gcp-mlops-stack", "light", 0.6, deployed_days=7.0,
    )
    out = capsys.readouterr().out

    assert "ACTUAL COST" in out and "gcp-mlops-stack" in out
    assert "last 7 days" in out
    assert "Run-rate" in out
    # The measured numbers are shown next to the price they produced.
    assert "30.0k req/mo, 240 ms median" in out
    # Cloud SQL bills for existing, so uptime is reported rather than discounted.
    assert "up 50% of window" in out
    assert "$   34.55" in out
    # light/heavy is now a label on real usage, not a pricing input.
    assert "LIGHT user" in out
    assert "Biggest lever" in out and "deployml destroy" in out
    # A $0 is always explained.
    assert "About these numbers" in out and "streaming inserts" in out
    # ~$8.23 = 35.26 * 7/30
    assert "Charged so far" in out


def test_display_actual_costs_omits_profile_label_without_traffic(capsys):
    sql = "module.cloud_sql_postgres.google_sql_database_instance.pg"
    resources = [
        _rc(sql, "google_sql_database_instance", 34.55, "fixed", "Cloud SQL", "db"),
    ]
    measured = _measured(window_days=30.0, notes=["Cloud Run served no requests."])
    display_actual_costs(
        resources, CostAnalysis(34.55, "USD", 71, 10, 61), measured,
        "ws", "light", 0.0,
    )
    out = capsys.readouterr().out
    # Calling someone a "light user" on zero data would be a guess.
    assert "LIGHT user" not in out
    assert "Charged so far" not in out  # no deploy timestamp available
    assert "Cloud Run served no requests." in out


def test_render_usage_yaml_escapes_for_each_addresses():
    # A for_each address embeds its own quotes, e.g.
    #   google_project_service.required["cloudkms.googleapis.com"]
    # Naive f-string quoting closes the YAML string early and the whole usage file
    # becomes unparseable, which infracost would reject or misread.
    addr = 'module.x.google_storage_bucket.buckets["prod"]'
    out = render_usage_yaml({}, {addr: {"storage_gb": 5}})
    data = yaml.safe_load(out)  # must not raise
    assert data["resource_usage"][addr]["storage_gb"] == 5
