import sys
import yaml
import typer
import shutil
import subprocess
import re
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
from deployml.utils.kubernetes_local import (
    start_minikube,
    generate_fastapi_manifests,
    deploy_fastapi_to_minikube,
    generate_mlflow_manifests,
    deploy_mlflow_to_minikube,
    check_minikube_running
)
from deployml.utils.kubernetes_gke import (
    generate_mlflow_manifests_gke,
    generate_fastapi_manifests_gke,
    deploy_to_gke,
    connect_to_gke_cluster,
)


def upload_terraform_files_to_gcs(terraform_dir: Path, project_id: str, workspace_name: str):
    """
    Upload Terraform files to GCS bucket for Cloud Build teardown.
    Gets bucket name from Terraform state.
    """
    try:
        # Get terraform files bucket from Terraform state
        # The bucket is created by the teardown module
        state_proc = subprocess.run(
            ["terraform", "state", "list"],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
        )
        
        if state_proc.returncode != 0:
            typer.echo(f"⚠️  Could not read Terraform state: {state_proc.stderr}")
            return
        
        # Find the terraform_files bucket resource
        bucket_resource = None
        for line in state_proc.stdout.split('\n'):
            if 'module.teardown.google_storage_bucket.terraform_files' in line:
                bucket_resource = line.strip()
                break
        
        if not bucket_resource:
            typer.echo("⚠️  Teardown module bucket not found in state. Skipping upload.")
            return
        
        # Get bucket name from state
        show_proc = subprocess.run(
            ["terraform", "state", "show", bucket_resource],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
        )
        
        if show_proc.returncode != 0:
            typer.echo(f"⚠️  Could not get bucket name: {show_proc.stderr}")
            return
        
        # Extract bucket name from terraform state show output
        bucket_name = None
        for line in show_proc.stdout.split('\n'):
            if 'name' in line and '=' in line:
                bucket_name = line.split('=')[1].strip().strip('"')
                break
        
        if not bucket_name:
            typer.echo("⚠️  Could not extract bucket name from state.")
            return
        
        # Upload Terraform files
        storage_client = storage.Client(project=project_id)
        bucket = storage_client.bucket(bucket_name)
        
        # Upload all .tf files, .tfvars, and state files
        terraform_files = list(terraform_dir.glob("*.tf")) + list(terraform_dir.glob("*.tfvars"))
        terraform_files += list(terraform_dir.glob("terraform.tfstate*"))  # Include state files
        terraform_files += list((terraform_dir / "modules").rglob("*.tf")) if (terraform_dir / "modules").exists() else []
        
        uploaded_count = 0
        for tf_file in terraform_files:
            if tf_file.is_file():
                # Create relative path from terraform_dir
                relative_path = tf_file.relative_to(terraform_dir)
                blob_path = f"{workspace_name}/terraform/{relative_path}"
                
                blob = bucket.blob(blob_path)
                blob.upload_from_filename(str(tf_file))
                uploaded_count += 1
        
        typer.echo(f"✅ Uploaded {uploaded_count} Terraform files to gs://{bucket_name}/{workspace_name}/terraform/")
        
    except Exception as e:
        typer.echo(f"⚠️  Error uploading Terraform files: {e}")
        import traceback
        typer.echo(traceback.format_exc())


