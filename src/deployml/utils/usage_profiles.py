"""
Usage profiles for cost estimation.

Infracost prices usage-based resources (Cloud Run, BigQuery, GCS) at *zero usage*
by default, so `deployml estimate` would show $0 for everything except the
always-on Cloud SQL instance. These profiles feed infracost a realistic
assumption of how much a student actually uses the stack, so the estimate
reflects a real monthly bill.

Field names below are the exact keys infracost expects for each resource type
(see infracost's usage-file schema). To tune assumptions, edit the numbers here.
"""

# A typical student demo: clicking around the UIs + running the example serving
# script a few times over a month. Small storage, light query volume.
LIGHT = {
    "google_cloud_run_service": {
        "monthly_requests": 50000,
        "average_request_duration_ms": 300,
        "concurrent_requests_per_instance": 10,
    },
    "google_storage_bucket": {
        "storage_gb": 5,
        "monthly_class_a_operations": 20000,
        "monthly_class_b_operations": 100000,
        "monthly_data_retrieval_gb": 5,
    },
    "google_bigquery_dataset": {
        "monthly_queries_tb": 0.05,  # ~50 GB scanned / month
    },
    "google_bigquery_table": {
        "monthly_active_storage_gb": 1,
        "monthly_streaming_inserts_mb": 200,
    },
}

# A heavier course project / small team: more traffic, more data, more queries.
# Roughly 10-20x light — used to show students a rough ceiling, not a hard limit.
HEAVY = {
    "google_cloud_run_service": {
        "monthly_requests": 1000000,
        "average_request_duration_ms": 400,
        "concurrent_requests_per_instance": 20,
    },
    "google_storage_bucket": {
        "storage_gb": 100,
        "monthly_class_a_operations": 500000,
        "monthly_class_b_operations": 2000000,
        "monthly_data_retrieval_gb": 100,
    },
    "google_bigquery_dataset": {
        "monthly_queries_tb": 1.0,  # ~1 TB scanned / month
    },
    "google_bigquery_table": {
        "monthly_active_storage_gb": 25,
        "monthly_streaming_inserts_mb": 5000,
    },
}

PROFILES = {"light": LIGHT, "heavy": HEAVY}


def get_profile(name: str) -> dict:
    """Return a usage profile by name, defaulting to light for unknown names."""
    return PROFILES.get(name, LIGHT)


def render_usage_yaml(profile: dict) -> str:
    """
    Render a usage profile into an infracost-usage.yml document.

    Uses `resource_type_default_usage`, which applies the same assumptions to
    every resource of a given type (e.g. all three Cloud Run services), which is
    exactly what a coarse light/heavy profile wants.
    """
    lines = ["version: 0.1", "resource_type_default_usage:"]
    for resource_type, fields in profile.items():
        lines.append(f"  {resource_type}:")
        for key, value in fields.items():
            lines.append(f"    {key}: {value}")
    return "\n".join(lines) + "\n"
