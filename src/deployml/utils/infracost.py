import json
import os
import shutil
import subprocess
import tempfile
import typer
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


_RESOURCE_TYPE_LABELS = {
    "google_sql_database_instance": "Cloud SQL",
    "google_cloud_run_service": "Cloud Run",
    "google_cloud_run_v2_service": "Cloud Run",
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
    "bigquery": "prediction logging & analytics",
}
_TYPE_DESCRIPTIONS = {
    "google_sql_database_instance": "always-on Postgres database",
    "google_cloud_run_service": "serverless container",
    "google_cloud_run_v2_service": "serverless container",
    "google_storage_bucket": "object / artifact storage",
    "google_bigquery_dataset": "analytics queries",
    "google_bigquery_table": "analytics storage",
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
    resource_costs: List[Tuple[str, float]] = field(default_factory=list)


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
        result = subprocess.run(
            ["infracost", "--version"],
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


def run_infracost_scan(terraform_dir: Path) -> Optional[Dict]:
    """
    Run infracost v2 scan and return parsed JSON.
    Uses `infracost scan <dir> --json`. Falls back to flag-before-subcommand
    form if needed, since --json is a global flag in v2.
    Does not require terraform init — infracost v2 parses HCL directly.
    """
    cmds = [
        ["infracost", "scan", str(terraform_dir), "--json"],
        ["infracost", "--json", "scan", str(terraform_dir)],
    ]
    for cmd in cmds:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            if "unknown flag" not in result.stderr:
                typer.echo(f"Infracost scan failed: {result.stderr}")
                return None
            # unknown flag → try next form
        except subprocess.TimeoutExpired:
            typer.echo("Infracost scan timed out")
            return None
        except json.JSONDecodeError:
            typer.echo("Failed to parse infracost JSON output")
            return None
        except (FileNotFoundError, subprocess.SubprocessError) as e:
            typer.echo(f"Infracost error: {e}")
            return None
    typer.echo("Infracost scan failed: could not find working --json flag form")
    return None


def run_infracost_scan_with_usage(
    terraform_dir: Path, usage_profile: Dict
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
    """
    from deployml.utils.usage_profiles import render_usage_yaml

    config_dir = Path(tempfile.mkdtemp())
    try:
        shutil.copytree(terraform_dir, config_dir / "tf")
        (config_dir / "infracost-usage.yml").write_text(
            render_usage_yaml(usage_profile)
        )
        (config_dir / "infracost.yml").write_text(
            "version: 0.1\n"
            "projects:\n"
            "  - path: tf\n"
            "    usage_file: infracost-usage.yml\n"
            "    terraform_var_files: [terraform.tfvars]\n"
        )
        result = subprocess.run(
            ["infracost", "scan", "--json"],
            cwd=config_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            typer.echo(f"Infracost scan failed: {result.stderr}")
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
        result = subprocess.run(
            [
                "infracost",
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
            return []
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, ValueError, OSError):
        return []


def fetch_resource_costs(scan_json_path: Path) -> List[Tuple[str, float]]:
    """
    Return a list of (label, monthly_cost) for non-zero cost resources, grouped
    by GCP service label. Used by the simple deploy/costs breakdown view.
    """
    costs: List[Tuple[str, float]] = []
    seen_labels = set()
    for row in _run_inspect_rows(scan_json_path):
        cost = float(row.get("cost", 0) or 0)
        if cost <= 0:
            continue
        address = row.get("columns", {}).get("resource", "")
        label = _resource_label(address)
        if label in seen_labels:
            # Accumulate duplicate resource types (e.g. multiple Cloud Run services)
            for i, (lbl, c) in enumerate(costs):
                if lbl == label:
                    costs[i] = (lbl, c + cost)
                    break
        else:
            seen_labels.add(label)
            costs.append((label, cost))
    return sorted(costs, key=lambda x: x[1], reverse=True)


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


def display_cost_breakdown(
    analysis: CostAnalysis,
    warning_threshold: float = 100.0,
    show_resources: bool = False,
) -> None:
    typer.echo("\n" + "=" * 60)
    typer.secho("COST ANALYSIS", fg=typer.colors.BRIGHT_CYAN, bold=True)
    typer.echo("=" * 60)

    monthly_cost = analysis.total_monthly_cost
    color = typer.colors.BRIGHT_GREEN if monthly_cost < warning_threshold else typer.colors.BRIGHT_YELLOW
    typer.secho(
        f"Monthly Cost: ${monthly_cost:.2f} {analysis.currency}",
        fg=color,
        bold=True,
    )
    typer.echo(
        f"Resources:    {analysis.costed_resources} costed, "
        f"{analysis.free_resources} free, {analysis.resources} total"
    )

    if show_resources and analysis.resource_costs:
        typer.echo("\nWhat costs money:")
        for label, cost in analysis.resource_costs:
            typer.secho(f"  ${cost:.2f}  {label}", fg=typer.colors.BRIGHT_BLUE)
        typer.echo(
            "\nNote: Cloud Run, BigQuery, and GCS show $0 at idle — they scale to\n"
            "zero and charge only for actual usage."
        )

    if monthly_cost > warning_threshold:
        typer.echo()
        typer.secho(
            f"WARNING: Monthly cost exceeds ${warning_threshold:.0f} threshold!",
            fg=typer.colors.BRIGHT_RED,
            bold=True,
        )
    typer.echo()


def format_cost_for_confirmation(monthly_cost: float, currency: str) -> str:
    if monthly_cost > 0:
        return f"Monthly cost: ~${monthly_cost:.2f} {currency}"
    else:
        return "Monthly cost: Variable (usage-based pricing)"


def run_infracost_analysis(
    terraform_dir: Path,
    warning_threshold: float = 100.0,
    show_resources: bool = False,
) -> Optional[CostAnalysis]:
    if not check_infracost_available():
        typer.echo("Tip: Install infracost CLI for cost analysis before deployment")
        typer.echo("   Visit: https://www.infracost.io/docs/#quick-start")
        return None

    if not check_infracost_authenticated():
        typer.echo("Tip: Authenticate infracost to enable cost analysis")
        typer.echo("   Run: infracost auth login")
        typer.echo("   Or set: export INFRACOST_API_KEY=<your-key>")
        return None

    typer.echo("Running cost analysis...")
    raw_data = run_infracost_scan(terraform_dir)
    if raw_data is None:
        return None

    analysis = parse_infracost_scan_data(raw_data)
    if analysis is None:
        return None

    if show_resources:
        # Write the scan result to a temp file and inspect it explicitly, rather
        # than letting infracost read its global "most recent scan" cache.
        scan_dir = Path(tempfile.mkdtemp())
        scan_json_path = scan_dir / "infracost-scan.json"
        try:
            scan_json_path.write_text(json.dumps(raw_data))
            analysis.resource_costs = fetch_resource_costs(scan_json_path)
        finally:
            shutil.rmtree(scan_dir, ignore_errors=True)

    display_cost_breakdown(analysis, warning_threshold, show_resources=show_resources)
    return analysis


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
