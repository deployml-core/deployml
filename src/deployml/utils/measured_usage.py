"""
Measure a deployment's *real* GCP usage and express it in infracost's usage keys.

Why this exists
---------------
`deployml estimate` prices a stack that does not exist yet, so it has to *assume*
how much a student will use it (the light/heavy profiles in `usage_profiles.py`).
Once the stack is deployed we can do better: Cloud Monitoring already records how
many requests each Cloud Run service served, how many bytes sit in GCS, and how
many bytes BigQuery scanned. This module reads those counters and converts them
into the exact keys infracost expects, so `deployml costs` prices the student's
actual behaviour instead of a guess.

There is deliberately no billing integration here. GCP has no API that returns
"my spend so far" -- that needs a BigQuery billing export, which requires
billing-account admin and has a ~24h lag, so it is out of reach for most
students. Measuring usage and pricing it through infracost needs nothing beyond
`roles/monitoring.viewer`.

How usage maps onto infracost keys
----------------------------------
| infracost key                              | Monitoring metric                              |
|--------------------------------------------|------------------------------------------------|
| `monthly_requests`            (Cloud Run)  | `run.googleapis.com/request_count`             |
| `average_request_duration_ms` (Cloud Run)  | `run.googleapis.com/request_latencies` (p50)   |
| `storage_gb`                  (GCS)        | `storage.googleapis.com/storage/total_bytes`   |
| `monthly_class_a_operations`  (GCS)        | `storage.googleapis.com/api/request_count`     |
| `monthly_class_b_operations`  (GCS)        | `storage.googleapis.com/api/request_count`     |
| `monthly_data_retrieval_gb`   (GCS)        | `storage.googleapis.com/network/sent_bytes_count` |
| `monthly_queries_tb`          (BQ dataset) | `bigquery.googleapis.com/query/scanned_bytes`  |
| `monthly_active_storage_gb`   (BQ table)   | `bigquery.googleapis.com/storage/stored_bytes` |
| `monthly_streaming_inserts_mb`(BQ table)   | `bigquery.googleapis.com/storage/uploaded_bytes` |
| (display only) Cloud SQL uptime            | `cloudsql.googleapis.com/database/up`          |

Three honest approximations, each surfaced to the user in `MeasuredUsage.notes`:

1. **Class A vs B operations.** GCS reports operations by method name, not by
   billing class, so we bucket mutating methods and List as class A and Get as
   class B. That matches Google's pricing table for the methods this stack
   actually calls, but it is a mapping we maintain, not a number GCP reports.
2. **BigQuery attribution.** Scanned and stored bytes arrive project-scoped, not
   per-table, so we split them evenly across the deployment's BigQuery
   addresses. BigQuery storage and query pricing are both linear in bytes, so
   the *total* cost is exact -- only the per-row split is approximate.
3. **Flow vs stock.** Counters (requests, bytes scanned) are summed over the
   window and scaled to 30 days. Levels (bytes stored) are averaged over the
   window and used as-is, because a monthly average level is already what
   infracost's `storage_gb` means. Cloud SQL uptime is the mean of a 0/1 gauge,
   which is the fraction of the window the instance was running.

Design rule: never invent a number. Anything Monitoring does not return is left
absent, so infracost prices it at zero, and the reason lands in `notes` for the
display to print. A silent $0 is the bug `deployml costs` exists to fix; an
explained $0 is fine.
"""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

from deployml.utils.platform_compat import run_tool

MONITORING_ENDPOINT = "https://monitoring.googleapis.com/v3/projects/{project}/timeSeries"

# A month, for scaling a measurement window up to the monthly figures infracost wants.
DAYS_PER_MONTH = 30.0

_BYTES_PER_GB = 1024 ** 3
_BYTES_PER_TB = 1024 ** 4
_BYTES_PER_MB = 1024 ** 2