def extract_resource_manifest(terraform_dir: Path, project_id: str, workspace_name: str, region: str) -> dict:
    """
    Extract resource details from Terraform outputs and state.
    Returns a manifest dictionary with all resources that need to be deleted.
    """
    import json
    import subprocess
    from urllib.parse import urlparse
    
    manifest = {
        "workspace_name": workspace_name,
        "project_id": project_id,
        "region": region,
        "resources": {
            "cloud_run_services": [],
            "cloud_run_jobs": [],
            "cloud_sql_instances": [],
            "storage_buckets": [],
            "cloud_scheduler_jobs": [],
            "pubsub_topics": [],
            "secret_manager_secrets": [],
            "service_accounts": [],
            "cloud_build_triggers": [],
        }
    }
    
    # Get Terraform outputs
    output_proc = subprocess.run(
        ["terraform", "output", "-json"],
        cwd=terraform_dir,
        capture_output=True,
        text=True,
    )
    
    if output_proc.returncode == 0:
        outputs = json.loads(output_proc.stdout)
        
        # Extract Cloud Run service names from URLs
        for key, value in outputs.items():
            output_val = value.get('value', '')
            
            # Cloud Run services - we'll extract from Terraform state instead of URLs
            # (URLs contain hash suffixes that don't match actual service names)
            pass  # Skip URL parsing, will get from state below
            
            # Storage buckets
            if '_bucket' in key and output_val:
                if isinstance(output_val, str) and output_val:
                    manifest["resources"]["storage_buckets"].append({
                        "name": output_val
                    })
            
            # Cloud SQL instance connection name
            if 'instance_connection_name' in key and output_val:
                # Format: project:region:instance
                parts = str(output_val).split(':')
                if len(parts) == 3:
                    manifest["resources"]["cloud_sql_instances"].append({
                        "name": parts[2],
                        "region": parts[1]
                    })
    
    # Query Terraform state for additional resources
    state_proc = subprocess.run(
        ["terraform", "state", "list"],
        cwd=terraform_dir,
        capture_output=True,
        text=True,
    )
    
    if state_proc.returncode == 0:
        state_resources = [r.strip() for r in state_proc.stdout.strip().split('\n') if r.strip()]
        
        for resource in state_resources:
            try:
                # Cloud Run services (v1 and v2)
                if 'google_cloud_run_service' in resource and 'google_cloud_run_v2_job' not in resource:
                    show_proc = subprocess.run(
                        ["terraform", "state", "show", resource],
                        cwd=terraform_dir,
                        capture_output=True,
                        text=True,
                    )
                    if show_proc.returncode == 0:
                        service_name = None
                        service_region = region
                        for line in show_proc.stdout.split('\n'):
                            # Strip ANSI escape codes
                            clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
                            # Check for name field (but not location, id, or other fields)
                            if (clean_line.strip().startswith('name') or ' = name' in clean_line.lower()) and '=' in clean_line and 'location' not in clean_line.lower() and 'id' not in clean_line.lower() and 'latest' not in clean_line.lower():
                                parts = clean_line.split('=')
                                if len(parts) >= 2:
                                    potential_name = parts[1].strip().strip('"').strip("'")
                                    # Remove ANSI codes from the name itself
                                    potential_name = re.sub(r'\x1b\[[0-9;]*m', '', potential_name)
                                    # Skip null, empty, or invalid values
                                    if potential_name and potential_name.lower() != 'null' and '/' not in potential_name and '@' not in potential_name and len(potential_name) < 200:
                                        service_name = potential_name
                                        break
                            # Check for location or region field
                            elif (clean_line.strip().startswith('location') or clean_line.strip().startswith('region')) and '=' in clean_line:
                                parts = clean_line.split('=')
                                if len(parts) >= 2:
                                    service_region = parts[1].strip().strip('"').strip("'")
                                    service_region = re.sub(r'\x1b\[[0-9;]*m', '', service_region)
                        if service_name:
                            manifest["resources"]["cloud_run_services"].append({
                                "name": service_name,
                                "region": service_region
                            })
                
                # Cloud Run Jobs
                elif 'google_cloud_run_v2_job' in resource:
                    show_proc = subprocess.run(
                        ["terraform", "state", "show", resource],
                        cwd=terraform_dir,
                        capture_output=True,
                        text=True,
                    )
                    if show_proc.returncode == 0:
                        for line in show_proc.stdout.split('\n'):
                            if 'name' in line.lower() and '=' in line and 'location' not in line.lower():
                                job_name = line.split('=')[1].strip().strip('"').strip("'")
                                if job_name:
                                    manifest["resources"]["cloud_run_jobs"].append({
                                        "name": job_name,
                                        "region": region
                                    })
                                    break
                
                # Cloud Scheduler jobs
                elif 'google_cloud_scheduler_job' in resource:
                    show_proc = subprocess.run(
                        ["terraform", "state", "show", resource],
                        cwd=terraform_dir,
                        capture_output=True,
                        text=True,
                    )
                    if show_proc.returncode == 0:
                        job_name = None
                        job_region = region
                        for line in show_proc.stdout.split('\n'):
                            if 'name' in line.lower() and '=' in line and 'location' not in line.lower():
                                job_name = line.split('=')[1].strip().strip('"').strip("'")
                                # Extract job name from URL if it's a full URL
                                if job_name and '/jobs/' in job_name:
                                    job_name = job_name.split('/jobs/')[-1].split(':')[0].split('/')[-1]
                            elif 'region' in line.lower() and '=' in line:
                                job_region = line.split('=')[1].strip().strip('"').strip("'")
                        if job_name:
                            manifest["resources"]["cloud_scheduler_jobs"].append({
                                "name": job_name,
                                "region": job_region
                            })
                
                # Pub/Sub topics
                elif 'google_pubsub_topic' in resource:
                    show_proc = subprocess.run(
                        ["terraform", "state", "show", resource],
                        cwd=terraform_dir,
                        capture_output=True,
                        text=True,
                    )
                    if show_proc.returncode == 0:
                        for line in show_proc.stdout.split('\n'):
                            if 'name' in line.lower() and '=' in line:
                                topic_name = line.split('=')[1].strip().strip('"').strip("'")
                                if topic_name:
                                    manifest["resources"]["pubsub_topics"].append({
                                        "name": topic_name
                                    })
                                    break
                
                # Secret Manager secrets
                elif 'google_secret_manager_secret' in resource:
                    show_proc = subprocess.run(
                        ["terraform", "state", "show", resource],
                        cwd=terraform_dir,
                        capture_output=True,
                        text=True,
                    )
                    if show_proc.returncode == 0:
                        for line in show_proc.stdout.split('\n'):
                            if 'secret_id' in line.lower() and '=' in line:
                                secret_name = line.split('=')[1].strip().strip('"').strip("'")
                                if secret_name:
                                    manifest["resources"]["secret_manager_secrets"].append({
                                        "name": secret_name
                                    })
                                    break
                
                # Service accounts (only teardown ones to avoid deleting user SAs)
                elif 'google_service_account' in resource and 'teardown' in resource:
                    show_proc = subprocess.run(
                        ["terraform", "state", "show", resource],
                        cwd=terraform_dir,
                        capture_output=True,
                        text=True,
                    )
                    if show_proc.returncode == 0:
                        for line in show_proc.stdout.split('\n'):
                            if 'email' in line.lower() and '@' in line and '=' in line:
                                sa_email = line.split('=')[1].strip().strip('"').strip("'")
                                if sa_email:
                                    manifest["resources"]["service_accounts"].append({
                                        "email": sa_email
                                    })
                                    break
                
                # Cloud Build triggers
                elif 'google_cloudbuild_trigger' in resource:
                    show_proc = subprocess.run(
                        ["terraform", "state", "show", resource],
                        cwd=terraform_dir,
                        capture_output=True,
                        text=True,
                    )
                    if show_proc.returncode == 0:
                        for line in show_proc.stdout.split('\n'):
                            if 'name' in line.lower() and '=' in line:
                                trigger_name = line.split('=')[1].strip().strip('"').strip("'")
                                if trigger_name:
                                    manifest["resources"]["cloud_build_triggers"].append({
                                        "name": trigger_name
                                    })
                                    break
            except Exception as e:
                # Skip resources that can't be parsed
                continue
    
    # Remove duplicates
    for resource_type in manifest["resources"]:
        seen = set()
        unique_resources = []
        for res in manifest["resources"][resource_type]:
            if resource_type in ["cloud_run_services", "cloud_run_jobs", "cloud_sql_instances", "cloud_scheduler_jobs"]:
                key = (res.get("name"), res.get("region"))
            elif resource_type == "service_accounts":
                key = res.get("email")
            else:
                key = res.get("name")
            
            if key and key not in seen:
                seen.add(key)
                unique_resources.append(res)
        manifest["resources"][resource_type] = unique_resources
    
    return manifest


