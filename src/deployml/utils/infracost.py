import json
import subprocess
import typer
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass

from deployml.utils.platform_compat import run_tool


@dataclass
class CostComponent:
    """Represents a single cost component for a resource"""

    name: str
    unit: str
    monthly_cost: float
    hourly_cost: float
    usage_based: bool = False


@dataclass
class ResourceCost:
    """Represents cost information for a single resource"""

    name: str
    resource_type: str
    monthly_cost: float
    hourly_cost: float
    components: List[CostComponent]


@dataclass
class CostAnalysis:
    """Represents the complete cost analysis results"""

    total_monthly_cost: float
    total_hourly_cost: float
    currency: str
    resources: List[ResourceCost]
    detected_resources: int
    supported_resources: int


def check_infracost_available() -> bool:
    """
    Check if infracost CLI is available in the system PATH.

    Returns:
        bool: True if infracost is available, False otherwise.
    """
    try:
        result = run_tool(
            "infracost", ["--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (
        subprocess.TimeoutExpired,
        FileNotFoundError,
        subprocess.SubprocessError,
    ):
        return False


def run_infracost_breakdown(terraform_dir: Path, usage_file: Optional[Path] = None) -> Optional[Dict]:
    """
    Run infracost breakdown analysis on the terraform directory.

    Args:
        terraform_dir: Path to the terraform directory

    Returns:
        Dict containing the infracost JSON output, or None if failed
    """
    if not check_infracost_available():
        return None

    try:
        # Run infracost breakdown and capture JSON output
        cmd = [
            "infracost",
            "breakdown",
            "--path",
            str(terraform_dir),
            "--format",
            "json",
        ]
        if usage_file is not None:
            cmd.extend(["--usage-file", str(usage_file)])

        result = run_tool(
            cmd[0], cmd[1:],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            typer.echo(f"⚠️ Infracost analysis failed: {result.stderr}")
            return None

    except subprocess.TimeoutExpired:
        typer.echo("⚠️ Infracost analysis timed out")
        return None
    except json.JSONDecodeError:
        typer.echo("⚠️ Failed to parse infracost output")
        return None
    except Exception as e:
        typer.echo(f"⚠️ Infracost error: {e}")
        return None


def parse_infracost_data(data: Dict) -> Optional[CostAnalysis]:
    """
    Parse infracost JSON data into structured cost analysis.

    Args:
        data: Raw infracost JSON data

    Returns:
        CostAnalysis object or None if parsing failed
    """
    try:
        resources = []

        for project in data.get("projects", []):
            breakdown = project.get("breakdown", {})

            for resource_data in breakdown.get("resources", []):
                components = []

                # Parse cost components
                for comp_data in resource_data.get("costComponents", []):
                    monthly_cost = comp_data.get("monthlyCost")
                    hourly_cost = comp_data.get("hourlyCost")

                    # Skip components without cost data
                    if monthly_cost is None and hourly_cost is None:
                        continue

                    component = CostComponent(
                        name=comp_data.get("name", ""),
                        unit=comp_data.get("unit", ""),
                        monthly_cost=float(monthly_cost or 0),
                        hourly_cost=float(hourly_cost or 0),
                        usage_based=comp_data.get("usageBased", False),
                    )
                    components.append(component)

                resource = ResourceCost(
                    name=resource_data.get("name", ""),
                    resource_type=resource_data.get("resourceType", ""),
                    monthly_cost=float(resource_data.get("monthlyCost", 0)),
                    hourly_cost=float(resource_data.get("hourlyCost", 0)),
                    components=components,
                )
                resources.append(resource)

        return CostAnalysis(
            total_monthly_cost=float(data.get("totalMonthlyCost", 0)),
            total_hourly_cost=float(data.get("totalHourlyCost", 0)),
            currency=data.get("currency", "USD"),
            resources=resources,
            detected_resources=data.get("summary", {}).get(
                "totalDetectedResources", 0
            ),
            supported_resources=data.get("summary", {}).get(
                "totalSupportedResources", 0
            ),
        )

    except Exception as e:
        typer.echo(f"⚠️ Failed to parse cost data: {e}")
        return None


def display_cost_breakdown(
    analysis: CostAnalysis, warning_threshold: float = 100.0
) -> None:
    """
    Display a user-friendly cost breakdown.

    Args:
        analysis: CostAnalysis object with cost data
        warning_threshold: Monthly cost threshold for warnings (default: $100)
    """
    typer.echo("\n" + "=" * 60)
    typer.secho("💰 COST ANALYSIS", fg=typer.colors.BRIGHT_CYAN, bold=True)
    typer.echo("=" * 60)

    # Overall costs
    monthly_cost = analysis.total_monthly_cost
    typer.secho(
        f"Monthly Cost: ${monthly_cost:.2f} {analysis.currency}",
        fg=(
            typer.colors.BRIGHT_GREEN
            if monthly_cost < warning_threshold
            else typer.colors.BRIGHT_YELLOW
        ),
        bold=True,
    )
    typer.echo(
        f"Hourly Cost:  ${analysis.total_hourly_cost:.4f} {analysis.currency}"
    )
    typer.echo(
        f"Resources: {analysis.supported_resources} supported, {analysis.detected_resources} total"
    )

    # Warning for high costs
    if monthly_cost > warning_threshold:
        typer.echo()
        typer.secho(
            f"⚠️  WARNING: Monthly cost exceeds ${warning_threshold:.0f} threshold!",
            fg=typer.colors.BRIGHT_RED,
            bold=True,
        )

    # Resource breakdown
    if analysis.resources:
        typer.echo("\n📋 Resource Breakdown:")
        typer.echo("-" * 40)

        # Sort resources by monthly cost (highest first)
        sorted_resources = sorted(
            analysis.resources, key=lambda r: r.monthly_cost, reverse=True
        )

        for resource in sorted_resources:
            if resource.monthly_cost > 0:
                typer.echo(f"\n• {resource.name}")
                typer.echo(f"  Type: {resource.resource_type}")
                typer.secho(
                    f"  Monthly Cost: ${resource.monthly_cost:.2f}",
                    fg=typer.colors.BRIGHT_BLUE,
                )

                # Show top cost components
                if resource.components:
                    for component in resource.components[
                        :3
                    ]:  # Show top 3 components
                        if component.monthly_cost > 0:
                            usage_note = (
                                " (usage-based)"
                                if component.usage_based
                                else ""
                            )
                            typer.echo(
                                f"    └─ {component.name}: ${component.monthly_cost:.2f}{usage_note}"
                            )

    # Usage-based resources note
    usage_based_resources = [
        r
        for r in analysis.resources
        if any(c.usage_based for c in r.components)
    ]

    if usage_based_resources:
        typer.echo("\n📊 Note: Some resources have usage-based pricing")
        typer.echo("   Actual costs may vary based on usage patterns")

    typer.echo()


def format_cost_for_confirmation(monthly_cost: float, currency: str) -> str:
    """
    Format cost information for the deployment confirmation prompt.

    Args:
        monthly_cost: Monthly cost in the specified currency
        currency: Currency code (e.g., 'USD')

    Returns:
        Formatted string for confirmation prompt
    """
    if monthly_cost > 0:
        return f"💰 Monthly cost: ~${monthly_cost:.2f} {currency}"
    else:
        return "💰 Monthly cost: Variable (usage-based pricing)"


def run_infracost_analysis(
    terraform_dir: Path, warning_threshold: float = 100.0, usage_file: Optional[Path] = None
) -> Optional[CostAnalysis]:
    """
    Run complete infracost analysis workflow.

    Args:
        terraform_dir: Path to terraform directory
        warning_threshold: Cost warning threshold

    Returns:
        CostAnalysis object or None if analysis failed
    """
    # Check if infracost is available
    if not check_infracost_available():
        typer.echo(
            "💡 Tip: Install infracost CLI for cost analysis before deployment"
        )
        typer.echo("   Visit: https://www.infracost.io/docs/#quick-start")
        return None

    typer.echo("💰 Running cost analysis...")

    # Run infracost breakdown
    raw_data = run_infracost_breakdown(terraform_dir, usage_file=usage_file)
    if not raw_data:
        return None

    # Parse the data
    analysis = parse_infracost_data(raw_data)
    if not analysis:
        return None

    # Display the breakdown
    display_cost_breakdown(analysis, warning_threshold)

    return analysis
