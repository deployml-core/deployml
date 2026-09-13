import json
import os
import shutil
import subprocess
import tempfile
import typer
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from dataclasses import dataclass

from deployml.utils.platform_compat import run_tool

if TYPE_CHECKING:  # imported for typing only; avoids a runtime import cycle
    from deployml.utils.measured_usage import MeasuredUsage


_RESOURCE_TYPE_LABELS = {
    "google_sql_database_instance": "Cloud SQL",
    "google_cloud_run_service": "Cloud Run",
    "google_cloud_run_v2_service": "Cloud Run",
    "google_cloud_run_v2_job": "Cloud Run Job",
    "google_storage_bucket": "GCS Bucket",
    "google_bigquery_dataset": "BigQuery",
    "google_bigquery_table": "BigQuery",
    "google_compute_instance": "Compute Engine VM",
    "google_container_cluster": "GKE Cluster",
    "google_redis_instance": "Cloud Memorystore",
    "google_pubsub_topic": "Pub/Sub",
    "google_pubsub_subscription": "Pub/Sub",
}


def _resource_label(address: str) -> str:
    """Extract a human-readable label from a terraform resource address."""
    # address looks like: module.cloud_sql_postgres.google_sql_database_instance.postgres
    parts = address.split(".")
    for part in parts:
        if part in _RESOURCE_TYPE_LABELS:
            return _RESOURCE_TYPE_LABELS[part]
        if part.startswith("google_"):
            return part  # fall back to raw type name
    return address


# Resource types that bill 24/7 whether or not the stack is used. Anything with a
# cost that is NOT in this set is treated as usage-based (scales with activity).
_FIXED_TYPES = {
    "google_sql_database_instance",  # Cloud SQL — always-on Postgres
    "google_redis_instance",         # Memorystore — always-on
    "google_container_cluster",      # GKE control plane — always-on
    "google_compute_instance",       # VM — always-on
}

# Plain-English "what it is" text. Module-prefix descriptions are more specific
# (they name the tool), so they win over the generic per-type fallback below.
_MODULE_DESCRIPTIONS = {
    "cloud_sql_postgres": "MLflow's backend database",
    "experiment_tracking_mlflow": "MLflow tracking server",
    "artifact_tracking": "MLflow model artifacts",
    "model_serving_fastapi": "FastAPI model server",
    "model_monitoring_grafana": "Grafana dashboards",
}
_TYPE_DESCRIPTIONS = {
    "google_sql_database_instance": "always-on Postgres database",
    "google_cloud_run_service": "serverless container",
    "google_cloud_run_v2_service": "serverless container",
    "google_cloud_run_v2_job": "scheduled batch job",
    "google_storage_bucket": "object / artifact storage",
    "google_bigquery_dataset": "prediction & feature queries",
    "google_bigquery_table": "prediction & feature storage",
    "google_compute_instance": "virtual machine",
    "google_container_cluster": "Kubernetes control plane",
    "google_redis_instance": "in-memory cache",
}


def _resource_type_from_address(address: str) -> str:
    """Pull the google_* resource type out of a terraform address."""
    for part in address.split("."):
        if part.startswith("google_"):
            return part
    return ""


def _classify_category(resource_type: str) -> str:
    """'fixed' if the resource bills 24/7, else 'usage'."""
    return "fixed" if resource_type in _FIXED_TYPES else "usage"


def _resource_description(address: str, resource_type: str) -> str:
    """Prefer a tool-specific description from the module name, else per-type text."""
    parts = address.split(".")
    if len(parts) >= 2 and parts[0] == "module":
        # strip the count index, e.g. model_serving_fastapi[0] -> model_serving_fastapi
        module_name = parts[1].split("[")[0]
        desc = _MODULE_DESCRIPTIONS.get(module_name)
        if desc:
            return desc
    return _TYPE_DESCRIPTIONS.get(resource_type, resource_type or "resource")


@dataclass
class CostAnalysis:
    total_monthly_cost: float
    currency: str
    resources: int
    costed_resources: int
    free_resources: int


