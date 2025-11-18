import sys
import yaml
import typer
import shutil
import subprocess
from deployml.utils.banner import display_banner
from deployml.utils.menu import prompt, show_menu
from deployml.utils.constants import (
    TEMPLATE_DIR,
    TERRAFORM_DIR,
    TOOL_VARIABLES,
    ANIMAL_NAMES,
    FALLBACK_WORDS,
    REQUIRED_GCP_APIS,
)
from deployml.enum.cloud_provider import CloudProvider
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from typing import Optional
import random
import string
from google.cloud import storage
import hashlib

# Import refactored utility functions
from deployml.utils.helpers import (
    check,
    check_gcp_auth,
    copy_modules_to_workspace,
    bucket_exists,
    generate_bucket_name,
    estimate_terraform_time,
    cleanup_cloud_sql_resources,
    cleanup_terraform_files,
    run_terraform_with_loading_bar,
)
from deployml.utils.infracost import (
    check_infracost_available,
    run_infracost_analysis,
    format_cost_for_confirmation,
)
from deployml.utils.teardown import (
    save_deployment_metadata,
    load_deployment_metadata,
    calculate_cron_from_timestamp,
)

import re
import time
import json
from datetime import datetime, timedelta

cli = typer.Typer()


@cli.command()
def doctor(
    project_id: str = typer.Option(
        "", "--project-id", "-j", help="GCP Project ID to check APIs (optional)"
    )
):
    """
    Run system checks for required tools and authentication for DeployML.
    Also checks if all required GCP APIs are enabled if GCP CLI is installed and authenticated.
    """
    typer.echo("\n📋 DeployML Doctor Summary:\n")

    docker_installed = check("docker")
    terraform_installed = check("terraform")
    gcp_installed = check("gcloud")
    gcp_authed = check_gcp_auth() if gcp_installed else False
    aws_installed = check("aws")
    infracost_installed = check_infracost_available()

    # Docker
    if docker_installed:
        typer.secho("\n✅ Docker 🐳 is installed", fg=typer.colors.GREEN)
    else:
        typer.secho("\n❌ Docker is not installed", fg=typer.colors.RED)

    # Terraform
    if terraform_installed:
        typer.secho("\n✅ Terraform 🔧 is installed", fg=typer.colors.GREEN)
    else:
        typer.secho("\n❌ Terraform is not installed", fg=typer.colors.RED)

    # Infracost
    if infracost_installed:
        typer.secho("\n✅ Infracost 💰 is installed", fg=typer.colors.GREEN)
    else:
        typer.secho(
            "\n⚠️ Infracost 💰 not installed (optional)", fg=typer.colors.YELLOW
        )
        typer.echo(
            "   Install for cost analysis: https://www.infracost.io/docs/#quick-start"
        )

    # GCP CLI
    if gcp_installed and gcp_authed:
        typer.secho(
            "\n✅ GCP CLI ☁️  installed and authenticated", fg=typer.colors.GREEN
        )
        # Check enabled GCP APIs
        if not project_id:
            project_id = typer.prompt(
                "Enter your GCP Project ID to check enabled APIs",
                default="",
                show_default=False,
            )
        if project_id:
            typer.echo(
                f"\n🔎 Checking enabled APIs for project: {project_id} ..."
            )
            result = subprocess.run(
                [
                    "gcloud",
                    "services",
                    "list",
                    "--enabled",
                    "--project",
                    project_id,
                    "--format=value(config.name)",
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                typer.echo("❌ Failed to list enabled APIs.")
            else:
                enabled_apis = set(result.stdout.strip().splitlines())
                missing_apis = [
                    api for api in REQUIRED_GCP_APIS if api not in enabled_apis
                ]
                if not missing_apis:
                    typer.secho(
                        "✅ All required GCP APIs are enabled.",
                        fg=typer.colors.GREEN,
                    )
                else:
                    typer.secho(
                        "⚠️  The following required APIs are NOT enabled:",
                        fg=typer.colors.YELLOW,
                    )
                    for api in missing_apis:
                        typer.echo(f"  - {api}")
                    typer.echo(
                        "You can enable them with: deployml init --provider gcp --project-id <PROJECT_ID>"
                    )
    elif gcp_installed:
        typer.secho(
            "\n⚠️ GCP CLI ⛈️  installed but not authenticated",
            fg=typer.colors.YELLOW,
        )
    else:
        typer.secho("\n❌ GCP CLI ⛈️  not installed", fg=typer.colors.RED)

    # AWS CLI
    if aws_installed:
        typer.secho(f"\n✅ AWS CLI ☁️  installed", fg=typer.colors.GREEN)
    else:
        typer.secho("\n❌ AWS CLI ⛈️  not installed", fg=typer.colors.RED)
    typer.echo()


@cli.command()
def vm():
    """
    Create a new Virtual Machine (VM) deployment.
    """
    pass


@cli.command()
def generate():
    """
    Generate a deployment configuration YAML file interactively.
    """
    display_banner("Welcome to DeployML Stack Generator!")
    typer.echo("\n")
    name = prompt("MLOps Stack name", "stack")
    provider = show_menu("☁️  Select Provider", CloudProvider, CloudProvider.GCP)

    # Import DeploymentType here to avoid circular imports
    from deployml.enum.deployment_type import DeploymentType

    deployment_type = show_menu(
        "🚀 Select Deployment Type", DeploymentType, DeploymentType.CLOUD_RUN
    )

    # Get provider-specific details
    if provider == "gcp":
        project_id = prompt("GCP Project ID", "your-project-id")
        region = prompt("GCP Region", "us-west1")
        zone = (
            prompt("GCP Zone", f"{region}-a")
            if deployment_type == "cloud_vm"
            else ""
        )

    # Generate YAML configuration
    config = {
        "name": name,
        "provider": {
            "name": provider,
            "project_id": project_id if provider == "gcp" else "",
            "region": region if provider == "gcp" else "",
        },
    }

    # Add zone for VM deployments
    if deployment_type == "cloud_vm" and provider == "gcp":
        config["provider"]["zone"] = zone

    config["deployment"] = {"type": deployment_type}

    # Add default stack configuration
    config["stack"] = [
        {
            "experiment_tracking": {
                "name": "mlflow",
                "params": {
                    "service_name": f"{name}-mlflow-server",
                    "allow_public_access": True,
                },
            }
        },
        {
            "artifact_tracking": {
                "name": "mlflow",
                "params": {
                    "artifact_bucket": (
                        f"{name}-artifacts-{project_id}"
                        if provider == "gcp"
                        else ""
                    ),
                    "create_bucket": True,
                },
            }
        },
        {
            "model_registry": {
                "name": "mlflow",
                "params": {"backend_store_uri": "sqlite:///mlflow.db"},
            }
        },
    ]

    # Add VM-specific parameters for cloud_vm deployment
    if deployment_type == "cloud_vm":
        config["stack"][0]["experiment_tracking"]["params"].update(
            {
                "vm_name": f"{name}-mlflow-vm",
                "machine_type": "e2-medium",
                "disk_size_gb": 20,
                "mlflow_port": 5000,
            }
        )

    # Write configuration to file
    config_filename = f"{name}.yaml"
    import yaml

    with open(config_filename, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    typer.secho(
        f"\n✅ Configuration saved to: {config_filename}", fg=typer.colors.GREEN
    )
    typer.echo(f"\nTo deploy this configuration, run:")
    typer.secho(
        f"  deployml deploy --config-path {config_filename}",
        fg=typer.colors.BRIGHT_BLUE,
    )


@cli.command()
def terraform(
    action: str,
    stack_config_path: str = typer.Option(
        ..., "--stack-config-path", help="Path to stack configuration YAML"
    ),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir", help="Output directory for Terraform files"
    ),
):
    """
    Run Terraform actions (plan, apply, destroy) for the specified stack configuration.
    """
    print(action)
    if action not in ["plan", "apply", "destroy"]:
        typer.secho(
            f"❌ Invalid action: {action}. Use: plan, apply, destroy",
            fg=typer.colors.RED,
        )

    config_path = Path(stack_config_path)

    print(config_path)
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

    except Exception as e:
        typer.secho(
            f"❌ Failed to load configuration: {e}", fg=typer.colors.RED
        )

    if not output_dir:
        output_dir = Path.cwd() / ".deployml" / "terraform" / config["name"]
    else:
        output_dir = Path(output_dir)


@cli.command()
def deploy(
    config_path: Path = typer.Option(
        ..., "--config-path", "-c", help="Path to YAML config file"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompts and deploy"
    ),
):
    """
    Deploy infrastructure based on a YAML configuration file.
    """
    if not config_path.exists():
        typer.echo(f"❌ Config file not found: {config_path}")
        raise typer.Exit(code=1)

    config = yaml.safe_load(config_path.read_text())

    # --- GCS bucket existence and unique name logic ---
    cloud = config["provider"]["name"]
    if cloud == "gcp":
        project_id = config["provider"]["project_id"]
        # Only run if google-cloud-storage is available
        # Simplified bucket logic - respect user settings
        for stage in config.get("stack", []):
            for stage_name, tool in stage.items():
                if stage_name == "artifact_tracking" and tool.get("name") in [
                    "mlflow",
                    "wandb",
                ]:
                    if "params" not in tool:
                        tool["params"] = {}

                    # If no bucket specified, generate one
                    if not tool["params"].get("artifact_bucket"):
                        new_bucket = generate_bucket_name(project_id)
                        typer.echo(
                            f"📦 No bucket specified for artifact_tracking, using generated bucket name: {new_bucket}"
                        )
                        tool["params"]["artifact_bucket"] = new_bucket
                        # Set create_artifact_bucket to True for generated buckets
                        if "create_artifact_bucket" not in tool["params"]:
                            tool["params"]["create_artifact_bucket"] = True

                    # Set use_postgres param based on backend_store_uri (mlflow only)
                    if tool.get("name") == "mlflow":
                        backend_uri = tool["params"].get(
                            "backend_store_uri", ""
                        )
                        tool["params"]["use_postgres"] = backend_uri.startswith(
                            "postgresql"
                        )

    workspace_name = config.get("name") or "development"

    DEPLOYML_DIR = Path.cwd() / ".deployml" / workspace_name
    DEPLOYML_TERRAFORM_DIR = DEPLOYML_DIR / "terraform"
    DEPLOYML_MODULES_DIR = DEPLOYML_DIR / "terraform" / "modules"

    typer.echo(f"📁 Using workspace: {workspace_name}")
    typer.echo(f"📍 Workspace path: {DEPLOYML_DIR}")

    DEPLOYML_TERRAFORM_DIR.mkdir(parents=True, exist_ok=True)
    DEPLOYML_MODULES_DIR.mkdir(parents=True, exist_ok=True)

    region = config["provider"]["region"]
    deployment_type = config["deployment"]["type"]
    stack = config["stack"]

    # --- PATCH: Ensure cloud_sql_postgres module is copied for mlflow cloud_run with postgres ---
    if (
        cloud == "gcp"
        and deployment_type == "cloud_run"
        and any(
            tool.get("name") == "mlflow"
            and tool.get("params", {})
            .get("backend_store_uri", "")
            .startswith("postgresql")
            for stage in stack
            for tool in stage.values()
        )
    ):
        # Only add if not already present
        if not any(
            tool.get("name") == "cloud_sql_postgres"
            for stage in stack
            for tool in stage.values()
        ):
            stack.append(
                {
                    "cloud_sql_postgres": {
                        "name": "cloud_sql_postgres",
                        "params": {},
                    }
                }
            )

    typer.echo("📦 Copying module templates...")
    copy_modules_to_workspace(
        DEPLOYML_MODULES_DIR,
        stack=stack,
        deployment_type=deployment_type,
        cloud=cloud,
    )
    # --- UNIFIED BUCKET CONFIGURATION APPROACH ---
    # Collect all bucket configurations in a structured way (similar to VM creation)
    bucket_configs = []
    for stage in stack:
        for stage_name, tool in stage.items():
            if tool.get("params", {}).get("artifact_bucket"):
                bucket_name = tool["params"]["artifact_bucket"]
                create_bucket = tool["params"].get(
                    "create_artifact_bucket", True
                )

                # Check if bucket already exists
                bucket_exists_flag = bucket_exists(bucket_name, project_id)

                bucket_configs.append(
                    {
                        "stage": stage_name,
                        "tool": tool["name"],
                        "bucket_name": bucket_name,
                        "create": create_bucket,
                        "exists": bucket_exists_flag,
                    }
                )

                typer.echo(
                    f"📦 Bucket config: {stage_name}/{tool['name']} -> {bucket_name} (create: {create_bucket}, exists: {bucket_exists_flag})"
                )

    # Simple boolean flag for backward compatibility
    create_artifact_bucket = any(config["create"] for config in bucket_configs)

    typer.echo(f"🔧 Unified bucket creation: {create_artifact_bucket}")

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    # PATCH: Use wandb_main.tf.j2 or mlflow_main.tf.j2 for cloud_run if present
    if deployment_type == "cloud_run":
        if any(
            tool.get("name") == "wandb"
            for stage in stack
            for tool in stage.values()
        ):
            main_template = env.get_template(
                f"{cloud}/{deployment_type}/wandb_main.tf.j2"
            )
        elif any(
            tool.get("name") == "mlflow"
            for stage in stack
            for tool in stage.values()
        ):
            main_template = env.get_template(
                f"{cloud}/{deployment_type}/mlflow_main.tf.j2"
            )
        else:
            main_template = env.get_template(
                f"{cloud}/{deployment_type}/main.tf.j2"
            )
    else:
        main_template = env.get_template(
            f"{cloud}/{deployment_type}/main.tf.j2"
        )
    var_template = env.get_template(
        f"{cloud}/{deployment_type}/variables.tf.j2"
    )
    tfvars_template = env.get_template(
        f"{cloud}/{deployment_type}/terraform.tfvars.j2"
    )

    # Compute a stable short hash for resource names to avoid collisions
    name_material = f"{workspace_name}:{project_id}".encode("utf-8")
    name_hash = hashlib.sha1(name_material).hexdigest()[:6]

    # Handle teardown configuration
    teardown_config = config.get("teardown", {})
    teardown_enabled = teardown_config.get("enabled", False)
    teardown_cron_schedule = ""
    teardown_scheduled_timestamp = 0
    
    if teardown_enabled:
        duration_hours = teardown_config.get("duration_hours", 24)
        deployed_at = datetime.utcnow()
        teardown_at = deployed_at + timedelta(hours=duration_hours)
        teardown_scheduled_timestamp = int(teardown_at.timestamp())
        teardown_cron_schedule = calculate_cron_from_timestamp(teardown_scheduled_timestamp)

    # Render templates
    if deployment_type == "cloud_vm":
        main_tf = main_template.render(
            cloud=cloud,
            stack=stack,
            deployment_type=deployment_type,
            create_artifact_bucket=create_artifact_bucket,
            bucket_configs=bucket_configs,  # ← Pass structured bucket configs
            project_id=project_id,
            region=region,
            zone=config["provider"].get("zone", f"{region}-a"),
            stack_name=workspace_name,
            name_hash=name_hash,
            teardown_config=teardown_config if teardown_enabled else None,
            teardown_cron_schedule=teardown_cron_schedule,
            teardown_scheduled_timestamp=teardown_scheduled_timestamp,
        )
    else:
        main_tf = main_template.render(
            cloud=cloud,
            stack=stack,
            deployment_type=deployment_type,
            create_artifact_bucket=create_artifact_bucket,
            bucket_configs=bucket_configs,  # ← Pass structured bucket configs
            project_id=project_id,
            stack_name=workspace_name,
            name_hash=name_hash,
            teardown_config=teardown_config if teardown_enabled else None,
            teardown_cron_schedule=teardown_cron_schedule,
            teardown_scheduled_timestamp=teardown_scheduled_timestamp,
        )
    variables_tf = var_template.render(
        stack=stack,
        cloud=cloud,
        project_id=project_id,
        stack_name=workspace_name,
        name_hash=name_hash,
    )
    tfvars_content = tfvars_template.render(
        project_id=project_id,
        region=region,
        zone=config["provider"].get("zone", f"{region}-a"),  # Add zone for VM
        stack=stack,
        cloud=cloud,
        create_artifact_bucket=create_artifact_bucket,
        stack_name=workspace_name,
        name_hash=name_hash,
    )

    # Write files
    (DEPLOYML_TERRAFORM_DIR / "main.tf").write_text(main_tf)
    (DEPLOYML_TERRAFORM_DIR / "variables.tf").write_text(variables_tf)
    (DEPLOYML_TERRAFORM_DIR / "terraform.tfvars").write_text(tfvars_content)

    # Deploy
    typer.echo(f"🚀 Deploying {config['name']} to {cloud}...")

    if not check_gcp_auth():
        typer.echo("🔐 Authenticating with GCP...")
        subprocess.run(
            ["gcloud", "auth", "application-default", "login"],
            cwd=DEPLOYML_TERRAFORM_DIR,
        )

    subprocess.run(
        ["gcloud", "config", "set", "project", project_id],
        cwd=DEPLOYML_TERRAFORM_DIR,
    )

    typer.echo("📋 Initializing Terraform...")
    # Suppress output of terraform init
    subprocess.run(
        ["terraform", "init"],
        cwd=DEPLOYML_TERRAFORM_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    typer.echo("📊 Planning deployment...")
    result = subprocess.run(
        ["terraform", "plan"],
        cwd=DEPLOYML_TERRAFORM_DIR,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        typer.echo(f"❌ Terraform plan failed: {result.stderr}")
        raise typer.Exit(code=1)

    # Run cost analysis after successful terraform plan
    # Check for cost analysis configuration
    cost_config = config.get("cost_analysis", {})
    cost_enabled = cost_config.get("enabled", True)  # Default: enabled
    warning_threshold = cost_config.get(
        "warning_threshold", 100.0
    )  # Default: $100

    cost_analysis = None
    if cost_enabled:
        usage_file_path = cost_config.get("usage_file")
        usage_file = Path(usage_file_path) if usage_file_path else None

        # If no explicit usage file provided, generate one from high-level YAML values
        if usage_file is None:
            try:
                bucket_amount = cost_config.get("bucket_amount")
                cloudsql_amount = cost_config.get(
                    "cloudSQL_amount"
                ) or cost_config.get("cloudsql_amount")
                bigquery_amount = cost_config.get(
                    "bigQuery_amount"
                ) or cost_config.get("bigquery_amount")

                resource_type_default_usage = {}
                # Map high-level amounts to Infracost resource defaults
                if bucket_amount is not None:
                    resource_type_default_usage["google_storage_bucket"] = {
                        "storage_gb": float(bucket_amount)
                    }
                if cloudsql_amount is not None:
                    resource_type_default_usage[
                        "google_sql_database_instance"
                    ] = {"storage_gb": float(cloudsql_amount)}
                if bigquery_amount is not None:
                    resource_type_default_usage["google_bigquery_table"] = {
                        "storage_gb": float(bigquery_amount)
                    }

                if resource_type_default_usage:
                    usage_yaml = {
                        "version": "0.1",
                        "resource_type_default_usage": resource_type_default_usage,
                    }
                    usage_file = DEPLOYML_TERRAFORM_DIR / "infracost-usage.yml"
                    with open(usage_file, "w") as f:
                        yaml.safe_dump(usage_yaml, f, sort_keys=False)
            except Exception:
                # If usage-file generation fails, continue without it
                usage_file = None

        cost_analysis = run_infracost_analysis(
            DEPLOYML_TERRAFORM_DIR, warning_threshold, usage_file=usage_file
        )

    # Format confirmation message with cost information
    if cost_analysis:
        cost_msg = format_cost_for_confirmation(
            cost_analysis.total_monthly_cost, cost_analysis.currency
        )
        confirmation_msg = f"🚀 Deploy stack? {cost_msg}"
    else:
        confirmation_msg = "🚀 Do you want to deploy the stack?"

    if yes or typer.confirm(confirmation_msg):
        estimated_time = estimate_terraform_time(result.stdout, "apply")
        typer.echo(f"🏗️ Applying changes... (Estimated time: {estimated_time})")
        # Suppress output of terraform init
        subprocess.run(
            ["terraform", "init"],
            cwd=DEPLOYML_TERRAFORM_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Parse estimated minutes from string (e.g., '~20 minutes ...')
        import re as _re

        match = _re.search(r"~(\d+)", estimated_time)
        minutes = (
            int(match.group(1)) if match else 8
        )  # Increased default for API operations
        result_code = run_terraform_with_loading_bar(
            ["terraform", "apply", "-auto-approve"],
            DEPLOYML_TERRAFORM_DIR,
            minutes,
        )
        if result_code == 0 or result_code == 1:
            typer.echo("✅ Deployment complete!")
            
            # Handle auto-teardown metadata
            if teardown_enabled:
                duration_hours = teardown_config.get("duration_hours", 24)
                deployed_at = datetime.utcnow()
                teardown_at = deployed_at + timedelta(hours=duration_hours)
                
                metadata = {
                    "deployed_at": deployed_at.isoformat(),
                    "teardown_scheduled_at": teardown_at.isoformat(),
                    "teardown_enabled": True,
                    "duration_hours": duration_hours,
                    "scheduler_job_name": f"deployml-teardown-{workspace_name}"
                }
                save_deployment_metadata(DEPLOYML_DIR, metadata)
                
                typer.echo(f"\n⏰ Auto-teardown scheduled for: {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                typer.echo(f"   (in {duration_hours} hours)")
                typer.echo(f"   To cancel: deployml teardown cancel --config-path {config_path}")
            
            # Show all Terraform outputs in a user-friendly way
            output_proc = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=DEPLOYML_TERRAFORM_DIR,
                capture_output=True,
                text=True,
            )
            if output_proc.returncode == 0:
                try:
                    outputs = json.loads(output_proc.stdout)
                    if outputs:
                        typer.echo("\n📦 DeployML Outputs:")
                        for key, value in outputs.items():
                            is_sensitive = value.get("sensitive", False)
                            output_type = value.get("type")
                            output_val = value.get("value")
                            if is_sensitive:
                                typer.secho(
                                    f"  {key}: [SENSITIVE] (value hidden)",
                                    fg=typer.colors.YELLOW,
                                )
                            elif isinstance(output_val, dict):
                                typer.echo(f"  {key}:")
                                for subkey, subval in output_val.items():
                                    if isinstance(subval, str) and (
                                        subval.startswith("http://")
                                        or subval.startswith("https://")
                                    ):
                                        typer.secho(
                                            f"    {subkey}: {subval}",
                                            fg=typer.colors.BRIGHT_BLUE,
                                            bold=True,
                                        )
                                    elif (
                                        isinstance(subval, str) and subval == ""
                                    ):
                                        typer.secho(
                                            f"    {subkey}: [No value] (likely using SQLite or not applicable)",
                                            fg=typer.colors.YELLOW,
                                        )
                                    else:
                                        typer.echo(f"    {subkey}: {subval}")
                            elif isinstance(output_val, list):
                                typer.echo(f"  {key}: {output_val}")
                            elif isinstance(output_val, str):
                                if output_val.startswith(
                                    "http://"
                                ) or output_val.startswith("https://"):
                                    typer.secho(
                                        f"  {key}: {output_val}",
                                        fg=typer.colors.BRIGHT_BLUE,
                                        bold=True,
                                    )
                                elif output_val == "":
                                    typer.secho(
                                        f"  {key}: [No value] (likely using SQLite or not applicable)",
                                        fg=typer.colors.YELLOW,
                                    )
                                else:
                                    typer.echo(f"  {key}: {output_val}")
                            else:
                                typer.echo(f"  {key}: {output_val}")
                    else:
                        typer.echo("No outputs found in Terraform state.")
                except Exception as e:
                    typer.echo(f"⚠️ Failed to parse Terraform outputs: {e}")
            else:
                typer.echo("⚠️ Could not retrieve Terraform outputs.")
        else:
            typer.echo("❌ Terraform apply failed")
            raise typer.Exit(code=1)
    else:
        typer.echo("❌ Deployment cancelled")


@cli.command()
def destroy(
    config_path: Path = typer.Option(
        ..., "--config-path", "-c", help="Path to YAML config file"
    ),
    workspace: Optional[str] = typer.Option(
        None, "--workspace", help="Override workspace name from config"
    ),
    clean_workspace: bool = typer.Option(
        False, "--clean-workspace", help="Remove entire workspace after destroy"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompts and destroy"
    ),
):
    """
    Destroy infrastructure and optionally clean up workspace and Terraform state files.
    """
    if not config_path.exists():
        typer.echo(f"❌ Config file not found: {config_path}")
        raise typer.Exit(code=1)

    config = yaml.safe_load(config_path.read_text())

    # Determine workspace name (same logic as deploy)
    workspace_name = config.get("name") or "default"

    # Find the workspace
    DEPLOYML_DIR = Path.cwd() / ".deployml" / workspace_name
    DEPLOYML_TERRAFORM_DIR = DEPLOYML_DIR / "terraform"
    DEPLOYML_MODULES_DIR = DEPLOYML_DIR / "terraform" / "modules"

    if not DEPLOYML_TERRAFORM_DIR.exists():
        typer.echo(f"⚠️ No workspace found for {workspace_name}")
        typer.echo(
            "Nothing to destroy - infrastructure may already be cleaned up."
        )
        return

    # Extract project info
    cloud = config["provider"]["name"]
    if cloud == "gcp":
        project_id = config["provider"]["project_id"]

    # Confirmation unless auto-approve

    typer.echo(f"\n⚠️  About to DESTROY infrastructure for: {workspace_name}")
    typer.echo(f"📁 Workspace: {DEPLOYML_DIR}")
    typer.echo(f"🌐 Project: {project_id}")
    typer.echo("This will permanently delete all resources!")

    if not (
        yes or typer.confirm("Are you sure you want to destroy all resources?")
    ):
        typer.echo("❌ Destroy cancelled")
        return

    try:
        typer.echo(f"💥 Destroying infrastructure...")

        # Set GCP project
        subprocess.run(
            ["gcloud", "config", "set", "project", project_id],
            cwd=DEPLOYML_TERRAFORM_DIR,
        )

        # Check if we have Cloud SQL resources and clean them up first
        plan_result = subprocess.run(
            ["terraform", "plan", "-destroy"],
            cwd=DEPLOYML_TERRAFORM_DIR,
            capture_output=True,
            text=True,
        )

        if "google_sql_database_instance" in plan_result.stdout:
            cleanup_cloud_sql_resources(DEPLOYML_TERRAFORM_DIR, project_id)

        # Build destroy command
        cmd = ["terraform", "destroy", "--auto-approve"]

        # Run destroy
        result = subprocess.run(cmd, cwd=DEPLOYML_TERRAFORM_DIR, check=False)

        if result.returncode == 0:
            typer.echo("✅ Infrastructure destroyed successfully!")

            if clean_workspace:
                typer.echo("🧹 Cleaning workspace...")
                shutil.rmtree(DEPLOYML_DIR)
                typer.echo("✅ Workspace cleaned")
            elif typer.confirm("Clean up Terraform state files?"):
                cleanup_terraform_files(DEPLOYML_TERRAFORM_DIR)
        else:
            typer.echo(f"❌ Destroy failed: {result.stderr}")
            raise typer.Exit(code=1)

    except Exception as e:
        typer.echo(f"❌ Error during destroy: {e}")
        raise typer.Exit(code=1)


@cli.command()
def status():
    """
    Check the deployment status of the current workspace.
    """
    typer.echo("Checking deployment status...")


@cli.command()
def teardown(
    action: str = typer.Argument(..., help="Action: cancel, status, or schedule"),
    config_path: Path = typer.Option(
        ..., "--config-path", "-c", help="Path to YAML config file"
    ),
):
    """
    Manage auto-teardown: cancel scheduled teardown, check status, or schedule new teardown.
    """
    if not config_path.exists():
        typer.echo(f"❌ Config file not found: {config_path}")
        raise typer.Exit(code=1)
    
    config = yaml.safe_load(config_path.read_text())
    workspace_name = config.get("name") or "default"
    DEPLOYML_DIR = Path.cwd() / ".deployml" / workspace_name
    
    if action == "cancel":
        cancel_teardown(config, DEPLOYML_DIR, workspace_name)
    elif action == "status":
        show_teardown_status(DEPLOYML_DIR, workspace_name)
    elif action == "schedule":
        schedule_teardown(config, DEPLOYML_DIR, workspace_name)
    else:
        typer.echo(f"❌ Unknown action: {action}. Use: cancel, status, or schedule")
        raise typer.Exit(code=1)


def cancel_teardown(config: dict, deployml_dir: Path, workspace_name: str):
    """Cancel scheduled teardown."""
    project_id = config["provider"]["project_id"]
    region = config["provider"]["region"]
    
    # Delete Cloud Scheduler job
    scheduler_job_name = f"deployml-teardown-{workspace_name}"
    result = subprocess.run(
        ["gcloud", "scheduler", "jobs", "delete", scheduler_job_name,
         "--project", project_id, "--region", region, "--quiet"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode == 0:
        typer.echo("✅ Scheduled teardown cancelled")
        # Update metadata
        metadata = load_deployment_metadata(deployml_dir)
        if metadata:
            metadata["teardown_enabled"] = False
            save_deployment_metadata(deployml_dir, metadata)
    else:
        typer.echo(f"⚠️ Could not cancel teardown: {result.stderr}")
        typer.echo("   The scheduler job may not exist or may have already been deleted.")


def show_teardown_status(deployml_dir: Path, workspace_name: str):
    """Show teardown status."""
    metadata = load_deployment_metadata(deployml_dir)
    
    if not metadata or not metadata.get("teardown_enabled"):
        typer.echo("ℹ️ Auto-teardown is not enabled for this workspace")
        return
    
    deployed_at = datetime.fromisoformat(metadata["deployed_at"])
    teardown_at = datetime.fromisoformat(metadata["teardown_scheduled_at"])
    now = datetime.utcnow()
    
    if now >= teardown_at:
        typer.echo("⚠️ Teardown time has passed (may have already executed)")
    else:
        time_remaining = teardown_at - now
        hours = int(time_remaining.total_seconds() // 3600)
        minutes = int((time_remaining.total_seconds() % 3600) // 60)
        typer.echo(f"⏰ Scheduled teardown: {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        typer.echo(f"   Time remaining: {hours}h {minutes}m")
        typer.echo(f"   To cancel: deployml teardown cancel --config-path <config-file>")


def schedule_teardown(config: dict, deployml_dir: Path, workspace_name: str):
    """Schedule a new teardown."""
    duration_hours = typer.prompt("Hours until teardown", default=24, type=int)
    deployed_at = datetime.utcnow()
    teardown_at = deployed_at + timedelta(hours=duration_hours)
    
    metadata = {
        "deployed_at": deployed_at.isoformat(),
        "teardown_scheduled_at": teardown_at.isoformat(),
        "teardown_enabled": True,
        "duration_hours": duration_hours
    }
    save_deployment_metadata(deployml_dir, metadata)
    
    typer.echo(f"✅ Teardown scheduled for: {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    typer.echo("⚠️ Note: This only updates local metadata. To actually schedule teardown,")
    typer.echo("   you need to redeploy with teardown.enabled: true in your config.")


@cli.command()
def init(
    provider: str = typer.Option(
        ..., "--provider", "-p", help="Cloud provider: gcp, aws, or azure"
    ),
    project_id: str = typer.Option(
        "", "--project-id", "-j", help="Project ID (for GCP)"
    ),
):
    """
    Initialize cloud project by enabling required APIs/services before deployment.
    """
    if provider == "gcp":
        if not project_id:
            typer.echo("❌ --project-id is required for GCP.")
            raise typer.Exit(code=1)
        typer.echo(
            f"🔑 Enabling required GCP APIs for project: {project_id} ..."
        )
        result = subprocess.run(
            [
                "gcloud",
                "services",
                "enable",
                *REQUIRED_GCP_APIS,
                "--project",
                project_id,
            ]
        )
        if result.returncode == 0:
            typer.echo("✅ All required GCP APIs are enabled.")
        else:
            typer.echo("❌ Failed to enable one or more GCP APIs.")
            raise typer.Exit(code=1)
    elif provider == "aws":
        typer.echo(
            "No API enablement required for AWS. Ensure IAM permissions are set."
        )
    elif provider == "azure":
        typer.echo(
            "No API enablement required for most Azure services. Register providers if needed."
        )
    else:
        typer.echo(f"❌ Unknown provider: {provider}")
        raise typer.Exit(code=1)


def main():
    """
    Entry point for the DeployML CLI.
    """
    cli()


if __name__ == "__main__":
    main()