# GCS reports operations by method name; pricing bills them by class. Methods that
# create, modify, or enumerate objects are class A; plain reads are class B.
# Anything unrecognised is counted as class B, the cheaper of the two, so an
# unknown method can never silently inflate the estimate.
_CLASS_A_METHOD_HINTS = (
    "insert", "create", "update", "patch", "delete", "copy",
    "compose", "rewrite", "list", "setiampolicy", "post",
)

# Cloud Run resource types, for matching a terraform address to a service name.
_CLOUD_RUN_TYPES = ("google_cloud_run_service", "google_cloud_run_v2_service")

# Where each resource type keeps its GCP-side name in `terraform show -json`.
# Falls back to "name" for everything not listed.
_NAME_KEYS = {
    "google_bigquery_table": ("table_id",),
    "google_bigquery_dataset": ("dataset_id",),
    "google_sql_database_instance": ("name",),
}


class MonitoringError(Exception):
    """
    The Monitoring API could not be read at all.

    Carries a `hint` with the command that fixes it, so the CLI can tell the
    student what to do instead of dumping an HTTP status.
    """

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


@dataclass
class DeployedResource:
    """One resource in the deployed terraform state, with its GCP-side name."""
    address: str        # module.cloud_sql_postgres.google_sql_database_instance.postgres
    resource_type: str  # google_sql_database_instance
    name: str           # mlops-postgres


@dataclass
class MeasuredUsage:
    """Real usage over a window, keyed the way infracost wants it."""
    window_days: float
    # terraform address -> infracost usage keys. Fed straight into the usage file.
    resource_usage: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # terraform address -> human annotation ("1.2M requests, 240 ms median")
    details: Dict[str, str] = field(default_factory=dict)
    # terraform address -> fraction of the window the instance was up (0.0-1.0)
    sql_uptime: Dict[str, float] = field(default_factory=dict)
    # Things we could not measure, printed so a $0 is never unexplained.
    notes: List[str] = field(default_factory=list)
    # Headline number used to label the student light/heavy.
    cloud_run_monthly_requests: float = 0.0

    def is_empty(self) -> bool:
        """True when Monitoring returned nothing usable for any resource."""
        return not self.resource_usage


# --------------------------------------------------------------------------- #
# Reading the deployed terraform state
# --------------------------------------------------------------------------- #

def _walk_module(module: Dict) -> List[Dict]:
    """Flatten a `terraform show -json` module tree into a list of resources."""
    resources = list(module.get("resources") or [])
    for child in module.get("child_modules") or []:
        resources.extend(_walk_module(child))
    return resources


def _gcp_name(resource: Dict) -> str:
    """Pull the GCP-side resource name out of one `terraform show -json` entry."""
    values = resource.get("values") or {}
    for key in _NAME_KEYS.get(resource.get("type", ""), ("name",)):
        name = values.get(key)
        if name:
            return str(name)
    return ""


def build_resource_map(terraform_dir: Path) -> List[DeployedResource]:
    """
    List the deployed google_* resources with both their terraform address and
    their GCP-side name.

    Uses `terraform show -json`, the machine-readable form, rather than parsing
    the human output of `terraform state show` line by line. Monitoring reports
    usage against GCP names while infracost keys usage against terraform
    addresses, so this mapping is what lets measured usage reach the right
    resource.

    Returns [] when the state cannot be read; callers treat that as "nothing
    deployed here" rather than an error.
    """
    try:
        result = run_tool(
            "terraform", ["show", "-json"],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError, ValueError):
        return []

    root = (data.get("values") or {}).get("root_module") or {}
    deployed: List[DeployedResource] = []
    for resource in _walk_module(root):
        # Data sources show up here too (module.x.data.google_project.current).
        # They are lookups, not billable resources, and infracost never costs them.
        if resource.get("mode", "managed") != "managed":
            continue
        resource_type = resource.get("type", "")
        if not resource_type.startswith("google_"):
            continue
        name = _gcp_name(resource)
        if not name:
            continue
        deployed.append(
            DeployedResource(
                address=resource.get("address", ""),
                resource_type=resource_type,
                name=name,
            )
        )
    return deployed


