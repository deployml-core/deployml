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

import json
import math
from typing import Dict, Optional, Tuple

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


def render_usage_yaml(
    profile: Dict,
    resource_usage: Optional[Dict[str, Dict[str, float]]] = None,
) -> str:
    """
    Render an infracost-usage.yml document.

    Two sections, either of which may be omitted:

    - `resource_type_default_usage` applies one assumption to every resource of a
      type, so all three Cloud Run services get the same request count. That is
      what a coarse light/heavy *estimate* wants.
    - `resource_usage` pins usage to a single terraform address. That is what
      measured usage needs: real numbers differ per service, and a type default
      would charge every service the whole deployment's total.

    Per-address entries win over type defaults, which is why `deployml costs`
    passes an empty profile plus measured `resource_usage`: anything it could not
    measure then stays at infracost's zero default instead of being invented.

    Values are formatted straight into YAML, so only scalars are supported.
    """
    lines = ["version: 0.1"]

    if profile:
        lines.append("resource_type_default_usage:")
        for resource_type, fields in profile.items():
            lines.append(f"  {resource_type}:")
            for key, value in fields.items():
                lines.append(f"    {key}: {value}")

    if resource_usage:
        lines.append("resource_usage:")
        for address, fields in resource_usage.items():
            # Addresses contain dots and brackets, so they need quoting -- and a
            # for_each address embeds its own quotes, e.g.
            #   google_project_service.required["cloudkms.googleapis.com"]
            # which would close the string early and produce invalid YAML.
            # json.dumps emits a correctly escaped double-quoted scalar, which is
            # also valid YAML double-quoted style.
            lines.append(f"  {json.dumps(address)}:")
            for key, value in fields.items():
                lines.append(f"    {key}: {value}")

    return "\n".join(lines) + "\n"


def classify_usage_profile(monthly_requests: float) -> Tuple[str, float]:
    """
    Label measured usage against the light and heavy profiles.

    This is the payoff of measuring. Once we know a student's real request
    volume, light and heavy stop being pricing *inputs* (guesses we bill them
    for) and become pricing *labels* ("you are a light user"). Compared on a log
    scale, because the profiles are 20x apart and the useful question is which
    order of magnitude the student is in, not the arithmetic distance.

    Returns (profile name, ratio of measured usage to that profile).
    """
    light = LIGHT["google_cloud_run_service"]["monthly_requests"]
    heavy = HEAVY["google_cloud_run_service"]["monthly_requests"]
    if monthly_requests <= 0:
        return "light", 0.0
    light_distance = abs(math.log(monthly_requests / light))
    heavy_distance = abs(math.log(monthly_requests / heavy))
    if heavy_distance < light_distance:
        return "heavy", monthly_requests / heavy
    return "light", monthly_requests / light