def upload_resource_manifest(manifest: dict, terraform_dir: Path, project_id: str, workspace_name: str):
    """Upload resource manifest to GCS bucket."""
    import json
    
    try:
        # Get bucket name from Terraform state (same logic as upload_terraform_files_to_gcs)
        state_proc = subprocess.run(
            ["terraform", "state", "list"],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
        )
        
        if state_proc.returncode != 0:
            raise Exception(f"Could not read Terraform state: {state_proc.stderr}")
        
        bucket_resource = None
        for line in state_proc.stdout.split('\n'):
            if 'module.teardown.google_storage_bucket.terraform_files' in line:
                bucket_resource = line.strip()
                break
        
        if not bucket_resource:
            raise Exception("Teardown module bucket not found in state")
        
        show_proc = subprocess.run(
            ["terraform", "state", "show", bucket_resource],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
        )
        
        if show_proc.returncode != 0:
            raise Exception(f"Could not get bucket name: {show_proc.stderr}")
        
        bucket_name = None
        for line in show_proc.stdout.split('\n'):
            if 'name' in line and '=' in line:
                bucket_name = line.split('=')[1].strip().strip('"')
                break
        
        if not bucket_name:
            raise Exception("Could not extract bucket name from state")
        
        # Upload manifest
        storage_client = storage.Client(project=project_id)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(f"{workspace_name}/resource-manifest.json")
        blob.upload_from_string(json.dumps(manifest, indent=2))
        
        typer.echo(f"✅ Resource manifest uploaded to gs://{bucket_name}/{workspace_name}/resource-manifest.json")
        
    except Exception as e:
        typer.echo(f"⚠️  Error uploading resource manifest: {e}")
        raise

import re
import time
import json
from datetime import datetime, timedelta

def get_version():
    """Get version from package metadata"""
    try:
        from importlib.metadata import version
        return version("deployml-core")
    except Exception:
        return "version unknown"

cli = typer.Typer(invoke_without_command=True)