def _addresses_of_type(resources: List[DeployedResource], *types: str) -> List[str]:
    return [r.address for r in resources if r.resource_type in types]


def _address_by_name(
    resources: List[DeployedResource], name: str, *types: str
) -> Optional[str]:
    """Find the terraform address of the resource GCP calls `name`."""
    for r in resources:
        if r.resource_type in types and r.name == name:
            return r.address
    return None


# --------------------------------------------------------------------------- #
# Talking to Cloud Monitoring
# --------------------------------------------------------------------------- #

def access_token() -> str:
    """
    Mint an access token from Application Default Credentials.

    Uses the same `gcloud auth application-default print-access-token` call that
    `helpers.check_gcp_adc()` probes with, so if `deployml doctor` says ADC is
    configured this will succeed.
    """
    try:
        result = run_tool(
            "gcloud", ["auth", "application-default", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
        raise MonitoringError(
            f"Could not run gcloud to get credentials: {e}",
            hint="gcloud auth application-default login",
        )
    if result.returncode != 0 or not result.stdout.strip():
        raise MonitoringError(
            "No Application Default Credentials available.",
            hint="gcloud auth application-default login",
        )
    return result.stdout.strip()


def _point_value(point: Dict) -> float:
    """Read a numeric value out of one Monitoring point, whatever its type."""
    value = point.get("value") or {}
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "int64Value" in value:
        # int64 comes back as a JSON string.
        return float(value["int64Value"])
    if "distributionValue" in value:
        dist = value["distributionValue"] or {}
        return float(dist.get("mean", 0) or 0)
    if "boolValue" in value:
        return 1.0 if value["boolValue"] else 0.0
    return 0.0


def query_timeseries(
    project_id: str,
    token: str,
    metric_type: str,
    start: datetime,
    end: datetime,
    aligner: str,
) -> List[Dict]:
    """
    Fetch one metric's time series over [start, end].

    The alignment period is the whole window, so each series collapses to a
    single point: a total for counters (ALIGN_SUM) or an average for levels
    (ALIGN_MEAN), which for a 0/1 gauge is also the uptime fraction.

    Deliberately no crossSeriesReducer/groupByFields: we want the raw per-series
    breakdown so `resource.labels` still tells us which bucket or service each
    number belongs to, and we aggregate in Python instead. Cloud Run splits
    request_count by response code and GCS splits api/request_count by method,
    so there are several series per resource either way.

    Raises MonitoringError when the API itself is unreachable (bad credentials,
    API disabled, missing IAM). Returns [] when the API works but has no data.
    """
    window_seconds = max(int((end - start).total_seconds()), 60)
    params = {
        "filter": f'metric.type = "{metric_type}"',
        "interval.startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "interval.endTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "aggregation.alignmentPeriod": f"{window_seconds}s",
        "aggregation.perSeriesAligner": aligner,
    }
    url = MONITORING_ENDPOINT.format(project=project_id)
    series: List[Dict] = []
    page_token = None
    # Cap pages so a pathological project can't hang the command.
    for _ in range(10):
        if page_token:
            params["pageToken"] = page_token
        try:
            response = requests.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=60,
            )
        except requests.RequestException as e:
            raise MonitoringError(
                f"Could not reach the Cloud Monitoring API: {e}",
                hint="Check your network connection and retry.",
            )

        if response.status_code in (401, 403):
            raise MonitoringError(
                "Not allowed to read Cloud Monitoring metrics for this project.",
                hint=(
                    "Enable the API and grant yourself the viewer role:\n"
                    f"    gcloud services enable monitoring.googleapis.com --project {project_id}\n"
                    "    then ask your project owner for roles/monitoring.viewer"
                ),
            )
        if response.status_code != 200:
            raise MonitoringError(
                f"Cloud Monitoring returned HTTP {response.status_code}.",
                hint="Retry in a moment; if it persists, check the GCP status page.",
            )

        try:
            payload = response.json()
        except ValueError:
            raise MonitoringError(
                "Cloud Monitoring returned a response we could not parse.",
                hint="Retry in a moment.",
            )

        series.extend(payload.get("timeSeries") or [])
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return series


def _sum_points(entry: Dict) -> float:
    """Total a single series' points (normally just one, given our alignment)."""
    return sum(_point_value(p) for p in entry.get("points") or [])


def _mean_points(entry: Dict) -> float:
    points = entry.get("points") or []
    if not points:
        return 0.0
    return sum(_point_value(p) for p in points) / len(points)


def _by_resource_label(
    series: List[Dict], label: str, reducer=_sum_points
) -> Dict[str, float]:
    """Collapse series into {resource label value: number}, summing duplicates."""
    totals: Dict[str, float] = {}
    for entry in series:
        key = ((entry.get("resource") or {}).get("labels") or {}).get(label)
        if not key:
            continue
        totals[key] = totals.get(key, 0.0) + reducer(entry)
    return totals


# --------------------------------------------------------------------------- #
# Formatting helpers for the display annotations
# --------------------------------------------------------------------------- #

def human_count(value: float) -> str:
    """Compact a request count: 1234567 -> '1.2M'."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:.0f}"


def _scale_to_month(total: float, days: float) -> float:
    """Scale a counter measured over `days` up to a 30-day month."""
    if days <= 0:
        return 0.0
    return total * (DAYS_PER_MONTH / days)


# --------------------------------------------------------------------------- #
# Per-service collectors. Each fills in the infracost keys it can measure and
# appends a note for anything it cannot, then leaves the rest alone.
# --------------------------------------------------------------------------- #

def _collect_cloud_run(fetch, resources: List[DeployedResource],
                       usage: MeasuredUsage, days: float) -> None:
    if not _addresses_of_type(resources, *_CLOUD_RUN_TYPES):
        return

    # request_count is the first call made, so it carries required=True: if the
    # API is unreachable we want one clear error, not a note on every metric.
    per_service = _by_resource_label(
        fetch("run.googleapis.com/request_count", "ALIGN_SUM", required=True),
        "service_name",
    )
    per_service_latency = _by_resource_label(
        fetch("run.googleapis.com/request_latencies", "ALIGN_PERCENTILE_50"),
        "service_name",
        _mean_points,
    )

    if not per_service:
        usage.notes.append(
            "Cloud Run served no requests in this window, so it is priced at $0."
        )
        return

    matched = False
    for service_name, count in per_service.items():
        address = _address_by_name(resources, service_name, *_CLOUD_RUN_TYPES)
        if address is None:
            # A Cloud Run service in this project that this stack did not deploy.
            continue
        matched = True
        monthly = _scale_to_month(count, days)
        entry: Dict[str, float] = {"monthly_requests": round(monthly, 2)}
        detail = f"{human_count(monthly)} req/mo"

        latency = per_service_latency.get(service_name)
        if latency:
            entry["average_request_duration_ms"] = round(latency, 1)
            detail += f", {latency:.0f} ms median"

        usage.resource_usage[address] = entry
        usage.details[address] = detail
        usage.cloud_run_monthly_requests += monthly

    if matched:
        usage.notes.append(
            "Cloud Run concurrency is not exposed as a metric, so requests per "
            "instance uses infracost's default."
        )


def _collect_gcs(fetch, resources: List[DeployedResource],
                 usage: MeasuredUsage, days: float) -> None:
    if not _addresses_of_type(resources, "google_storage_bucket"):
        return

    stored = _by_resource_label(
        fetch("storage.googleapis.com/storage/total_bytes", "ALIGN_MEAN"),
        "bucket_name",
        _mean_points,
    )
    retrieved = _by_resource_label(
        fetch("storage.googleapis.com/network/sent_bytes_count", "ALIGN_SUM"),
        "bucket_name",
    )

    # Operations arrive split by method name, which we map onto billing classes.
    class_a: Dict[str, float] = {}
    class_b: Dict[str, float] = {}
    for entry in fetch("storage.googleapis.com/api/request_count", "ALIGN_SUM"):
        bucket = ((entry.get("resource") or {}).get("labels") or {}).get("bucket_name")
        if not bucket:
            continue
        method = (((entry.get("metric") or {}).get("labels") or {})
                  .get("method", "") or "").lower()
        target = class_a if any(h in method for h in _CLASS_A_METHOD_HINTS) else class_b
        target[bucket] = target.get(bucket, 0.0) + _sum_points(entry)

    buckets = set(stored) | set(retrieved) | set(class_a) | set(class_b)
    if not buckets:
        usage.notes.append(
            "GCS reported no storage or traffic in this window, so it is priced at $0."
        )
        return

    matched_ops = False
    for bucket in buckets:
        address = _address_by_name(resources, bucket, "google_storage_bucket")
        if address is None:
            continue
        entry: Dict[str, float] = {}
        details: List[str] = []

        stored_gb = stored.get(bucket, 0.0) / _BYTES_PER_GB
        if stored_gb > 0:
            entry["storage_gb"] = round(stored_gb, 4)
            details.append(f"{stored_gb:.2f} GB stored")

        retrieved_gb = _scale_to_month(retrieved.get(bucket, 0.0), days) / _BYTES_PER_GB
        if retrieved_gb > 0:
            entry["monthly_data_retrieval_gb"] = round(retrieved_gb, 4)
            details.append(f"{retrieved_gb:.2f} GB/mo read")

        ops_a = _scale_to_month(class_a.get(bucket, 0.0), days)
        ops_b = _scale_to_month(class_b.get(bucket, 0.0), days)
        if ops_a > 0 or ops_b > 0:
            matched_ops = True
            entry["monthly_class_a_operations"] = round(ops_a, 2)
            entry["monthly_class_b_operations"] = round(ops_b, 2)
            details.append(f"{human_count(ops_a + ops_b)} ops/mo")

        if entry:
            usage.resource_usage[address] = entry
            usage.details[address] = " · ".join(details)

    if matched_ops:
        usage.notes.append(
            "GCS class A/B operations are inferred from method names, since GCS "
            "reports methods rather than billing classes."
        )


def _collect_bigquery(fetch, resources: List[DeployedResource],
                      usage: MeasuredUsage, days: float) -> None:
    dataset_addresses = _addresses_of_type(resources, "google_bigquery_dataset")
    table_addresses = _addresses_of_type(resources, "google_bigquery_table")
    if not dataset_addresses and not table_addresses:
        return

    scanned_bytes = sum(
        _sum_points(e)
        for e in fetch("bigquery.googleapis.com/query/scanned_bytes", "ALIGN_SUM")
    )
    stored_bytes = sum(
        _mean_points(e)
        for e in fetch("bigquery.googleapis.com/storage/stored_bytes", "ALIGN_MEAN")
    )
    uploaded_bytes = sum(
        _sum_points(e)
        for e in fetch("bigquery.googleapis.com/storage/uploaded_bytes", "ALIGN_SUM")
    )

    # These metrics are project-scoped, so they are split evenly across the
    # deployment's addresses. BigQuery query and storage pricing are both linear
    # in bytes, so the total cost is exact; only the per-row split is a guess.
    if dataset_addresses and scanned_bytes > 0:
        scanned_tb = _scale_to_month(scanned_bytes, days) / _BYTES_PER_TB
        share = scanned_tb / len(dataset_addresses)
        for address in dataset_addresses:
            usage.resource_usage.setdefault(address, {})["monthly_queries_tb"] = round(share, 6)
            usage.details[address] = f"{scanned_tb:.3f} TB/mo scanned"
    elif dataset_addresses:
        usage.notes.append(
            "BigQuery ran no queries in this window, so query cost is $0."
        )

    if table_addresses:
        stored_gb = stored_bytes / _BYTES_PER_GB
        uploaded_mb = _scale_to_month(uploaded_bytes, days) / _BYTES_PER_MB
        if stored_gb > 0 or uploaded_mb > 0:
            storage_share = stored_gb / len(table_addresses)
            insert_share = uploaded_mb / len(table_addresses)
            for address in table_addresses:
                entry = usage.resource_usage.setdefault(address, {})
                if stored_gb > 0:
                    entry["monthly_active_storage_gb"] = round(storage_share, 6)
                if uploaded_mb > 0:
                    entry["monthly_streaming_inserts_mb"] = round(insert_share, 4)
            details = []
            if stored_gb > 0:
                details.append(f"{stored_gb:.2f} GB stored")
            if uploaded_mb > 0:
                details.append(f"{uploaded_mb:.1f} MB/mo inserted")
            # Annotate the first table; the display collapses identical rows anyway.
            usage.details[table_addresses[0]] = " · ".join(details)
        if uploaded_mb <= 0:
            usage.notes.append(
                "BigQuery streaming inserts were not reported for this window, "
                "so insert cost shows as $0."
            )
        if len(table_addresses) > 1 and stored_gb > 0:
            usage.notes.append(
                f"BigQuery storage is reported per project, so it is split evenly "
                f"across {len(table_addresses)} tables. The total is exact."
            )


def _collect_cloud_sql(fetch, resources: List[DeployedResource],
                       usage: MeasuredUsage) -> None:
    """
    Record how much of the window the database was actually up.

    Cloud SQL is billed for existing, not for being used, so this does not change
    what infracost charges. It changes what we can *tell* the student: the
    always-on line is the whole bill for most deployments, and the only lever is
    not running it.
    """
    if not _addresses_of_type(resources, "google_sql_database_instance"):
        return

    # database/up is GAUGE/INT64, not BOOL, so ALIGN_FRACTION_TRUE is rejected
    # with HTTP 400. The value is 1 while the instance is up and 0 while it is
    # down, so the mean across the window is the uptime fraction.
    uptime = _by_resource_label(
        fetch("cloudsql.googleapis.com/database/up", "ALIGN_MEAN"),
        "database_id",
        _mean_points,
    )
    for database_id, fraction in uptime.items():
        # database_id is "project:instance"
        instance = database_id.split(":")[-1]
        address = _address_by_name(resources, instance, "google_sql_database_instance")
        if address is not None:
            usage.sql_uptime[address] = min(max(fraction, 0.0), 1.0)


def collect_measured_usage(
    project_id: str,
    resources: List[DeployedResource],
    days: float = 30.0,
) -> MeasuredUsage:
    """
    Measure real usage for the deployed resources over the last `days` days.

    Raises MonitoringError if Cloud Monitoring cannot be read at all, so the CLI
    can print one actionable message. Individual metrics that fail become notes
    and are priced at zero rather than guessed.
    """
    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(days=days)
    token = access_token()
    usage = MeasuredUsage(window_days=float(days))

    def fetch(metric_type: str, aligner: str, required: bool = False) -> List[Dict]:
        try:
            return query_timeseries(project_id, token, metric_type, start, end, aligner)
        except MonitoringError as e:
            if required:
                raise
            usage.notes.append(f"Could not read {metric_type}: {e}")
            return []

    _collect_cloud_run(fetch, resources, usage, days)
    _collect_gcs(fetch, resources, usage, days)
    _collect_bigquery(fetch, resources, usage, days)
    _collect_cloud_sql(fetch, resources, usage)
    return usage
