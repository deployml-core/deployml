import json
import os
import subprocess
import typer
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


@dataclass
class CostAnalysis:
    total_monthly_cost: float
    currency: str
    resources: int
    costed_resources: int
    free_resources: int
    resource_costs: List[Tuple[str, float]] = field(default_factory=list)


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


def fetch_resource_costs() -> List[Tuple[str, float]]:
    """
    Run `infracost inspect --group-by resource --json` against the last cached
    scan and return a list of (label, monthly_cost) for non-zero cost resources.
    """
    try:
        result = subprocess.run(
            ["infracost", "inspect", "--group-by", "resource", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        rows = json.loads(result.stdout)
        costs = []
        seen_labels = set()
        for row in rows:
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
    except Exception:
        return []


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
        analysis.resource_costs = fetch_resource_costs()

    display_cost_breakdown(analysis, warning_threshold, show_resources=show_resources)
    return analysis