@cli.callback()
def cli_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit"),
):
    """DeployML CLI - Infrastructure for academia with cost analysis"""
    if version:
        typer.echo(f"deployml {get_version()}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        # No command provided, show help
        typer.echo(ctx.get_help())
        raise typer.Exit()


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
    generate_only: bool = typer.Option(
        False, "--generate-only", "-g", help="Only generate manifests, do not apply (for GKE deployments)"
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

    # Handle GKE deployment type (Kubernetes manifests, not Terraform)
    if deployment_type == "gke":
        typer.echo("🚀 GKE deployment detected")
        typer.echo("   Using Kubernetes manifests (similar to minikube)")
        typer.echo("   Images will be pushed to GCR")
        
        # Extract GKE-specific config
        gke_config = config.get("gke", {})
        cluster_name = gke_config.get("cluster_name")
        zone = gke_config.get("zone")
        region_gke = gke_config.get("region")
        
        if not cluster_name:
            typer.echo("❌ GKE cluster_name must be specified in config.gke.cluster_name")
            raise typer.Exit(code=1)
        
        if not zone and not region_gke:
            typer.echo("❌ Either config.gke.zone or config.gke.region must be specified")
            raise typer.Exit(code=1)
        
        typer.echo(f"   Cluster: {cluster_name}")
        typer.echo(f"   Location: {zone or region_gke}")
        
        # Create manifests directory
        manifests_dir = DEPLOYML_DIR / "manifests"
        manifests_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate Kubernetes manifests for each service in stack
        from deployml.utils.kubernetes_gke import (
            generate_mlflow_manifests_gke,
            generate_fastapi_manifests_gke,
            deploy_to_gke,
            connect_to_gke_cluster,
        )
        
        # Connect to GKE cluster
        if not connect_to_gke_cluster(project_id, cluster_name, zone, region_gke):
            raise typer.Exit(code=1)
        
        # Process stack and generate manifests
        mlflow_manifest_dir = None
        fastapi_manifest_dir = None
        
        for stage in stack:
            for stage_name, tool in stage.items():
                if stage_name == "experiment_tracking" and tool.get("name") == "mlflow":
                    params = tool.get("params", {})
                    image = params.get("image", f"gcr.io/{project_id}/mlflow/mlflow:latest")
                    backend_uri = params.get("backend_store_uri", "sqlite:///mlflow.db")
                    artifact_root = params.get("artifact_root")
                    
                    mlflow_manifest_dir = manifests_dir / "mlflow"
                    typer.echo(f"\n📦 Generating MLflow manifests...")
                    generate_mlflow_manifests_gke(
                        output_dir=mlflow_manifest_dir,
                        image=image,
                        project_id=project_id,
                        backend_store_uri=backend_uri,
                        artifact_root=artifact_root,
                        push_image=not image.startswith("gcr.io/"),
                    )
                
                elif stage_name == "model_serving" and tool.get("name") == "fastapi":
                    params = tool.get("params", {})
                    image = params.get("image", f"gcr.io/{project_id}/fastapi/fastapi:latest")
                    mlflow_uri = params.get("mlflow_tracking_uri", "http://mlflow-service:5000")
                    
                    fastapi_manifest_dir = manifests_dir / "fastapi"
                    typer.echo(f"\n📦 Generating FastAPI manifests...")
                    generate_fastapi_manifests_gke(
                        output_dir=fastapi_manifest_dir,
                        image=image,
                        project_id=project_id,
                        mlflow_tracking_uri=mlflow_uri,
                        push_image=not image.startswith("gcr.io/"),
                    )
        
        # Deploy manifests
        if mlflow_manifest_dir and mlflow_manifest_dir.exists():
            typer.echo(f"\n🚀 Deploying MLflow to GKE...")
            if not deploy_to_gke(
                manifest_dir=mlflow_manifest_dir,
                cluster_name=cluster_name,
                project_id=project_id,
                zone=zone,
                region=region_gke,
            ):
                raise typer.Exit(code=1)
        
        if fastapi_manifest_dir and fastapi_manifest_dir.exists():
            typer.echo(f"\n🚀 Deploying FastAPI to GKE...")
            if not deploy_to_gke(
                manifest_dir=fastapi_manifest_dir,
                cluster_name=cluster_name,
                project_id=project_id,
                zone=zone,
                region=region_gke,
            ):
                raise typer.Exit(code=1)
        
        typer.echo("\n✅ GKE deployment complete!")
        typer.echo(f"📁 Manifests saved to: {manifests_dir}")
        return
    
    # Continue with Terraform-based deployments (cloud_run, cloud_vm)
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

    # Handle teardown configuration (needed before copying modules)
    teardown_config = config.get("teardown", {})
    teardown_enabled = teardown_config.get("enabled", False)

    typer.echo("📦 Copying module templates...")
    copy_modules_to_workspace(
        DEPLOYML_MODULES_DIR,
        stack=stack,
        deployment_type=deployment_type,
        cloud=cloud,
        teardown_enabled=teardown_enabled,
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

    # Calculate teardown schedule (teardown_config and teardown_enabled already defined above)
    # Note: This is a preliminary schedule - will be updated after Terraform completes with exact time
    teardown_cron_schedule = ""
    teardown_scheduled_timestamp = 0
    
    if teardown_enabled:
        duration_hours = teardown_config.get("duration_hours", 24)
        deployed_at = datetime.utcnow()
        # Add buffer to ensure schedule is in future (will be updated to exact time after deployment)
        teardown_at = deployed_at + timedelta(hours=duration_hours, minutes=10)
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
        if result_code == 0:
            typer.echo("✅ Deployment complete!")
            
            # Upload Terraform files and resource manifest to GCS for teardown (if enabled)
            if teardown_enabled:
                try:
                    typer.echo("📤 Uploading Terraform files to GCS for teardown...")
                    upload_terraform_files_to_gcs(DEPLOYML_TERRAFORM_DIR, project_id, workspace_name)
                    
                    # Extract and upload resource manifest
                    typer.echo("📋 Extracting resource manifest...")
                    manifest = extract_resource_manifest(
                        DEPLOYML_TERRAFORM_DIR,
                        project_id,
                        workspace_name,
                        region
                    )
                    upload_resource_manifest(manifest, DEPLOYML_TERRAFORM_DIR, project_id, workspace_name)
                    typer.echo("✅ Resource manifest uploaded successfully")
                    
                except Exception as e:
                    typer.echo(f"⚠️  Warning: Could not upload files/manifest to GCS: {e}")
                    typer.echo("   Teardown may not work automatically. Manual teardown required.")
            
            # Handle auto-teardown metadata and update scheduler schedule
            if teardown_enabled:
                duration_hours = teardown_config.get("duration_hours", 24)
                # Calculate teardown time AFTER deployment completes (not before)
                deployed_at = datetime.utcnow()
                teardown_at = deployed_at + timedelta(hours=duration_hours)
                
                # Calculate the correct cron schedule based on actual deployment completion time
                teardown_scheduled_timestamp = int(teardown_at.timestamp())
                correct_cron_schedule = calculate_cron_from_timestamp(teardown_scheduled_timestamp)
                time_zone = teardown_config.get("time_zone", "UTC")
                
                # Update the Cloud Scheduler job with the correct schedule
                scheduler_job_name = f"deployml-teardown-{workspace_name}"
                try:
                    typer.echo(f"⏰ Updating teardown schedule to: {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    update_result = subprocess.run(
                        [
                            "gcloud", "scheduler", "jobs", "update", "http", scheduler_job_name,
                            "--location", region,
                            "--schedule", correct_cron_schedule,
                            "--time-zone", time_zone,
                            "--project", project_id,
                            "--quiet"
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if update_result.returncode == 0:
                        typer.echo(f"✅ Teardown schedule updated successfully")
                    else:
                        typer.echo(f"⚠️  Warning: Could not update scheduler schedule: {update_result.stderr}")
                        typer.echo(f"   Schedule may be incorrect. Check manually with:")
                        typer.echo(f"   gcloud scheduler jobs describe {scheduler_job_name} --location={region} --project={project_id}")
                except Exception as e:
                    typer.echo(f"⚠️  Warning: Could not update scheduler schedule: {e}")
                    typer.echo(f"   Schedule may be incorrect. Check manually with:")
                    typer.echo(f"   gcloud scheduler jobs describe {scheduler_job_name} --location={region} --project={project_id}")
                
                metadata = {
                    "deployed_at": deployed_at.isoformat(),
                    "teardown_scheduled_at": teardown_at.isoformat(),
                    "teardown_enabled": True,
                    "duration_hours": duration_hours,
                    "scheduler_job_name": scheduler_job_name
                }
                save_deployment_metadata(DEPLOYML_DIR, metadata)
                
                typer.echo(f"\n✅ Auto-teardown scheduled for: {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
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
            log_file = DEPLOYML_TERRAFORM_DIR / "terraform_apply.log"
            typer.secho(f"\n❌ Terraform apply failed with exit code {result_code}", fg=typer.colors.RED, bold=True)
            typer.echo(f"\n📋 Check the Terraform log for details:")
            typer.echo(f"   {log_file}")
            typer.echo(f"\n💡 Common issues:")
            typer.echo("   - Required GCP APIs may not be enabled (check log for API activation URLs)")
            typer.echo("   - Insufficient IAM permissions")
            typer.echo("   - Resource conflicts or quota limits")
            typer.echo("\n🔍 Last 20 lines of the log:")
            if log_file.exists():
                try:
                    with open(log_file, 'r') as f:
                        lines = f.readlines()
                        for line in lines[-20:]:
                            typer.echo(f"   {line.rstrip()}")
                except Exception:
                    pass
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
    Manage auto-teardown: cancel scheduled teardown, check status, update schedule, or schedule new teardown.
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
        show_teardown_status(config, DEPLOYML_DIR, workspace_name)
    elif action == "update":
        update_teardown_schedule(config, DEPLOYML_DIR, workspace_name)
    elif action == "schedule":
        schedule_teardown(config, DEPLOYML_DIR, workspace_name)
    else:
        typer.echo(f"❌ Unknown action: {action}. Use: cancel, status, update, or schedule")
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


def show_teardown_status(config: dict, deployml_dir: Path, workspace_name: str):
    """Show teardown status by querying Cloud Scheduler."""
    project_id = config["provider"]["project_id"]
    region = config["provider"]["region"]
    scheduler_job_name = f"deployml-teardown-{workspace_name}"
    
    # Query Cloud Scheduler job
    result = subprocess.run(
        ["gcloud", "scheduler", "jobs", "describe", scheduler_job_name,
         "--project", project_id, "--location", region, "--format", "json"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        typer.echo(f"⚠️ Cloud Scheduler job not found: {scheduler_job_name}")
        typer.echo("   Teardown may not be scheduled or may have already been cancelled.")
        
        # Check local metadata as fallback
        metadata = load_deployment_metadata(deployml_dir)
        if metadata and metadata.get("teardown_enabled"):
            teardown_at = datetime.fromisoformat(metadata["teardown_scheduled_at"])
            typer.echo(f"\n📋 Local metadata shows teardown was scheduled for:")
            typer.echo(f"   {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        return
    
    # Parse Cloud Scheduler job details
    try:
        job_info = json.loads(result.stdout)
    except json.JSONDecodeError:
        typer.echo("❌ Failed to parse Cloud Scheduler job information")
        return
    
    # Extract information
    schedule = job_info.get("schedule", "N/A")
    time_zone = job_info.get("timeZone", "UTC")
    state = job_info.get("state", "UNKNOWN")
    schedule_time = job_info.get("scheduleTime", "")
    last_attempt_time = job_info.get("lastAttemptTime", "")
    
    # Display comprehensive status
    typer.echo("📋 Auto-Teardown Status")
    typer.echo("=" * 60)
    
    # Job state
    state_emoji = "✅" if state == "ENABLED" else "⏸️" if state == "PAUSED" else "❌"
    typer.echo(f"{state_emoji} Status: {state}")
    
    # Cron schedule
    typer.echo(f"📅 Cron Schedule: {schedule}")
    typer.echo(f"🌍 Timezone: {time_zone}")
    
    # Next execution time
    if schedule_time:
        try:
            # Parse ISO format with Z suffix (UTC)
            time_str = schedule_time.replace('Z', '+00:00')
            next_run = datetime.fromisoformat(time_str)
            # Get current UTC time as timezone-aware
            from datetime import timezone
            now = datetime.now(timezone.utc)
            typer.echo(f"⏰ Next Execution: {next_run.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            if now < next_run:
                time_remaining = next_run - now
                hours = int(time_remaining.total_seconds() // 3600)
                minutes = int((time_remaining.total_seconds() % 3600) // 60)
                typer.echo(f"   ⏳ Time Remaining: {hours}h {minutes}m")
            else:
                time_passed = now - next_run
                hours_passed = int(time_passed.total_seconds() // 3600)
                minutes_passed = int((time_passed.total_seconds() % 3600) // 60)
                typer.echo(f"   ⚠️  Scheduled time passed {hours_passed}h {minutes_passed}m ago")
        except Exception as e:
            typer.echo(f"⏰ Next Execution: {schedule_time}")
    
    # Last attempt
    if last_attempt_time and last_attempt_time != "1970-01-01T00:00:00Z":
        try:
            # Parse ISO format with Z suffix (UTC)
            time_str = last_attempt_time.replace('Z', '+00:00')
            last_run = datetime.fromisoformat(time_str)
            typer.echo(f"🕐 Last Execution: {last_run.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        except Exception:
            typer.echo(f"🕐 Last Execution: {last_attempt_time}")
    else:
        typer.echo("🕐 Last Execution: Never")
    
    # Job name for reference
    typer.echo(f"\n📌 Job Name: {scheduler_job_name}")
    
    # Actions
    typer.echo("\n💡 Actions:")
    typer.echo(f"   Update: deployml teardown update --config-path <config-file>")
    typer.echo(f"   Cancel: deployml teardown cancel --config-path <config-file>")
    typer.echo(f"   View in Console: https://console.cloud.google.com/cloudscheduler/jobs/edit/{region}/{scheduler_job_name}?project={project_id}")


def update_teardown_schedule(config: dict, deployml_dir: Path, workspace_name: str):
    """Update the scheduled teardown time."""
    project_id = config["provider"]["project_id"]
    region = config["provider"]["region"]
    scheduler_job_name = f"deployml-teardown-{workspace_name}"
    
    # Check if Cloud Scheduler job exists
    result = subprocess.run(
        ["gcloud", "scheduler", "jobs", "describe", scheduler_job_name,
         "--project", project_id, "--location", region, "--format", "json"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        typer.echo(f"❌ Cloud Scheduler job not found: {scheduler_job_name}")
        typer.echo("   Cannot update schedule. The teardown job may not exist.")
        typer.echo("   Use 'deployml deploy' with teardown.enabled: true to create it.")
        raise typer.Exit(code=1)
    
    # Get current job info to preserve timezone
    try:
        job_info = json.loads(result.stdout)
        time_zone = job_info.get("timeZone", "UTC")
    except json.JSONDecodeError:
        time_zone = "UTC"
    
    # Prompt for new schedule
    typer.echo("📅 Update Teardown Schedule")
    typer.echo("=" * 60)
    
    # Show current schedule
    try:
        schedule_time = job_info.get("scheduleTime", "")
        if schedule_time:
            time_str = schedule_time.replace('Z', '+00:00')
            current_time = datetime.fromisoformat(time_str)
            typer.echo(f"⏰ Current Schedule: {current_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    except Exception:
        pass
    
    # Get new duration
    duration_hours = typer.prompt("Hours until new teardown time", default=24, type=int)
    
    if duration_hours < 0:
        typer.echo("❌ Duration must be positive")
        raise typer.Exit(code=1)
    
    # Calculate new teardown time
    from datetime import timezone
    now = datetime.now(timezone.utc)
    teardown_at = now + timedelta(hours=duration_hours)
    # Use UTC timestamp directly to avoid timezone issues
    teardown_scheduled_timestamp = int(teardown_at.timestamp())
    new_cron_schedule = calculate_cron_from_timestamp(teardown_scheduled_timestamp)
    
    typer.echo(f"\n⏰ New Schedule: {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # Confirm update
    confirm = typer.confirm("Update the teardown schedule?", default=True)
    if not confirm:
        typer.echo("❌ Update cancelled")
        return
    
    # Update Cloud Scheduler job
    typer.echo("\n🔄 Updating Cloud Scheduler job...")
    typer.echo(f"   Cron schedule: {new_cron_schedule}")
    update_result = subprocess.run(
        [
            "gcloud", "scheduler", "jobs", "update", "http", scheduler_job_name,
            "--location", region,
            "--schedule", new_cron_schedule,
            "--time-zone", time_zone,
            "--project", project_id,
            "--quiet"
        ],
        capture_output=True,
        text=True,
    )
    
    if update_result.returncode != 0:
        typer.echo(f"❌ Failed to update schedule: {update_result.stderr}")
        if update_result.stdout:
            typer.echo(f"   stdout: {update_result.stdout}")
        raise typer.Exit(code=1)
    
    # Verify the update by querying the job again
    verify_result = subprocess.run(
        ["gcloud", "scheduler", "jobs", "describe", scheduler_job_name,
         "--project", project_id, "--location", region, "--format", "json"],
        capture_output=True,
        text=True,
    )
    
    if verify_result.returncode == 0:
        try:
            updated_job_info = json.loads(verify_result.stdout)
            updated_schedule_time = updated_job_info.get("scheduleTime", "")
            updated_schedule = updated_job_info.get("schedule", "")
            
            if updated_schedule_time:
                time_str = updated_schedule_time.replace('Z', '+00:00')
                actual_time = datetime.fromisoformat(time_str)
                typer.echo(f"\n✅ Teardown schedule updated successfully!")
                typer.echo(f"   Scheduled time: {actual_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                typer.echo(f"   Cron schedule: {updated_schedule}")
                
                # Check if it matches what we intended
                if actual_time.strftime('%Y-%m-%d %H:%M') != teardown_at.strftime('%Y-%m-%d %H:%M'):
                    typer.echo(f"\n⚠️  Warning: Scheduled time differs from intended time")
                    typer.echo(f"   Intended: {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    typer.echo(f"   Actual: {actual_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            else:
                typer.echo(f"✅ Teardown schedule updated successfully!")
                typer.echo(f"   Cron schedule: {updated_schedule}")
        except Exception as e:
            typer.echo(f"✅ Teardown schedule updated (verification failed: {e})")
    else:
        typer.echo(f"✅ Teardown schedule updated successfully!")
        typer.echo(f"   (Could not verify - check with: gcloud scheduler jobs describe {scheduler_job_name} --location={region} --project={project_id})")
    
    # Update local metadata
    metadata = load_deployment_metadata(deployml_dir) or {}
    metadata.update({
        "deployed_at": metadata.get("deployed_at", now.isoformat()),
        "teardown_scheduled_at": teardown_at.isoformat(),
        "teardown_enabled": True,
        "duration_hours": duration_hours,
        "scheduler_job_name": scheduler_job_name
    })
    save_deployment_metadata(deployml_dir, metadata)


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


@cli.command()
def minikube_init(
    output_dir: Path = typer.Option(
        ..., "--output-dir", "-o", help="Directory to create Kubernetes manifests"
    ),
    image: str = typer.Option(
        ..., "--image", "-i", help="FastAPI Docker image"
    ),
    mlflow_uri: Optional[str] = typer.Option(
        None, "--mlflow-uri", "-m", help="MLflow tracking URI (optional)"
    ),
    start_cluster: bool = typer.Option(
        True, "--start-cluster/--no-start-cluster",
        help="Start minikube cluster if not running"
    ),
):
    """
    Initialize minikube and generate FastAPI Kubernetes manifests.
    Creates deployment.yaml and service.yaml in the specified directory.
    """
    if not check_minikube_running():
        if start_cluster:
            if not start_minikube():
                raise typer.Exit(code=1)
        else:
            typer.echo("Minikube is not running. Use --start-cluster to start it.")
            raise typer.Exit(code=1)
    else:
        typer.echo("Minikube is already running")
    
    typer.echo(f"\nGenerating FastAPI Kubernetes manifests in {output_dir}...")
    generate_fastapi_manifests(
        output_dir=output_dir,
        image=image,
        mlflow_tracking_uri=mlflow_uri
    )
    
    typer.echo("\nSetup complete! Next steps:")
    typer.echo(f"  1. Edit the manifests in {output_dir} if needed")
    typer.echo(f"  2. Deploy with: deployml minikube-deploy --manifest-dir {output_dir}")


@cli.command()
def minikube_deploy(
    manifest_dir: Path = typer.Option(
        ..., "--manifest-dir", "-d",
        help="Directory containing deployment.yaml and service.yaml"
    ),
    image_name: Optional[str] = typer.Option(
        None, "--image-name", "-i",
        help="Docker image name to load into minikube (auto-detected from deployment.yaml if not provided)"
    ),
):
    """
    Deploy FastAPI to minikube using kubectl apply.
    Automatically loads the Docker image into minikube if needed.
    """
    if not manifest_dir.exists():
        typer.echo(f"Directory not found: {manifest_dir}")
        raise typer.Exit(code=1)
    
    if not check_minikube_running():
        typer.echo("Minikube is not running. Start it first:")
        typer.echo("   minikube start")
        typer.echo("   OR")
        typer.echo("   deployml minikube-init --start-cluster")
        raise typer.Exit(code=1)
    
    success = deploy_fastapi_to_minikube(manifest_dir, image_name=image_name)
    
    if not success:
        raise typer.Exit(code=1)


@cli.command()
def mlflow_init(
    output_dir: Path = typer.Option(
        ..., "--output-dir", "-o", help="Directory to create Kubernetes manifests"
    ),
    image: str = typer.Option(
        ..., "--image", "-i", help="MLflow Docker image"
    ),
    backend_store_uri: Optional[str] = typer.Option(
        None, "--backend-store-uri", "-b", help="Backend store URI (defaults to SQLite)"
    ),
    artifact_root: Optional[str] = typer.Option(
        None, "--artifact-root", "-a", help="Artifact root path (defaults to /mlflow-artifacts)"
    ),
    start_cluster: bool = typer.Option(
        True, "--start-cluster/--no-start-cluster",
        help="Start minikube cluster if not running"
    ),
):
    """
    Initialize minikube and generate MLflow Kubernetes manifests.
    Creates deployment.yaml and service.yaml in the specified directory.
    """
    if not check_minikube_running():
        if start_cluster:
            if not start_minikube():
                raise typer.Exit(code=1)
        else:
            typer.echo("Minikube is not running. Use --start-cluster to start it.")
            raise typer.Exit(code=1)
    else:
        typer.echo("Minikube is already running")
    
    typer.echo(f"\nGenerating MLflow Kubernetes manifests in {output_dir}...")
    generate_mlflow_manifests(
        output_dir=output_dir,
        image=image,
        backend_store_uri=backend_store_uri,
        artifact_root=artifact_root
    )
    
    typer.echo("\nSetup complete! Next steps:")
    typer.echo(f"  1. Edit the manifests in {output_dir} if needed")
    typer.echo(f"  2. Deploy with: deployml mlflow-deploy --manifest-dir {output_dir}")


@cli.command()
def mlflow_deploy(
    manifest_dir: Path = typer.Option(
        ..., "--manifest-dir", "-d",
        help="Directory containing deployment.yaml and service.yaml"
    ),
    image_name: Optional[str] = typer.Option(
        None, "--image-name", "-i",
        help="Docker image name to load into minikube (auto-detected from deployment.yaml if not provided)"
    ),
):
    """
    Deploy MLflow to minikube using kubectl apply.
    Automatically loads the Docker image into minikube if needed.
    """
    if not manifest_dir.exists():
        typer.echo(f"Directory not found: {manifest_dir}")
        raise typer.Exit(code=1)
    
    if not check_minikube_running():
        typer.echo("Minikube is not running. Start it first:")
        typer.echo("   minikube start")
        typer.echo("   OR")
        typer.echo("   deployml mlflow-init --start-cluster")
        raise typer.Exit(code=1)
    
    success = deploy_mlflow_to_minikube(manifest_dir, image_name=image_name)
    
    if not success:
        raise typer.Exit(code=1)


@cli.command()
def gke_deploy(
    manifest_dir: Path = typer.Option(
        ..., "--manifest-dir", "-d",
        help="Directory containing deployment.yaml and service.yaml"
    ),
    cluster: str = typer.Option(
        ..., "--cluster", "-c", help="GKE cluster name"
    ),
    project: str = typer.Option(
        ..., "--project", "-p", help="GCP project ID"
    ),
    zone: Optional[str] = typer.Option(
        None, "--zone", "-z", help="GKE cluster zone"
    ),
    region: Optional[str] = typer.Option(
        None, "--region", "-r", help="GKE cluster region"
    ),
):
    """
    Deploy Kubernetes manifests to GKE cluster.
    Simple command: just point to manifests and cluster info.
    """
    if not manifest_dir.exists():
        typer.echo(f"Directory not found: {manifest_dir}")
        raise typer.Exit(code=1)
    
    if not zone and not region:
        typer.echo("Either --zone or --region must be provided")
        raise typer.Exit(code=1)
    
    success = deploy_to_gke(
        manifest_dir=manifest_dir,
        cluster_name=cluster,
        project_id=project,
        zone=zone,
        region=region,
    )
    
    if not success:
        raise typer.Exit(code=1)


@cli.command()
def gke_init(
    output_dir: Path = typer.Option(
        ..., "--output-dir", "-o", help="Directory to create Kubernetes manifests"
    ),
    image: str = typer.Option(
        ..., "--image", "-i", help="Docker image name (local or GCR)"
    ),
    project: str = typer.Option(
        ..., "--project", "-p", help="GCP project ID"
    ),
    service: str = typer.Option(
        "mlflow", "--service", "-s", help="Service type: mlflow or fastapi"
    ),
    mlflow_uri: Optional[str] = typer.Option(
        None, "--mlflow-uri", "-m", help="MLflow URI (for FastAPI)"
    ),
):
    """
    Generate Kubernetes manifests for GKE.
    Simple command: specify image, project, and service type.
    """
    if service == "mlflow":
        generate_mlflow_manifests_gke(
            output_dir=output_dir,
            image=image,
            project_id=project,
            push_image=not image.startswith("gcr.io/"),
        )
        typer.echo(f"\nNext: deployml gke-deploy -d {output_dir} -c CLUSTER -p {project} -z ZONE")
    elif service == "fastapi":
        generate_fastapi_manifests_gke(
            output_dir=output_dir,
            image=image,
            project_id=project,
            mlflow_tracking_uri=mlflow_uri,
            push_image=not image.startswith("gcr.io/"),
        )
        typer.echo(f"\nNext: deployml gke-deploy -d {output_dir} -c CLUSTER -p {project} -z ZONE")
    else:
        typer.echo(f"Unknown service: {service}. Use 'mlflow' or 'fastapi'")
        raise typer.Exit(code=1)


@cli.command()
def gke_apply(
    config_path: Path = typer.Option(
        ..., "--config-path", "-c", help="Path to YAML config file"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompts and apply"
    ),
):
    """
    Apply Kubernetes manifests to GKE cluster.
    Manifests must be generated first using 'deployml deploy --config-path <config> --generate-only'.
    """
    if not config_path.exists():
        typer.echo(f"Config file not found: {config_path}")
        raise typer.Exit(code=1)

    config = yaml.safe_load(config_path.read_text())
    
    # Validate deployment type
    deployment_type = config.get("deployment", {}).get("type")
    if deployment_type != "gke":
        typer.echo(f"This command is only for GKE deployments. Found: {deployment_type}")
        raise typer.Exit(code=1)
    
    workspace_name = config.get("name") or "development"
    DEPLOYML_DIR = Path.cwd() / ".deployml" / workspace_name
    manifests_dir = DEPLOYML_DIR / "manifests"
    
    if not manifests_dir.exists():
        typer.echo(f"Manifests directory not found: {manifests_dir}")
        typer.echo("   Generate manifests first with: deployml deploy --config-path <config> --generate-only")
        raise typer.Exit(code=1)
    
    # Extract GKE-specific config
    project_id = config["provider"]["project_id"]
    gke_config = config.get("gke", {})
    cluster_name = gke_config.get("cluster_name")
    zone = gke_config.get("zone")
    region_gke = gke_config.get("region")
    
    if not cluster_name:
        typer.echo("GKE cluster_name must be specified in config.gke.cluster_name")
        raise typer.Exit(code=1)
    
    if not zone and not region_gke:
        typer.echo("Either config.gke.zone or config.gke.region must be specified")
        raise typer.Exit(code=1)
    
    typer.echo(f"🚀 Applying GKE manifests")
    typer.echo(f"   Cluster: {cluster_name}")
    typer.echo(f"   Location: {zone or region_gke}")
    typer.echo(f"   Manifests: {manifests_dir}")
    
    # Import deployment function
    from deployml.utils.kubernetes_gke import (
        deploy_to_gke,
        connect_to_gke_cluster,
    )
    
    # Connect to GKE cluster
    if not connect_to_gke_cluster(project_id, cluster_name, zone, region_gke):
        raise typer.Exit(code=1)
    
    # Find and deploy all manifest directories
    mlflow_manifest_dir = manifests_dir / "mlflow"
    fastapi_manifest_dir = manifests_dir / "fastapi"
    
    if not yes:
        typer.echo("\n About to apply manifests to GKE cluster")
        if not typer.confirm("Continue?"):
            typer.echo("Deployment cancelled")
            return
    
    deployed_any = False
    
    if mlflow_manifest_dir.exists():
        typer.echo(f"\n Deploying MLflow to GKE...")
        if deploy_to_gke(
            manifest_dir=mlflow_manifest_dir,
            cluster_name=cluster_name,
            project_id=project_id,
            zone=zone,
            region=region_gke,
        ):
            deployed_any = True
        else:
            raise typer.Exit(code=1)
    
    if fastapi_manifest_dir.exists():
        typer.echo(f"\n Deploying FastAPI to GKE...")
        if deploy_to_gke(
            manifest_dir=fastapi_manifest_dir,
            cluster_name=cluster_name,
            project_id=project_id,
            zone=zone,
            region=region_gke,
        ):
            deployed_any = True
        else:
            raise typer.Exit(code=1)
    
    if deployed_any:
        typer.echo("\n GKE deployment complete!")
    else:
        typer.echo("\n No manifests found to deploy")
        typer.echo(f"   Check: {manifests_dir}")


def main():
    """
    Entry point for the DeployML CLI.
    """
    cli()


if __name__ == "__main__":
    main()