@dataclass
class ResourceCost:
    """A single costed resource, classified and labelled for the estimate view."""
    address: str          # module.cloud_sql_postgres.google_sql_database_instance.postgres
    resource_type: str    # google_sql_database_instance
    monthly_cost: float
    category: str         # "fixed" | "usage"
    label: str            # "Cloud SQL"
    description: str      # "MLflow's backend database"


def _row_to_resource_cost(row: Dict) -> ResourceCost:
    """Map one `infracost inspect --group-by resource` row to a ResourceCost."""
    cost = float(row.get("cost", 0) or 0)
    address = row.get("columns", {}).get("resource", "")
    resource_type = _resource_type_from_address(address)
    return ResourceCost(
        address=address,
        resource_type=resource_type,
        monthly_cost=cost,
        category=_classify_category(resource_type),
        label=_resource_label(address),
        description=_resource_description(address, resource_type),
    )


def check_infracost_available() -> bool:
    try:
        result = run_tool(
            "infracost", ["--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False


def check_infracost_authenticated() -> bool:
    if os.environ.get("INFRACOST_API_KEY"):
        return True
    # v2 on macOS stores token here; v1 / Linux uses ~/.config/infracost/credentials.yml
    macos_token = Path.home() / "Library" / "Application Support" / "infracost" / "token.json"
    linux_creds = Path.home() / ".config" / "infracost" / "credentials.yml"
    return macos_token.exists() or linux_creds.exists()


# Substrings infracost uses when the problem is credentials rather than terraform.
_AUTH_ERROR_HINTS = (
    "unauthorized", "unauthenticated", "invalid api key", "invalid token",
    "expired", "log in", "login", "not authenticated", "401", "403",
)


def _report_scan_failure(stderr: str) -> None:
    """
    Explain a failed scan, and name the fix when it is an auth problem.

    check_infracost_authenticated() can only see whether a token file exists, so
    an expired token passes the pre-flight check and fails here instead. Rather
    than dump a raw stderr at the student, recognise the auth case and tell them
    what to run.
    """
    text = (stderr or "").strip()
    if any(hint in text.lower() for hint in _AUTH_ERROR_HINTS):
        typer.secho(
            "  Infracost rejected your credentials (the saved token may have expired).",
            fg=typer.colors.YELLOW,
        )
        typer.echo("   Run: infracost auth login")
        return
    typer.echo(f"Infracost scan failed: {text}")


def run_infracost_scan_with_usage(
    terraform_dir: Path,
    usage_profile: Dict,
    resource_usage: Optional[Dict[str, Dict[str, float]]] = None,
) -> Optional[Dict]:
    """
    Run infracost v2 with a usage profile applied and return parsed JSON.

    v2 has no --usage-file flag; usage must be supplied via an auto-discovered
    infracost.yml. That config route also does NOT auto-load terraform.tfvars and
    requires paths relative to the config file (absolute paths return 0
    resources). So we:
      1. copy the rendered terraform into <config_dir>/tf
      2. write <config_dir>/infracost-usage.yml and <config_dir>/infracost.yml
         (relative `path: tf`, usage_file, terraform_var_files: [terraform.tfvars])
      3. run `infracost scan --json` with cwd = config_dir

    `usage_profile` sets type-wide defaults (the light/heavy estimate path);
    `resource_usage` pins usage to individual terraform addresses (the measured
    path used by `deployml costs`). Either may be empty.
    """
    from deployml.utils.usage_profiles import render_usage_yaml

    config_dir = Path(tempfile.mkdtemp())
    try:
        shutil.copytree(terraform_dir, config_dir / "tf")
        (config_dir / "infracost-usage.yml").write_text(
            render_usage_yaml(usage_profile, resource_usage)
        )
        (config_dir / "infracost.yml").write_text(
            "version: 0.1\n"
            "projects:\n"
            "  - path: tf\n"
            "    usage_file: infracost-usage.yml\n"
            "    terraform_var_files: [terraform.tfvars]\n"
        )
        result = run_tool(
            "infracost", ["scan", "--json"],
            cwd=config_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            _report_scan_failure(result.stderr)
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        typer.echo("Infracost scan timed out")
        return None
    except json.JSONDecodeError:
        typer.echo("Failed to parse infracost JSON output")
        return None
    except (FileNotFoundError, subprocess.SubprocessError, OSError) as e:
        typer.echo(f"Infracost error: {e}")
        return None
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)


def _run_inspect_rows(scan_json_path: Path) -> List[Dict]:
    """
    Run `infracost inspect --file <scan_json> --group-by resource --json` and
    return the raw rows (or [] on any failure).

    Passing --file pins inspect to the exact scan we just produced. Without it,
    inspect reads infracost's global "most recent scan" cache, so a prior or
    concurrent scan of a different workspace could be reported here instead.
    """
    try:
        result = run_tool(
            "infracost",
            [
                "inspect",
                "--file",
                str(scan_json_path),
                "--group-by",
                "resource",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            typer.secho(
                "  Could not read the per-resource cost breakdown "
                "(infracost inspect failed); showing totals only.",
                fg=typer.colors.YELLOW,
            )
            return []
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, ValueError, OSError):
        typer.secho(
            "  Could not read the per-resource cost breakdown; showing totals only.",
            fg=typer.colors.YELLOW,
        )
        return []


def fetch_resource_costs_detailed(scan_json_path: Path) -> List[ResourceCost]:
    """
    Return per-resource ResourceCost records (non-zero cost only), each classified
    as fixed vs usage and labelled in plain English. Drives the estimate view.
    """
    resources = [
        _row_to_resource_cost(row)
        for row in _run_inspect_rows(scan_json_path)
    ]
    resources = [r for r in resources if r.monthly_cost > 0]
    return sorted(resources, key=lambda r: r.monthly_cost, reverse=True)


def parse_infracost_scan_data(data: Dict) -> Optional[CostAnalysis]:
    """
    Parse v2 infracost JSON into a CostAnalysis.

    Two schemas exist depending on how infracost is invoked:
    - `infracost scan --json`: fields under a top-level "summary" key,
      cost field is "total_monthly_cost"
    - `infracost inspect --json`: fields at top level, cost field is "monthly_cost"
    """
    try:
        if "summary" in data:
            # infracost scan --json format
            summary = data["summary"]
            monthly_cost_str = summary.get("total_monthly_cost", "0") or "0"
            return CostAnalysis(
                total_monthly_cost=float(monthly_cost_str),
                currency=data.get("currency", "USD"),
                resources=int(summary.get("resources", 0)),
                costed_resources=int(summary.get("costed_resources", 0)),
                free_resources=int(summary.get("free_resources", 0)),
            )
        # infracost inspect --json format
        monthly_cost_str = data.get("monthly_cost", "0") or "0"
        return CostAnalysis(
            total_monthly_cost=float(monthly_cost_str),
            currency=data.get("currency", "USD"),
            resources=int(data.get("resources", 0)),
            costed_resources=int(data.get("costed_resources", 0)),
            free_resources=int(data.get("free_resources", 0)),
        )
    except (ValueError, TypeError) as e:
        typer.echo(f"Failed to parse cost data: {e}")
        return None


def format_cost_for_confirmation(monthly_cost: float, currency: str) -> str:
    if monthly_cost > 0:
        return f"Monthly cost: ~${monthly_cost:.2f} {currency}"
    else:
        return "Monthly cost: Variable (usage-based pricing)"


def display_estimate(
    resources: List[ResourceCost],
    analysis: CostAnalysis,
    profile_name: str,
    warning_threshold: float = 100.0,
) -> None:
    """
    Render the estimate view: a headline split into fixed vs usage cost, the two
    buckets with plain-English labels, and a call-out for the biggest cost lever.
    """
    fixed = [r for r in resources if r.category == "fixed"]
    usage = [r for r in resources if r.category == "usage"]
    fixed_total = sum(r.monthly_cost for r in fixed)
    usage_total = sum(r.monthly_cost for r in usage)
    total = analysis.total_monthly_cost
    currency = analysis.currency

    typer.echo("\n" + "=" * 60)
    typer.secho("  MONTHLY COST", fg=typer.colors.BRIGHT_CYAN, bold=True)
    typer.echo("=" * 60)
    headline_color = (
        typer.colors.BRIGHT_GREEN if total < warning_threshold
        else typer.colors.BRIGHT_YELLOW
    )
    typer.secho(
        f"  ~${total:,.0f} / month   "
        f"(${fixed_total:,.2f} fixed  +  ~${usage_total:,.2f} usage)  {currency}",
        fg=headline_color,
        bold=True,
    )

    if fixed:
        typer.echo()
        typer.secho("  ALWAYS-ON  (billed 24/7 even if you never use the stack)", bold=True)
        for r in fixed:
            typer.secho(
                f"    ${r.monthly_cost:>8.2f}  {r.label:<12} {r.description}",
                fg=typer.colors.BRIGHT_BLUE,
            )

    if usage:
        typer.echo()
        typer.secho(
            f"  USAGE-BASED  (scales with activity · profile: {profile_name})", bold=True
        )
        # Collapse identical rows (e.g. the four BigQuery tables) into one line.
        grouped: "OrderedDict[Tuple[str, str], Tuple[float, int]]" = OrderedDict()
        for r in usage:
            key = (r.label, r.description)
            cost, count = grouped.get(key, (0.0, 0))
            grouped[key] = (cost + r.monthly_cost, count + 1)
        for (label, description), (cost, count) in grouped.items():
            suffix = f" (x{count})" if count > 1 else ""
            typer.secho(
                f"    ${cost:>8.2f}  {label:<12} {description}{suffix}",
                fg=typer.colors.BRIGHT_BLUE,
            )

    # Biggest lever: if one always-on resource dominates, tell the student.
    if fixed and total > 0:
        top = max(fixed, key=lambda r: r.monthly_cost)
        share = top.monthly_cost / total
        if share > 0.5:
            typer.echo()
            typer.secho(
                f"  Biggest lever: {top.label} is {share * 100:.0f}% of your cost and runs 24/7.",
                fg=typer.colors.BRIGHT_MAGENTA,
                bold=True,
            )
            if top.resource_type == "google_sql_database_instance":
                typer.secho(
                    "  Switch MLflow to a SQLite backend to drop this to ~$0/month.",
                    fg=typer.colors.BRIGHT_MAGENTA,
                )

    omitted = max(analysis.resources - len(resources), 0)
    if omitted:
        typer.echo()
        typer.echo(f"  {omitted} free / API-enablement resources omitted (no cost).")

    typer.echo(
        "\n  Note: usage costs are estimated at this profile's load. Heavier use\n"
        "  raises the usage line, not the fixed baseline."
    )

    if total > warning_threshold:
        typer.echo()
        typer.secho(
            f"  WARNING: exceeds ${warning_threshold:.0f}/month threshold!",
            fg=typer.colors.BRIGHT_RED,
            bold=True,
        )
    typer.echo()


def run_estimate_analysis(
    terraform_dir: Path,
    profile_name: str = "light",
    warning_threshold: float = 100.0,
) -> Optional[CostAnalysis]:
    """
    Scan `terraform_dir` with a usage profile applied, then render the estimate
    view. Assumes infracost availability/auth has already been checked by the
    caller. Returns the CostAnalysis, or None on failure.
    """
    from deployml.utils.usage_profiles import get_profile

    typer.echo(f"Running cost estimate (usage profile: {profile_name})...")
    raw_data = run_infracost_scan_with_usage(terraform_dir, get_profile(profile_name))
    if raw_data is None:
        return None

    analysis = parse_infracost_scan_data(raw_data)
    if analysis is None:
        return None

    scan_dir = Path(tempfile.mkdtemp())
    scan_json_path = scan_dir / "infracost-scan.json"
    try:
        scan_json_path.write_text(json.dumps(raw_data))
        resources = fetch_resource_costs_detailed(scan_json_path)
    finally:
        shutil.rmtree(scan_dir, ignore_errors=True)

    display_estimate(resources, analysis, profile_name, warning_threshold)
    return analysis


def display_actual_costs(
    resources: List[ResourceCost],
    analysis: CostAnalysis,
    measured: "MeasuredUsage",
    workspace_name: str,
    profile_label: str,
    profile_ratio: float,
    deployed_days: Optional[float] = None,
    warning_threshold: float = 100.0,
) -> None:
    """
    Render the measured-cost view for a running deployment.

    Same two-bucket shape as display_estimate, with three additions that only
    make sense once the stack actually exists: each usage line is annotated with
    the real numbers behind it, the always-on line reports how much of the window
    the database was up, and the student gets told which profile their real usage
    resembles.
    """
    fixed = [r for r in resources if r.category == "fixed"]
    usage = [r for r in resources if r.category == "usage"]
    fixed_total = sum(r.monthly_cost for r in fixed)
    usage_total = sum(r.monthly_cost for r in usage)
    total = analysis.total_monthly_cost
    currency = analysis.currency
    window = measured.window_days

    typer.echo("\n" + "=" * 60)
    typer.secho(f"  ACTUAL COST  ·  {workspace_name}", fg=typer.colors.BRIGHT_CYAN, bold=True)
    typer.echo("=" * 60)
    typer.echo(f"  Measured from your real GCP usage over the last {window:g} days.")
    typer.echo()

    headline_color = (
        typer.colors.BRIGHT_GREEN if total < warning_threshold
        else typer.colors.BRIGHT_YELLOW
    )
    typer.secho(
        f"  Run-rate: ~${total:,.0f} / month   "
        f"(${fixed_total:,.2f} always-on  +  ~${usage_total:,.2f} measured usage)  {currency}",
        fg=headline_color,
        bold=True,
    )
    if deployed_days:
        # Straight-line projection from the monthly run-rate. Not a billed figure:
        # for that a student needs a BigQuery billing export.
        so_far = total * (deployed_days / 30.0)
        typer.secho(
            f"  Charged so far: ~${so_far:,.2f}   "
            f"({deployed_days:.1f} days since deploy, approximate)",
            fg=headline_color,
        )

    if fixed:
        typer.echo()
        typer.secho("  ALWAYS-ON  (billed 24/7 while the stack exists)", bold=True)
        for r in fixed:
            line = f"    ${r.monthly_cost:>8.2f}  {r.label:<12} {r.description}"
            uptime = measured.sql_uptime.get(r.address)
            if uptime is not None:
                line += f"  ·  up {uptime * 100:.0f}% of window"
            typer.secho(line, fg=typer.colors.BRIGHT_BLUE)

    if usage:
        typer.echo()
        typer.secho(
            f"  USAGE-BASED  (measured over {window:g} days, scaled to a month)", bold=True
        )
        # Collapse identical rows the way display_estimate does, but carry each
        # group's measured detail through so the numbers stay visible.
        grouped: "OrderedDict[Tuple[str, str], List]" = OrderedDict()
        for r in usage:
            key = (r.label, r.description)
            entry = grouped.setdefault(key, [0.0, 0, []])
            entry[0] += r.monthly_cost
            entry[1] += 1
            detail = measured.details.get(r.address)
            if detail and detail not in entry[2]:
                entry[2].append(detail)
        for (label, description), (cost, count, details) in grouped.items():
            suffix = f" (x{count})" if count > 1 else ""
            line = f"    ${cost:>8.2f}  {label:<12} {description}{suffix}"
            if details:
                line += "  ·  " + "; ".join(details)
            typer.secho(line, fg=typer.colors.BRIGHT_BLUE)

    # The payoff of measuring: light/heavy become labels, not pricing inputs.
    if measured.cloud_run_monthly_requests > 0:
        typer.echo()
        typer.secho(
            f"  You are a {profile_label.upper()} user — your real usage is "
            f"{profile_ratio:.1f}x the '{profile_label}' profile.",
            fg=typer.colors.BRIGHT_CYAN,
        )

    if fixed and total > 0:
        top = max(fixed, key=lambda r: r.monthly_cost)
        share = top.monthly_cost / total
        if share > 0.5:
            typer.echo()
            typer.secho(
                f"  Biggest lever: {top.label} is {share * 100:.0f}% of your cost "
                f"and runs 24/7.",
                fg=typer.colors.BRIGHT_MAGENTA,
                bold=True,
            )
            typer.secho(
                "  Tear the stack down when you are not using it:  deployml destroy",
                fg=typer.colors.BRIGHT_MAGENTA,
            )

    if measured.notes:
        # Covers both what Monitoring could not report (priced at $0) and the
        # places where a measurement is an approximation. Either way the student
        # sees why a number is what it is.
        typer.echo()
        typer.secho("  About these numbers:", bold=True)
        for note in measured.notes:
            typer.echo(f"    - {note}")

    typer.echo(
        "\n  Note: this prices your real usage, it is not a billing statement.\n"
        "  Check the GCP Billing Console for the amount you were actually charged."
    )

    if total > warning_threshold:
        typer.echo()
        typer.secho(
            f"  WARNING: exceeds ${warning_threshold:.0f}/month threshold!",
            fg=typer.colors.BRIGHT_RED,
            bold=True,
        )
    typer.echo()


def run_actual_cost_analysis(
    terraform_dir: Path,
    project_id: str,
    workspace_name: str,
    days: float = 30.0,
    warning_threshold: float = 100.0,
    deployed_days: Optional[float] = None,
) -> Optional[CostAnalysis]:
    """
    Price a running deployment from its real usage, then render the result.

    Same contract as run_estimate_analysis: assumes the caller already checked
    infracost availability and auth, prints its own diagnostics, and returns the
    CostAnalysis or None.

    The usage profile passed to infracost is deliberately empty. Only the
    measured per-address numbers are supplied, so anything Monitoring could not
    tell us stays at zero instead of falling back to a light/heavy guess, and
    the reason is printed in the "Not measured" section.
    """
    from deployml.utils.measured_usage import (
        MonitoringError,
        build_resource_map,
        collect_measured_usage,
    )
    from deployml.utils.usage_profiles import classify_usage_profile

    deployed = build_resource_map(terraform_dir)
    if not deployed:
        typer.secho(
            "  Could not read any deployed resources from the terraform state.",
            fg=typer.colors.YELLOW,
        )
        typer.echo(
            "   Run 'deployml deploy' first, or 'deployml estimate' for a "
            "pre-deploy prediction."
        )
        return None

    typer.echo(
        f"Measuring real usage for {len(deployed)} deployed resources "
        f"over the last {days:g} days..."
    )
    try:
        measured = collect_measured_usage(project_id, deployed, days)
    except MonitoringError as e:
        typer.secho(f"  {e}", fg=typer.colors.BRIGHT_RED)
        if e.hint:
            for line in e.hint.splitlines():
                typer.echo(f"   {line}")
        return None

    if measured.is_empty():
        typer.secho(
            "  No usage has been recorded for this deployment yet.",
            fg=typer.colors.YELLOW,
        )
        typer.echo(
            "   Monitoring data takes a few minutes to appear after a deploy. "
            "Showing always-on cost only."
        )

    raw_data = run_infracost_scan_with_usage(
        terraform_dir, {}, measured.resource_usage
    )
    if raw_data is None:
        return None

    analysis = parse_infracost_scan_data(raw_data)
    if analysis is None:
        return None

    scan_dir = Path(tempfile.mkdtemp())
    scan_json_path = scan_dir / "infracost-scan.json"
    try:
        scan_json_path.write_text(json.dumps(raw_data))
        resources = fetch_resource_costs_detailed(scan_json_path)
    finally:
        shutil.rmtree(scan_dir, ignore_errors=True)

    profile_label, profile_ratio = classify_usage_profile(
        measured.cloud_run_monthly_requests
    )
    display_actual_costs(
        resources,
        analysis,
        measured,
        workspace_name,
        profile_label,
        profile_ratio,
        deployed_days=deployed_days,
        warning_threshold=warning_threshold,
    )
    return analysis
