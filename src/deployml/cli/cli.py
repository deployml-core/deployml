import sys
import yaml
import typer
import shutil
import subprocess
import re
import importlib.resources as pkg_resources
from deployml.utils.banner import display_banner
from deployml.utils.menu import prompt, show_menu
from deployml.utils.constants import (
    TEMPLATE_DIR,
    TERRAFORM_DIR,
    TOOL_VARIABLES,
    ANIMAL_NAMES,
    FALLBACK_WORDS,
    REQUIRED_GCP_APIS,
    REQUIRED_GCP_IAM_ROLES,
)
from deployml.enum.cloud_provider import CloudProvider
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from typing import Optional
import random
import string
from google.cloud import storage
import hashlib

from deployml.notebook.docker import build_images 

# Import refactored utility functions
from deployml.utils.helpers import (
    check,
    check_gcp_auth,
    check_gcp_adc,
    check_bq,
    get_terraform_version,
    validate_gcp_project,
    validate_gcp_region,
    get_missing_iam_roles,
    check_docker_daemon,
    copy_modules_to_workspace,
    bucket_exists,
    generate_bucket_name,
    estimate_terraform_time,
    cleanup_cloud_sql_resources,
    cleanup_terraform_files,
    run_terraform_with_loading_bar,
    _create_docker_folder,
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
            typer.echo(f"WARNING: Could not read Terraform state: {state_proc.stderr}")
            return
        
        # Find the terraform_files bucket resource
        bucket_resource = None
        for line in state_proc.stdout.split('\n'):
            if 'module.teardown.google_storage_bucket.terraform_files' in line:
                bucket_resource = line.strip()
                break
        
        if not bucket_resource:
            typer.echo("WARNING: Teardown module bucket not found in state. Skipping upload.")
            return
        
        # Get bucket name from state
        show_proc = subprocess.run(
            ["terraform", "state", "show", bucket_resource],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
        )
        
        if show_proc.returncode != 0:
            typer.echo(f"WARNING: Could not get bucket name: {show_proc.stderr}")
            return
        
        # Extract bucket name from terraform state show output
        bucket_name = None
        for line in show_proc.stdout.split('\n'):
            if 'name' in line and '=' in line:
                bucket_name = line.split('=')[1].strip().strip('"')
                break
        
        if not bucket_name:
            typer.echo("WARNING: Could not extract bucket name from state.")
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
        
        typer.echo(f" Uploaded {uploaded_count} Terraform files to gs://{bucket_name}/{workspace_name}/terraform/")
        
    except Exception as e:
        typer.echo(f"WARNING: Error uploading Terraform files: {e}")
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
        
        typer.echo(f" Resource manifest uploaded to gs://{bucket_name}/{workspace_name}/resource-manifest.json")
        
    except Exception as e:
        typer.echo(f"WARNING: Error uploading resource manifest: {e}")
        raise

import re
import time
import json
from datetime import datetime, timedelta

def _load_config_or_exit(config_path: Path) -> dict:
    """Load YAML config with clean error messages. Exits non-zero on failure."""
    try:
        data = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError as e:
        typer.secho(f" Config file is not valid YAML: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if not isinstance(data, dict):
        typer.secho(
            f" Config file must be a YAML mapping at the top level, got {type(data).__name__}.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    return data


_SUPPORTED_PROVIDERS = {"gcp", "aws", "azure"}


def _validate_deploy_config_or_exit(config: dict) -> None:
    """Validate the fields deploy and destroy need. Exits non-zero on missing or bad values."""
    provider = config.get("provider")
    if not isinstance(provider, dict):
        typer.secho(" Config is missing required field: provider (mapping).", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    name = provider.get("name")
    if name not in _SUPPORTED_PROVIDERS:
        typer.secho(
            f" provider.name must be one of {sorted(_SUPPORTED_PROVIDERS)}, got {name!r}.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    if name == "gcp" and not provider.get("project_id"):
        typer.secho(" GCP config is missing provider.project_id.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    deployment = config.get("deployment")
    if not isinstance(deployment, dict) or not deployment.get("type"):
        typer.secho(" Config is missing required field: deployment.type.", fg=typer.colors.RED)
        raise typer.Exit(code=1)


def _gcp_credentials_preflight_or_exit() -> None:
    """Verify gcloud auth and Application Default Credentials before any GCP deploy
    work. ADC backs the Terraform google provider, so without it deploy fails
    opaquely at apply with 'default credentials not found' (issue #54)."""
    if not check_gcp_auth():
        typer.secho(
            " gcloud is not authenticated. Run: gcloud auth login",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    if not check_gcp_adc():
        typer.secho(
            " Application Default Credentials are missing. "
            "Run: gcloud auth application-default login",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)


def get_version():
    """Get version from package metadata"""
    try:
        from importlib.metadata import version
        return version("deployml-core")
    except Exception:
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent.parent.parent
            )
            if result.returncode == 0:
                git_version = result.stdout.strip().lstrip("v")
                return git_version
        except Exception:
            pass
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
    typer.echo("\n DeployML Doctor Summary:\n")

    docker_installed = check("docker")
    terraform_installed = check("terraform")
    gcp_installed = check("gcloud")
    gcp_authed = check_gcp_auth() if gcp_installed else False
    aws_installed = check("aws")
    infracost_installed = check_infracost_available()

    # Docker
    if docker_installed:
        typer.secho("\n Docker is installed", fg=typer.colors.GREEN)
    else:
        typer.secho("\n Docker is not installed", fg=typer.colors.RED)

    # Terraform with version gate (need >= 1.0)
    if terraform_installed:
        tf_ver = get_terraform_version()
        if tf_ver and tf_ver[0] >= 1:
            typer.secho(f"\n Terraform {'.'.join(map(str, tf_ver))} (>= 1.0)", fg=typer.colors.GREEN)
        elif tf_ver:
            typer.secho(f"\n Terraform {'.'.join(map(str, tf_ver))} found, but requires >= 1.0", fg=typer.colors.RED)
        else:
            typer.secho("\n Terraform installed, version unknown", fg=typer.colors.YELLOW)
    else:
        typer.secho("\n Terraform is not installed", fg=typer.colors.RED)

    # Infracost
    if infracost_installed:
        typer.secho("\n Infracost is installed", fg=typer.colors.GREEN)
    else:
        typer.secho(
            "\nWARNING: Infracost not installed (optional)", fg=typer.colors.YELLOW
        )
        typer.echo(
            "   Install for cost analysis: https://www.infracost.io/docs/#quick-start"
        )

    # GCP CLI
    if gcp_installed and gcp_authed:
        typer.secho(
            "\n GCP CLI installed and authenticated", fg=typer.colors.GREEN
        )
        # Check enabled GCP APIs
        # ADC and bq are required for client libs and BigQuery work
        if check_gcp_adc():
            typer.secho("\n GCP Application Default Credentials configured", fg=typer.colors.GREEN)
        else:
            typer.secho("\n GCP Application Default Credentials NOT configured", fg=typer.colors.RED)
            typer.echo("   Fix: gcloud auth application-default login")
        if check_bq():
            typer.secho("\n bq CLI is installed", fg=typer.colors.GREEN)
        else:
            typer.secho("\n bq CLI not installed", fg=typer.colors.YELLOW)
            typer.echo("   Fix: gcloud components install bq")
        if not project_id:
            typer.secho(
                "\nSKIP: API and IAM checks need --project-id. Re-run as: deployml doctor --project-id YOUR_GCP_PROJECT_ID",
                fg=typer.colors.YELLOW,
            )
        if project_id:
            project_id = project_id.strip()
        if project_id:  # Check if not empty after stripping
            typer.echo(
                f"\n Checking enabled APIs for project: {project_id} ..."
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
                typer.secho(" Failed to list enabled APIs.", fg=typer.colors.RED)
                if result.stderr:
                    typer.echo(f"   Error: {result.stderr.strip()}")
            else:
                enabled_apis = set(result.stdout.strip().splitlines())
                missing_apis = [
                    api for api in REQUIRED_GCP_APIS if api not in enabled_apis
                ]
                if not missing_apis:
                    typer.secho(
                        " All required GCP APIs are enabled.",
                        fg=typer.colors.GREEN,
                    )
                else:
                    typer.secho(
                        "WARNING: The following required APIs are NOT enabled:",
                        fg=typer.colors.YELLOW,
                    )
                    for api in missing_apis:
                        typer.echo(f"  - {api}")
                    typer.echo(
                        "You can enable them with: deployml init --provider gcp --project-id <PROJECT_ID>"
                    )
            # IAM role probe for the same project
            missing_roles = get_missing_iam_roles(project_id, REQUIRED_GCP_IAM_ROLES)
            if not missing_roles:
                typer.secho(
                    f"\n IAM roles on {project_id}: all required roles present",
                    fg=typer.colors.GREEN,
                )
            else:
                typer.secho(
                    f"\nWARNING: Missing IAM roles on {project_id}:",
                    fg=typer.colors.YELLOW,
                )
                for r in missing_roles:
                    typer.echo(f"  - {r}")
                typer.echo("   Fix: grant roles/owner OR each role via gcloud projects add-iam-policy-binding")
    elif gcp_installed:
        typer.secho(
            "\nWARNING: GCP CLI installed but not authenticated",
            fg=typer.colors.YELLOW,
        )
    else:
        typer.secho("\n GCP CLI not installed", fg=typer.colors.RED)

    # AWS CLI
    if aws_installed:
        typer.secho(f"\n AWS CLI installed", fg=typer.colors.GREEN)
    else:
        typer.secho(
            "\n AWS CLI not installed",
            fg=typer.colors.YELLOW,
        )
    typer.echo()


@cli.command()
def vm():
    """
    Create a new Virtual Machine (VM) deployment. NOT YET IMPLEMENTED.
    """
    typer.secho(
        " The `vm` command is not yet implemented. Use `deployml deploy` with "
        "deployment.type: cloud_vm in config.yaml.",
        fg=typer.colors.YELLOW,
    )
    raise typer.Exit(code=1)


@cli.command()
def generate(
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite an existing config without confirming"
    ),
):
    """
    Generate a deployment configuration YAML file interactively.
    """
    display_banner("Welcome to DeployML Stack Generator!")
    typer.echo("\n")
    name = prompt("MLOps Stack name", "stack")
    provider = show_menu("  Select Provider", [CloudProvider.GCP], CloudProvider.GCP)

    # Import DeploymentType here to avoid circular imports
    from deployml.enum.deployment_type import DeploymentType

    deployment_type = show_menu(
        " Select Deployment Type", DeploymentType, DeploymentType.CLOUD_RUN
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
    config_filename = "config.yaml"
    config_path = Path(config_filename)

    # Confirm only if the file already exists. Earlier code mistakenly called
    # .exists() on a string and crashed for every user; now it gates on the
    # real overwrite case.
    if config_path.exists() and not force:
        confirm = typer.confirm(
            "This will overwrite the existing config.yaml. Continue?"
        )
        if not confirm:
            typer.echo("Aborted.")
            raise typer.Exit()

    with open(config_filename, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    typer.secho(
        f"\n Configuration saved to: {config_filename}", fg=typer.colors.GREEN
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
    if action not in ["plan", "apply", "destroy"]:
        typer.secho(
            f" Invalid action: {action}. Use: plan, apply, destroy",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    config_path = Path(stack_config_path)
    if not config_path.exists():
        typer.secho(f" Config file not found: {config_path}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    config = _load_config_or_exit(config_path)

    if not output_dir:
        workspace = config.get("name") or "default"
        output_dir = Path.cwd() / ".deployml" / workspace / "terraform"
    else:
        output_dir = Path(output_dir)


@cli.command()
def deploy(
    config_path: Path = typer.Option(
        Path("config.yaml"), "--config-path", "-c", help="Path to YAML config file"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompts and deploy"
    ),
    generate_only: bool = typer.Option(
        False, "--generate-only", "-g", help="Only generate manifests, do not apply (for GKE deployments)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Stream Terraform logs to stdout instead of showing progress bar"
    ),
):
    """
    Deploy infrastructure based on a YAML configuration file.
    """
    if not config_path.exists():
        typer.echo(f" Config file not found: {config_path}")
        raise typer.Exit(code=1)

    config = _load_config_or_exit(config_path)
    _validate_deploy_config_or_exit(config)

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
                            f" No bucket specified for artifact_tracking, using generated bucket name: {new_bucket}"
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

    # Workspace name MUST match across deploy, get-urls, and destroy.
    # All three default to "default" when config has no name set.
    workspace_name = config.get("name") or "default"

    DEPLOYML_DIR = Path.cwd() / ".deployml" / workspace_name
    DEPLOYML_TERRAFORM_DIR = DEPLOYML_DIR / "terraform"
    DEPLOYML_MODULES_DIR = DEPLOYML_DIR / "terraform" / "modules"

    typer.echo(f" Using workspace: {workspace_name}")
    typer.echo(f" Workspace path: {DEPLOYML_DIR}")

    DEPLOYML_TERRAFORM_DIR.mkdir(parents=True, exist_ok=True)
    DEPLOYML_MODULES_DIR.mkdir(parents=True, exist_ok=True)

    # Project ID drift detection. If this workspace was previously deployed to a
    # different project, fail fast so we do not orphan resources in the old one.
    project_marker = DEPLOYML_DIR / ".project_id"
    if cloud == "gcp":
        if project_marker.exists():
            previous_project = project_marker.read_text().strip()
            if previous_project and previous_project != project_id:
                typer.secho(
                    f" Workspace '{workspace_name}' was previously deployed to project "
                    f"'{previous_project}'. Config now points at '{project_id}'.",
                    fg=typer.colors.RED,
                )
                typer.echo("  Run `deployml destroy` first to clean up the old project,")
                typer.echo("  or change `name:` in config.yaml to use a fresh workspace.")
                raise typer.Exit(code=1)
        project_marker.write_text(project_id)

    region = config["provider"]["region"]
    if cloud == "gcp" and not validate_gcp_region(region, project_id):
        typer.secho(f" Region '{region}' is not valid for GCP. Run: gcloud compute regions list", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # ADC backs the Terraform google provider, so deploy must verify auth and ADC
    # the way init and doctor do. Without this a logged-in user with no ADC passes
    # the auth check and then fails opaquely at terraform apply (issue #54).
    if cloud == "gcp":
        _gcp_credentials_preflight_or_exit()

    deployment_type = config["deployment"]["type"]
    stack = config["stack"]

    # Handle GKE deployment type (Kubernetes manifests, not Terraform)
    if deployment_type == "gke":
        typer.echo(" GKE deployment detected")
        typer.echo("   Using Kubernetes manifests (similar to minikube)")
        typer.echo("   Images will be pushed to GCR")
        
        # Extract GKE-specific config
        gke_config = config.get("gke", {})
        cluster_name = gke_config.get("cluster_name")
        zone = gke_config.get("zone")
        region_gke = gke_config.get("region")
        
        if not cluster_name:
            typer.echo(" GKE cluster_name must be specified in config.gke.cluster_name")
            raise typer.Exit(code=1)
        
        if not zone and not region_gke:
            typer.echo(" Either config.gke.zone or config.gke.region must be specified")
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
        
        # Connect to the cluster only when we will actually apply. --generate-only
        # renders manifests offline, so it can run before the cluster exists.
        if not generate_only and not connect_to_gke_cluster(project_id, cluster_name, zone, region_gke):
            raise typer.Exit(code=1)

        # Process stack and generate manifests
        mlflow_manifest_dir = None
        fastapi_manifest_dir = None
        
        for stage in stack:
            for stage_name, tool in stage.items():
                if stage_name == "experiment_tracking" and tool.get("name") == "mlflow":
                    params = tool.get("params", {})
                    image = params.get("image", f"gcr.io/{project_id}/mlflow/mlflow:latest")
                    # Leave as None when unset so the GKE generator picks its
                    # persistent default (sqlite on the mounted PVC). A hardcoded
                    # sqlite:///mlflow.db here would override it with an ephemeral,
                    # container-local store that is wiped on every pod restart.
                    backend_uri = params.get("backend_store_uri")
                    artifact_root = params.get("artifact_root")
                    
                    mlflow_manifest_dir = manifests_dir / "mlflow"
                    typer.echo(f"\n Generating MLflow manifests...")
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
                    typer.echo(f"\n Generating FastAPI manifests...")
                    generate_fastapi_manifests_gke(
                        output_dir=fastapi_manifest_dir,
                        image=image,
                        project_id=project_id,
                        mlflow_tracking_uri=mlflow_uri,
                        push_image=not image.startswith("gcr.io/"),
                    )
        
        # --generate-only stops here: manifests are rendered but not applied.
        # The documented flow is to then apply them with `deployml gke-apply`.
        if generate_only:
            typer.echo("\n Manifests generated (not applied).")
            typer.echo(f" Manifests saved to: {manifests_dir}")
            typer.echo(f" Apply with: deployml gke-apply --config-path {config_path}")
            return

        # Deploy manifests
        if mlflow_manifest_dir and mlflow_manifest_dir.exists():
            typer.echo(f"\n Deploying MLflow to GKE...")
            if not deploy_to_gke(
                manifest_dir=mlflow_manifest_dir,
                cluster_name=cluster_name,
                project_id=project_id,
                zone=zone,
                region=region_gke,
            ):
                raise typer.Exit(code=1)
        
        if fastapi_manifest_dir and fastapi_manifest_dir.exists():
            typer.echo(f"\n Deploying FastAPI to GKE...")
            if not deploy_to_gke(
                manifest_dir=fastapi_manifest_dir,
                cluster_name=cluster_name,
                project_id=project_id,
                zone=zone,
                region=region_gke,
            ):
                raise typer.Exit(code=1)
        
        typer.echo("\n GKE deployment complete!")
        typer.echo(f" Manifests saved to: {manifests_dir}")
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

    typer.echo(" Copying module templates...")
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
                    f" Bucket config: {stage_name}/{tool['name']} -> {bucket_name} (create: {create_bucket}, exists: {bucket_exists_flag})"
                )

    # Simple boolean flag for backward compatibility
    create_artifact_bucket = any(config["create"] for config in bucket_configs)

    typer.echo(f" Unified bucket creation: {create_artifact_bucket}")

    # Auto-resolve image URIs: if a service image is not specified in the config (or still
    # points to a legacy gcr.io path), derive it from the Artifact Registry path that
    # `deployml build-images` produces: {region}-docker.pkg.dev/{project}/mlops-images/{name}
    # This keeps the YAML config free of hardcoded image URIs — project/region are enough.
    _TOOL_IMAGE_NAMES = {
        "mlflow": "mlflow",
        "feast": "feast",
        "fastapi": "fastapi",
        "grafana": "grafana-container",
        "wandb": "wandb",
    }
    _ar_base = f"{region}-docker.pkg.dev/{project_id}/mlops-images"
    # Tag defaults to the deployml version so deploys are reproducible.
    # Users can pin to anything (a git SHA, a date string, a release tag) via
    # config.provider.image_tag. Avoid :latest in production paths.
    _image_tag = config.get("provider", {}).get("image_tag") or f"v{get_version()}"
    for stage in stack:
        for stage_name, tool in stage.items():
            tool_name = tool.get("name", "")
            params = tool.setdefault("params", {})
            existing_image = params.get("image", "")
            if not existing_image or existing_image.startswith("gcr.io/"):
                image_name = _TOOL_IMAGE_NAMES.get(tool_name)
                if image_name:
                    params["image"] = f"{_ar_base}/{image_name}:{_image_tag}"
            # Cron job images are per-job and must be set explicitly. Skip here.
            if stage_name == "workflow_orchestration" and tool_name == "cron":
                for job in params.get("jobs", []):
                    if not job.get("image") or job.get("image", "").startswith("gcr.io/"):
                        job_name = job.get("service_name", "")
                        job["image"] = f"{_ar_base}/{job_name}:{_image_tag}"

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
        # Use timezone-aware UTC. datetime.utcnow() returns a naive datetime,
        # and .timestamp() on a naive datetime treats it as local time,
        # corrupting the schedule by the local TZ offset.
        from datetime import timezone as _tz
        deployed_at = datetime.now(_tz.utc)
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

    # Deploy. Falls back to workspace_name when config has no top-level 'name'.
    # Auth and ADC were already preflighted above, so just point gcloud at the project.
    typer.echo(f" Deploying {config.get('name', workspace_name)} to {cloud}...")

    subprocess.run(
        ["gcloud", "config", "set", "project", project_id],
        cwd=DEPLOYML_TERRAFORM_DIR,
    )

    typer.echo(" Initializing Terraform...")
    # Capture stderr so init failures (state lock, missing ADC, bucket perms)
    # surface a real message instead of a silent exit.
    init_proc = subprocess.run(
        ["terraform", "init"],
        cwd=DEPLOYML_TERRAFORM_DIR,
        capture_output=True,
        text=True,
    )
    if init_proc.returncode != 0:
        typer.secho(" Terraform init failed.", fg=typer.colors.RED)
        if init_proc.stderr.strip():
            typer.echo(init_proc.stderr.strip())
        raise typer.Exit(code=1)

    typer.echo(" Planning deployment...")
    result = subprocess.run(
        ["terraform", "plan"],
        cwd=DEPLOYML_TERRAFORM_DIR,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        typer.echo(f" Terraform plan failed: {result.stderr}")
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
        confirmation_msg = f" Deploy stack? {cost_msg}"
    else:
        confirmation_msg = " Do you want to deploy the stack?"

    if yes or typer.confirm(confirmation_msg):
        estimated_time = estimate_terraform_time(result.stdout, "apply")
        typer.echo(f" Applying changes... (Estimated time: {estimated_time})")
        # Re-init before apply; capture stderr to surface failures
        init_proc2 = subprocess.run(
            ["terraform", "init"],
            cwd=DEPLOYML_TERRAFORM_DIR,
            capture_output=True,
            text=True,
        )
        if init_proc2.returncode != 0:
            typer.secho(" Terraform init failed before apply.", fg=typer.colors.RED)
            if init_proc2.stderr.strip():
                typer.echo(init_proc2.stderr.strip())
            raise typer.Exit(code=1)
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
            verbose=verbose,
        )
        if result_code == 0:
            typer.echo(" Deployment complete!")
            
            # Upload Terraform files and resource manifest to GCS for teardown (if enabled)
            if teardown_enabled:
                try:
                    typer.echo(" Uploading Terraform files to GCS for teardown...")
                    upload_terraform_files_to_gcs(DEPLOYML_TERRAFORM_DIR, project_id, workspace_name)
                    
                    # Extract and upload resource manifest
                    typer.echo(" Extracting resource manifest...")
                    manifest = extract_resource_manifest(
                        DEPLOYML_TERRAFORM_DIR,
                        project_id,
                        workspace_name,
                        region
                    )
                    upload_resource_manifest(manifest, DEPLOYML_TERRAFORM_DIR, project_id, workspace_name)
                    typer.echo(" Resource manifest uploaded successfully")
                    
                except Exception as e:
                    typer.echo(f"WARNING: Warning: Could not upload files/manifest to GCS: {e}")
                    typer.echo("   Teardown may not work automatically. Manual teardown required.")
            
            # Handle auto-teardown metadata and update scheduler schedule
            if teardown_enabled:
                duration_hours = teardown_config.get("duration_hours", 24)
                # Timezone-aware UTC. Avoid datetime.utcnow() to keep .timestamp() correct.
                from datetime import timezone as _tz
                deployed_at = datetime.now(_tz.utc)
                teardown_at = deployed_at + timedelta(hours=duration_hours)

                teardown_scheduled_timestamp = int(teardown_at.timestamp())
                correct_cron_schedule = calculate_cron_from_timestamp(teardown_scheduled_timestamp)
                time_zone = teardown_config.get("time_zone", "UTC")
                
                # Update the Cloud Scheduler job with the correct schedule
                scheduler_job_name = f"deployml-teardown-{workspace_name}"
                try:
                    typer.echo(f" Updating teardown schedule to: {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
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
                        typer.echo(f" Teardown schedule updated successfully")
                    else:
                        typer.echo(f"WARNING: Warning: Could not update scheduler schedule: {update_result.stderr}")
                        typer.echo(f"   Schedule may be incorrect. Check manually with:")
                        typer.echo(f"   gcloud scheduler jobs describe {scheduler_job_name} --location={region} --project={project_id}")
                except Exception as e:
                    typer.echo(f"WARNING: Warning: Could not update scheduler schedule: {e}")
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
                
                typer.echo(f"\n Auto-teardown scheduled for: {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
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
                        typer.echo("\n DeployML Outputs:")
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
                    typer.echo(f"WARNING:Failed to parse Terraform outputs: {e}")
            else:
                typer.echo("WARNING:Could not retrieve Terraform outputs.")
        else:
            log_file = DEPLOYML_TERRAFORM_DIR / "terraform_apply.log"
            typer.secho(f"\n Terraform apply failed with exit code {result_code}", fg=typer.colors.RED, bold=True)
            typer.echo(f"\n Check the Terraform log for details:")
            typer.echo(f"   {log_file}")
            typer.echo(f"\n Common issues:")
            typer.echo("   - Required GCP APIs may not be enabled (check log for API activation URLs)")
            typer.echo("   - Insufficient IAM permissions")
            typer.echo("   - Resource conflicts or quota limits")
            typer.echo("\n Last 20 lines of the log:")
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
        typer.echo(" Deployment cancelled")


@cli.command()
def get_urls(
    config_path: Path = typer.Option(
        Path("config.yaml"), "--config-path", "-c", help="Path to YAML config file"
    ),
    env_path: Path = typer.Option(
        Path(".env"), "--env-path", help="Path to write .env file"
    ),
    show_secrets: bool = typer.Option(
        False, "--show-secrets", help="Fetch and print Grafana admin password and MLflow DSN connection hint. Uses gcloud secrets versions access."
    ),
):
    """
    Print service URLs from the last deployment and write them to a .env file.
    """
    if not config_path.exists():
        typer.echo(f" Config file not found: {config_path}")
        raise typer.Exit(code=1)

    config = _load_config_or_exit(config_path)
    workspace_name = config.get("name") or "default"
    project_id = config.get("provider", {}).get("project_id", "")
    terraform_dir = Path.cwd() / ".deployml" / workspace_name / "terraform"

    if not terraform_dir.exists():
        typer.echo(f" No deployment found at {terraform_dir}. Run 'deployml deploy' first.")
        raise typer.Exit(code=1)

    output_proc = subprocess.run(
        ["terraform", "output", "-json"],
        cwd=terraform_dir,
        capture_output=True,
        text=True,
    )
    if output_proc.returncode != 0:
        typer.echo(" Could not retrieve Terraform outputs. Is the stack deployed?")
        raise typer.Exit(code=1)

    try:
        outputs = json.loads(output_proc.stdout)
    except Exception:
        typer.echo(" Failed to parse Terraform outputs.")
        raise typer.Exit(code=1)

    if not outputs:
        typer.echo("No outputs found. Is the stack deployed?")
        raise typer.Exit(code=1)

    typer.echo("\n DeployML Outputs:")
    env_lines = []
    for key, value in outputs.items():
        is_sensitive = value.get("sensitive", False)
        output_val = value.get("value")
        env_key = key.upper()
        if is_sensitive:
            typer.secho(f"  {key}: [SENSITIVE] (value hidden)", fg=typer.colors.YELLOW)
        elif isinstance(output_val, str):
            if output_val.startswith("http://") or output_val.startswith("https://"):
                typer.secho(f"  {key}: {output_val}", fg=typer.colors.BRIGHT_BLUE, bold=True)
                env_lines.append(f"{env_key}={output_val}")
            elif output_val == "":
                typer.secho(f"  {key}: [No value]", fg=typer.colors.YELLOW)
            else:
                typer.echo(f"  {key}: {output_val}")
                env_lines.append(f"{env_key}={output_val}")
        elif isinstance(output_val, dict):
            typer.echo(f"  {key}:")
            for subkey, subval in output_val.items():
                sub_env_key = f"{env_key}_{subkey.upper()}"
                if isinstance(subval, str) and (subval.startswith("http://") or subval.startswith("https://")):
                    typer.secho(f"    {subkey}: {subval}", fg=typer.colors.BRIGHT_BLUE, bold=True)
                    env_lines.append(f"{sub_env_key}={subval}")
                elif isinstance(subval, str) and subval:
                    typer.echo(f"    {subkey}: {subval}")
                    env_lines.append(f"{sub_env_key}={subval}")
        else:
            typer.echo(f"  {key}: {output_val}")

    if project_id:
        env_lines.append(f"BIGQUERY_PROJECT={project_id}")
        typer.echo(f"  bigquery_project: {project_id}")

    env_path.write_text("\n".join(env_lines) + "\n")
    typer.echo(f"\n .env written to {env_path.resolve()}")

    if show_secrets:
        typer.secho("\n Secrets:", fg=typer.colors.YELLOW, bold=True)
        # Grafana admin password
        grafana_secret = outputs.get("grafana_admin_password_secret_id", {}).get("value", "")
        if grafana_secret and project_id:
            fetch = subprocess.run(
                ["gcloud", "secrets", "versions", "access", "latest",
                 "--secret", grafana_secret, "--project", project_id],
                capture_output=True, text=True,
            )
            if fetch.returncode == 0:
                typer.echo(f"  grafana_admin_user: admin")
                typer.echo(f"  grafana_admin_password: {fetch.stdout.strip()}")
            else:
                typer.echo(f"  grafana_admin_password: (fetch failed: {fetch.stderr.strip()})")
        # MLflow DSN. Public IP is blocked; print the Cloud SQL Auth Proxy steps.
        instance = outputs.get("instance_connection_name", {}).get("value", "")
        dsn_secret = outputs.get("mlflow_dsn_secret_id", {}).get("value", "")
        if instance and dsn_secret and project_id:
            typer.echo("")
            typer.echo("  To connect to MLflow Postgres from your laptop, run the Cloud SQL Auth Proxy:")
            typer.echo(f"    cloud-sql-proxy {instance} --port=5432")
            typer.echo("  Install the proxy if you do not have it:")
            typer.echo("    https://cloud.google.com/sql/docs/postgres/sql-proxy#install")
            typer.echo("  Fetch the DSN with:")
            typer.echo(f"    gcloud secrets versions access latest --secret={dsn_secret} --project={project_id}")


@cli.command()
def destroy(
    config_path: Path = typer.Option(
        Path("config.yaml"), "--config-path", "-c", help="Path to YAML config file"
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
        typer.echo(f" Config file not found: {config_path}")
        raise typer.Exit(code=1)

    config = _load_config_or_exit(config_path)

    # Determine workspace name (same logic as deploy)
    workspace_name = config.get("name") or "default"

    # Find the workspace
    DEPLOYML_DIR = Path.cwd() / ".deployml" / workspace_name
    DEPLOYML_TERRAFORM_DIR = DEPLOYML_DIR / "terraform"
    DEPLOYML_MODULES_DIR = DEPLOYML_DIR / "terraform" / "modules"

    if not DEPLOYML_TERRAFORM_DIR.exists():
        typer.echo(f"WARNING:No workspace found for {workspace_name}")
        typer.echo(
            "Nothing to destroy - infrastructure may already be cleaned up."
        )
        return

    _validate_deploy_config_or_exit(config)

    # Extract project info
    cloud = config["provider"]["name"]
    if cloud == "gcp":
        project_id = config["provider"]["project_id"]

    # Confirmation unless auto-approve

    typer.echo(f"\nWARNING: About to DESTROY infrastructure for: {workspace_name}")
    typer.echo(f" Workspace: {DEPLOYML_DIR}")
    typer.echo(f"🌐 Project: {project_id}")
    typer.echo("This will permanently delete all resources!")

    if not (
        yes or typer.confirm("Are you sure you want to destroy all resources?")
    ):
        typer.echo(" Destroy cancelled")
        return

    try:
        typer.echo(f" Destroying infrastructure...")

        # Set GCP project
        subprocess.run(
            ["gcloud", "config", "set", "project", project_id],
            cwd=DEPLOYML_TERRAFORM_DIR,
        )

        # Shut down Cloud Run services first to close any open DB connections
        # before attempting to destroy Cloud SQL — otherwise active connections
        # prevent database/user deletion and the destroy fails.
        region = config.get("provider", {}).get("region", "us-central1")
        cr_result = subprocess.run(
            ["gcloud", "run", "services", "list",
             "--project", project_id,
             "--region", region,
             "--format", "value(metadata.name)"],
            capture_output=True, text=True
        )
        if cr_result.returncode == 0:
            services = [s.strip() for s in cr_result.stdout.splitlines() if s.strip()]
            for service in services:
                typer.echo(f" Deleting Cloud Run service: {service}")
                subprocess.run(
                    ["gcloud", "run", "services", "delete", service,
                     "--project", project_id,
                     "--region", region,
                     "--quiet"],
                    capture_output=True,
                )

        # Remove Cloud SQL databases and user from Terraform state so Terraform
        # doesn't try to delete them individually — the instance deletion handles
        # that automatically, avoiding active-connection errors on destroy.
        state_result = subprocess.run(
            ["terraform", "state", "list"],
            cwd=DEPLOYML_TERRAFORM_DIR,
            capture_output=True,
            text=True,
        )
        if state_result.returncode == 0:
            resources_to_remove = [
                r.strip() for r in state_result.stdout.splitlines()
                if any(x in r for x in [
                    "google_sql_database.",
                    "google_sql_user.",
                ])
            ]
            for resource in resources_to_remove:
                typer.echo(f" Removing from state: {resource}")
                subprocess.run(
                    ["terraform", "state", "rm", resource],
                    cwd=DEPLOYML_TERRAFORM_DIR,
                    capture_output=True,
                )

        # Build destroy command
        cmd = ["terraform", "destroy", "--auto-approve"]

        # Run destroy
        result = subprocess.run(cmd, cwd=DEPLOYML_TERRAFORM_DIR, check=False)

        if result.returncode == 0:
            typer.echo(" Infrastructure destroyed successfully!")

            # Clean up the Artifact Registry repo created by build-images.
            # Terraform does not manage it, so without this it lingers and bills.
            region = config.get("provider", {}).get("region", "us-central1")
            ar_repo = "mlops-images"
            typer.echo(f" Removing Artifact Registry repo {ar_repo}...")
            subprocess.run(
                ["gcloud", "artifacts", "repositories", "delete", ar_repo,
                 "--location", region, "--project", project_id, "--quiet"],
                capture_output=True,
            )

            # Clean up the Cloud Build staging bucket that `gcloud builds submit`
            # auto-creates during build-images. It is not Terraform-managed and
            # accumulates source tarballs across cycles. Best-effort; Cloud Build
            # recreates it on the next build if needed.
            cb_bucket = f"gs://{project_id}_cloudbuild"
            typer.echo(f" Removing Cloud Build staging bucket {cb_bucket}...")
            subprocess.run(
                ["gcloud", "storage", "rm", "--recursive", cb_bucket, "--quiet"],
                capture_output=True,
            )

            if clean_workspace:
                typer.echo(" Cleaning workspace...")
                shutil.rmtree(DEPLOYML_DIR)
                typer.echo(" Workspace cleaned")
            elif yes or typer.confirm("Clean up Terraform state files?"):
                # --yes propagates to the cleanup confirm so scripted runs do not hang
                cleanup_terraform_files(DEPLOYML_TERRAFORM_DIR)
        else:
            # PRESERVE state on partial failure so a re-run can reconcile.
            typer.secho(
                f"\n Destroy failed with exit code {result.returncode}. "
                "Terraform state preserved at:",
                fg=typer.colors.RED,
            )
            typer.echo(f"   {DEPLOYML_TERRAFORM_DIR}")
            typer.echo("\nRecovery:")
            typer.echo("  1. Inspect residual resources: gcloud asset search-all-resources "
                       f"--scope=projects/{project_id}")
            typer.echo(f"  2. Re-run: deployml destroy --yes")
            typer.echo(f"  3. Or delete the whole project: gcloud projects delete {project_id}")
            raise typer.Exit(code=1)

    except Exception as e:
        typer.echo(f" Error during destroy: {e}")
        raise typer.Exit(code=1)


@cli.command()
def status(
    config_path: Path = typer.Option(
        Path("config.yaml"), "--config-path", "-c", help="Path to YAML config file"
    ),
):
    """
    Show the current workspace, whether a deployment exists, and the latest service URLs.
    """
    if not config_path.exists():
        typer.echo(f" Config file not found: {config_path}")
        raise typer.Exit(code=1)
    config = _load_config_or_exit(config_path)
    workspace_name = config.get("name") or "default"
    deployml_dir = Path.cwd() / ".deployml" / workspace_name
    tf_dir = deployml_dir / "terraform"
    typer.echo(f"Workspace: {workspace_name}")
    typer.echo(f"Path: {deployml_dir}")
    if not tf_dir.exists():
        typer.secho("Status: not deployed (no terraform workspace found)", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)
    marker = deployml_dir / ".project_id"
    if marker.exists():
        typer.echo(f"Project: {marker.read_text().strip()}")
    out_proc = subprocess.run(
        ["terraform", "output", "-json"],
        cwd=tf_dir, capture_output=True, text=True,
    )
    if out_proc.returncode == 0 and out_proc.stdout.strip():
        try:
            outputs = json.loads(out_proc.stdout)
            urls = {k: v.get("value") for k, v in outputs.items() if isinstance(v.get("value"), str) and v.get("value", "").startswith("http")}
            if urls:
                typer.secho("Status: deployed", fg=typer.colors.GREEN)
                for k, v in urls.items():
                    typer.echo(f"  {k}: {v}")
            else:
                typer.secho("Status: workspace exists but no URL outputs found", fg=typer.colors.YELLOW)
        except Exception:
            typer.secho("Status: workspace exists but terraform output is not parseable", fg=typer.colors.YELLOW)
    else:
        typer.secho("Status: workspace exists but terraform output is empty", fg=typer.colors.YELLOW)


@cli.command()
def teardown(
    action: str = typer.Argument(..., help="Action: cancel, status, update, or schedule"),
    config_path: Path = typer.Option(
        ..., "--config-path", "-c", help="Path to YAML config file"
    ),
    hours: int = typer.Option(
        24, "--hours", help="Hours until teardown. Used by schedule and update."
    ),
):
    """
    Manage auto-teardown: cancel scheduled teardown, check status, update schedule, or schedule new teardown.
    """
    if not config_path.exists():
        typer.echo(f" Config file not found: {config_path}")
        raise typer.Exit(code=1)

    config = _load_config_or_exit(config_path)
    workspace_name = config.get("name") or "default"
    DEPLOYML_DIR = Path.cwd() / ".deployml" / workspace_name

    if action == "cancel":
        cancel_teardown(config, DEPLOYML_DIR, workspace_name)
    elif action == "status":
        show_teardown_status(config, DEPLOYML_DIR, workspace_name)
    elif action == "update":
        update_teardown_schedule(config, DEPLOYML_DIR, workspace_name, hours)
    elif action == "schedule":
        schedule_teardown(config, DEPLOYML_DIR, workspace_name, hours)
    else:
        typer.echo(f" Unknown action: {action}. Use: cancel, status, update, or schedule")
        raise typer.Exit(code=1)


def cancel_teardown(config: dict, deployml_dir: Path, workspace_name: str):
    """Cancel scheduled teardown."""
    project_id = config["provider"]["project_id"]
    region = config["provider"]["region"]
    
    # Delete Cloud Scheduler job. Cloud Scheduler uses --location, not --region.
    # Earlier code passed --region which gcloud rejects, so cancel silently failed.
    scheduler_job_name = f"deployml-teardown-{workspace_name}"
    result = subprocess.run(
        ["gcloud", "scheduler", "jobs", "delete", scheduler_job_name,
         "--project", project_id, "--location", region, "--quiet"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode == 0:
        typer.echo(" Scheduled teardown cancelled")
        # Update metadata
        metadata = load_deployment_metadata(deployml_dir)
        if metadata:
            metadata["teardown_enabled"] = False
            save_deployment_metadata(deployml_dir, metadata)
    else:
        typer.echo(f"WARNING:Could not cancel teardown: {result.stderr}")
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
        typer.echo(f"WARNING:Cloud Scheduler job not found: {scheduler_job_name}")
        typer.echo("   Teardown may not be scheduled or may have already been cancelled.")
        
        # Check local metadata as fallback
        metadata = load_deployment_metadata(deployml_dir)
        if metadata and metadata.get("teardown_enabled"):
            teardown_at = datetime.fromisoformat(metadata["teardown_scheduled_at"])
            typer.echo(f"\n Local metadata shows teardown was scheduled for:")
            typer.echo(f"   {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        return
    
    # Parse Cloud Scheduler job details
    try:
        job_info = json.loads(result.stdout)
    except json.JSONDecodeError:
        typer.echo(" Failed to parse Cloud Scheduler job information")
        return
    
    # Extract information
    schedule = job_info.get("schedule", "N/A")
    time_zone = job_info.get("timeZone", "UTC")
    state = job_info.get("state", "UNKNOWN")
    schedule_time = job_info.get("scheduleTime", "")
    last_attempt_time = job_info.get("lastAttemptTime", "")
    
    # Display comprehensive status
    typer.echo(" Auto-Teardown Status")
    typer.echo("=" * 60)
    
    # Job state
    typer.echo(f"Status: {state}")
    
    # Cron schedule
    typer.echo(f" Cron Schedule: {schedule}")
    typer.echo(f" Timezone: {time_zone}")
    
    # Next execution time
    if schedule_time:
        try:
            # Parse ISO format with Z suffix (UTC)
            time_str = schedule_time.replace('Z', '+00:00')
            next_run = datetime.fromisoformat(time_str)
            # Get current UTC time as timezone-aware
            from datetime import timezone
            now = datetime.now(timezone.utc)
            typer.echo(f" Next Execution: {next_run.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            if now < next_run:
                time_remaining = next_run - now
                hours = int(time_remaining.total_seconds() // 3600)
                minutes = int((time_remaining.total_seconds() % 3600) // 60)
                typer.echo(f"    Time Remaining: {hours}h {minutes}m")
            else:
                time_passed = now - next_run
                hours_passed = int(time_passed.total_seconds() // 3600)
                minutes_passed = int((time_passed.total_seconds() % 3600) // 60)
                typer.echo(f"   WARNING: Scheduled time passed {hours_passed}h {minutes_passed}m ago")
        except Exception as e:
            typer.echo(f" Next Execution: {schedule_time}")
    
    # Last attempt
    if last_attempt_time and last_attempt_time != "1970-01-01T00:00:00Z":
        try:
            # Parse ISO format with Z suffix (UTC)
            time_str = last_attempt_time.replace('Z', '+00:00')
            last_run = datetime.fromisoformat(time_str)
            typer.echo(f" Last Execution: {last_run.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        except Exception:
            typer.echo(f" Last Execution: {last_attempt_time}")
    else:
        typer.echo(" Last Execution: Never")
    
    # Job name for reference
    typer.echo(f"\n Job Name: {scheduler_job_name}")
    
    # Actions
    typer.echo("\n Actions:")
    typer.echo(f"   Update: deployml teardown update --config-path <config-file>")
    typer.echo(f"   Cancel: deployml teardown cancel --config-path <config-file>")
    typer.echo(f"   View in Console: https://console.cloud.google.com/cloudscheduler/jobs/edit/{region}/{scheduler_job_name}?project={project_id}")


def update_teardown_schedule(config: dict, deployml_dir: Path, workspace_name: str, duration_hours: int = 24):
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
        typer.echo(f" Cloud Scheduler job not found: {scheduler_job_name}")
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
    typer.echo(" Update Teardown Schedule")
    typer.echo("=" * 60)
    
    # Show current schedule
    try:
        schedule_time = job_info.get("scheduleTime", "")
        if schedule_time:
            time_str = schedule_time.replace('Z', '+00:00')
            current_time = datetime.fromisoformat(time_str)
            typer.echo(f" Current Schedule: {current_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    except Exception:
        pass
    
    # Duration is now passed in via CLI flag instead of interactive prompt.
    if duration_hours < 0:
        typer.echo(" Duration must be positive")
        raise typer.Exit(code=1)
    
    # Calculate new teardown time
    from datetime import timezone
    now = datetime.now(timezone.utc)
    teardown_at = now + timedelta(hours=duration_hours)
    # Use UTC timestamp directly to avoid timezone issues
    teardown_scheduled_timestamp = int(teardown_at.timestamp())
    new_cron_schedule = calculate_cron_from_timestamp(teardown_scheduled_timestamp)
    
    typer.echo(f"\n New Schedule: {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Update Cloud Scheduler job
    typer.echo("\n Updating Cloud Scheduler job...")
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
        typer.echo(f" Failed to update schedule: {update_result.stderr}")
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
                typer.echo(f"\n Teardown schedule updated successfully!")
                typer.echo(f"   Scheduled time: {actual_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                typer.echo(f"   Cron schedule: {updated_schedule}")
                
                # Check if it matches what we intended
                if actual_time.strftime('%Y-%m-%d %H:%M') != teardown_at.strftime('%Y-%m-%d %H:%M'):
                    typer.echo(f"\nWARNING: Warning: Scheduled time differs from intended time")
                    typer.echo(f"   Intended: {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    typer.echo(f"   Actual: {actual_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            else:
                typer.echo(f" Teardown schedule updated successfully!")
                typer.echo(f"   Cron schedule: {updated_schedule}")
        except Exception as e:
            typer.echo(f" Teardown schedule updated (verification failed: {e})")
    else:
        typer.echo(f" Teardown schedule updated successfully!")
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


def schedule_teardown(config: dict, deployml_dir: Path, workspace_name: str, duration_hours: int = 24):
    """Schedule a new teardown."""
    from datetime import timezone as _tz
    deployed_at = datetime.now(_tz.utc)
    teardown_at = deployed_at + timedelta(hours=duration_hours)
    
    metadata = {
        "deployed_at": deployed_at.isoformat(),
        "teardown_scheduled_at": teardown_at.isoformat(),
        "teardown_enabled": True,
        "duration_hours": duration_hours
    }
    save_deployment_metadata(deployml_dir, metadata)
    
    typer.echo(f" Teardown scheduled for: {teardown_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    typer.echo("WARNING:Note: This only updates local metadata. To actually schedule teardown,")
    typer.echo("   you need to redeploy with teardown.enabled: true in your config.")


@cli.command()
def init(
    provider: str = typer.Option(
        ..., "--provider", "-p", help="Cloud provider: gcp, aws, or azure"
    ),
    project_id: str = typer.Option(
        "", "--project-id", "-j", help="Project ID (for GCP)"
    ),
    path: Path = typer.Option(
        Path.cwd(),
        "--path",
        help="Directory where project should be initialized.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Overwrite existing docker folder if it exists.",
    ),
):
    """
    Initialize cloud project by enabling required APIs/services before deployment.

    This creates:
      - docker/ folder with Dockerfile templates
      - config.yaml template
    """
    if provider == "gcp":
        if not project_id:
            typer.echo(" --project-id is required for GCP.")
            raise typer.Exit(code=1)
        if not check_gcp_auth():
            typer.secho(" gcloud is not authenticated. Run: gcloud auth login", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        if not check_gcp_adc():
            typer.secho(" Application Default Credentials missing. Run: gcloud auth application-default login", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        if not validate_gcp_project(project_id):
            typer.secho(f" Project '{project_id}' not found or not accessible by your gcloud account.", fg=typer.colors.RED)
            typer.echo("   Verify with: gcloud projects describe " + project_id)
            raise typer.Exit(code=1)
        typer.echo(
            f" Enabling required GCP APIs for project: {project_id} ..."
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
            typer.echo(" All required GCP APIs are enabled.")
        else:
            typer.echo(" Failed to enable one or more GCP APIs.")
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
        typer.echo(f" Unknown provider: {provider}")
        raise typer.Exit(code=1)
    
    project_root = Path(path)
    try:
        project_root.mkdir(parents=True, exist_ok=True)

        # ----------------------------------------
        # Create docker folder
        # ----------------------------------------
        _create_docker_folder(project_root, overwrite=overwrite)

        # ----------------------------------------
        # Create config.yaml
        # ----------------------------------------
        config_path = project_root / "config.yaml"

        if config_path.exists() and not overwrite:
            raise FileExistsError(
                f"{config_path} already exists. Use --overwrite to replace."
            )

        # Write a runnable starter config so the user can deploy immediately
        # after build-images. Earlier code wrote a Python set literal here,
        # which yaml.dump serialized as `!!set` and broke deploy.
        if provider == "gcp":
            config_template = {
                "name": f"{provider}-mlops-stack-mlflow",
                "provider": {
                    "name": provider,
                    "project_id": project_id,
                    "region": "us-west1",
                    "image_tag": f"v{get_version()}",
                },
                "deployment": {"type": "cloud_run"},
                "stack": [
                    {"experiment_tracking": {"name": "mlflow", "params": {"service_name": "mlflow-server"}}},
                    {"artifact_tracking": {"name": "mlflow", "params": {"artifact_bucket": f"mlflow-artifacts-{project_id}"}}},
                    {"model_registry": {"name": "mlflow", "params": {"backend_store_uri": "postgresql"}}},
                    {"model_serving": {"name": "fastapi", "params": {"service_name": "fastapi-mlflow-server"}}},
                    {"model_monitoring": {"name": "grafana", "params": {"service_name": "grafana-server"}}},
                ],
            }
        else:
            # AWS and Azure scaffolds. The full stack is not yet implemented for
            # these providers, but the file is at least valid YAML the user can extend.
            config_template = {
                "name": f"{provider}-mlops-stack",
                "provider": {"name": provider, "project_id": project_id, "region": ""},
                "deployment": {"type": ""},
                "stack": [],
            }

        with open(config_path, "w") as f:
            yaml.dump(config_template, f, sort_keys=False, default_flow_style=False)

        typer.secho("Project initialized successfully.", fg=typer.colors.GREEN)
        typer.echo()
        typer.echo("Created:")
        typer.echo("  - docker/")
        typer.echo(f"  - config.yaml  (runnable starter for {provider})")
        typer.echo()
        typer.echo("Next steps:")
        typer.echo("  1. Review config.yaml")
        typer.echo("  2. deployml build-images --create-repo")
        typer.echo("  3. deployml deploy --verbose")

    except Exception as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED)
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
    namespace: Optional[str] = typer.Option(
        None, "--namespace", "-n",
        help="Kubernetes namespace to deploy into. Defaults to the default namespace. "
        "Use the same namespace for MLflow and FastAPI so service DNS resolves."
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

    success = deploy_fastapi_to_minikube(manifest_dir, image_name=image_name, namespace=namespace)
    
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
        None, "--backend-store-uri", "-b", help="Backend store URI. Default sqlite on the mounted PVC."
    ),
    artifact_root: Optional[str] = typer.Option(
        None, "--artifact-root", "-a", help="Artifact root path (defaults to /mlflow-artifacts)"
    ),
    start_cluster: bool = typer.Option(
        True, "--start-cluster/--no-start-cluster",
        help="Start minikube cluster if not running"
    ),
    persistent_storage: bool = typer.Option(
        True, "--persistent-storage/--ephemeral-storage",
        help="Mount a PersistentVolumeClaim so sqlite and artifacts survive pod restarts. Default on."
    ),
    pvc_size: str = typer.Option(
        "5Gi", "--pvc-size", help="PVC size when --persistent-storage is on."
    ),
):
    """
    Initialize minikube and generate MLflow Kubernetes manifests.
    Creates deployment.yaml, service.yaml, and (when --persistent-storage)
    pvc.yaml in the specified directory.
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
        artifact_root=artifact_root,
        use_pvc=persistent_storage,
        pvc_size=pvc_size,
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
    namespace: Optional[str] = typer.Option(
        None, "--namespace", "-n",
        help="Kubernetes namespace to deploy into. Defaults to the default namespace. "
        "Use the same namespace for MLflow and FastAPI so service DNS resolves."
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

    success = deploy_mlflow_to_minikube(manifest_dir, image_name=image_name, namespace=namespace)
    
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
    namespace: Optional[str] = typer.Option(
        None, "--namespace", "-n",
        help="Kubernetes namespace to deploy into. Defaults to the default namespace. "
        "Use the same namespace for MLflow and FastAPI so service DNS resolves."
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
        namespace=namespace,
    )

    if not success:
        raise typer.Exit(code=1)


@cli.command("gke-cluster-create")
def gke_cluster_create(
    cluster: str = typer.Option(..., "--cluster", "-c", help="Cluster name"),
    project: str = typer.Option(..., "--project", "-p", help="GCP project ID"),
    region: str = typer.Option("us-west1", "--region", "-r", help="Region for the cluster"),
    autopilot: bool = typer.Option(
        True, "--autopilot/--standard",
        help="Use GKE Autopilot (default) or a standard zonal cluster.",
    ),
):
    """
    Create a GKE cluster. Thin wrapper around `gcloud container clusters create`.
    Autopilot is the default and the cheapest path for occasional testing.
    """
    if autopilot:
        cmd = [
            "gcloud", "container", "clusters", "create-auto", cluster,
            "--region", region, "--project", project,
        ]
    else:
        cmd = [
            "gcloud", "container", "clusters", "create", cluster,
            "--region", region, "--project", project,
            "--num-nodes", "1", "--machine-type", "e2-medium",
        ]
    typer.echo(f" Creating {'Autopilot' if autopilot else 'standard'} cluster {cluster}...")
    typer.echo("   This typically takes 5 to 10 minutes.")
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        raise typer.Exit(code=1)
    typer.secho(f" Cluster {cluster} created.", fg=typer.colors.GREEN)
    typer.echo(f"   Next: deployml gke-init --output-dir manifests --image gcr.io/{project}/... --project {project}")


@cli.command("gke-destroy")
def gke_destroy(
    manifest_dir: Path = typer.Option(
        ..., "--manifest-dir", "-d",
        help="Directory containing deployment.yaml and service.yaml that were applied"
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
    namespace: Optional[str] = typer.Option(
        None, "--namespace", "-n",
        help="Namespace the manifests were applied to. Defaults to the default namespace."
    ),
    delete_cluster: bool = typer.Option(
        False, "--delete-cluster",
        help="Also delete the GKE cluster after removing manifests."
    ),
    keep_images: bool = typer.Option(
        False, "--keep-images",
        help="Keep the gcr.io image this workload used. By default it is deleted so "
        "teardown is fully self-cleaning, matching the Cloud Run destroy behavior."
    ),
):
    """
    Remove deployml-managed manifests from a GKE cluster. Optionally delete the cluster.

    Mirrors the Cloud Run `destroy` command for the GKE flow. Without `--delete-cluster`,
    only the deployed Deployments and Services are removed; the cluster stays up. By
    default the gcr.io image referenced by the deployment is also deleted; pass
    --keep-images to keep it for a quick redeploy.
    """
    if not manifest_dir.exists():
        typer.echo(f"Directory not found: {manifest_dir}")
        raise typer.Exit(code=1)

    if not zone and not region:
        typer.echo("Either --zone or --region must be provided")
        raise typer.Exit(code=1)

    from deployml.utils.kubernetes_gke import connect_to_gke_cluster

    if not connect_to_gke_cluster(project, cluster, zone, region):
        raise typer.Exit(code=1)

    # Delete in reverse order: service, then deployment, then PVC last. The PVC
    # is deleted explicitly because its backing PersistentDisk bills even after
    # the workload is gone (GKE's default storageclass reclaims on PVC delete).
    ns = ["-n", namespace] if namespace and namespace != "default" else []
    for fname in ["service.yaml", "deployment.yaml", "pvc.yaml"]:
        f = manifest_dir / fname
        if f.exists():
            typer.echo(f" Deleting {fname}...")
            result = subprocess.run(
                ["kubectl", "delete", "-f", str(f), "--ignore-not-found"] + ns,
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                typer.echo(f"   {result.stdout.strip() or 'deleted'}")
            else:
                typer.secho(f"   {result.stderr.strip()}", fg=typer.colors.YELLOW)

    # Remove the gcr.io image this workload referenced so it does not linger and
    # bill, mirroring the Cloud Run destroy that removes the Artifact Registry repo.
    # Best-effort; --keep-images opts out for iterative redeploys.
    if not keep_images:
        dep = manifest_dir / "deployment.yaml"
        image = ""
        if dep.exists():
            try:
                doc = yaml.safe_load(dep.read_text())
                image = doc["spec"]["template"]["spec"]["containers"][0].get("image", "")
            except Exception:
                image = ""
        if image.startswith("gcr.io/"):
            typer.echo(f" Removing image {image}...")
            subprocess.run(
                ["gcloud", "container", "images", "delete", image,
                 "--force-delete-tags", "--quiet", "--project", project],
                capture_output=True,
            )

    if delete_cluster:
        typer.echo(f"\n Deleting cluster {cluster}...")
        cmd = ["gcloud", "container", "clusters", "delete", cluster,
               "--project", project, "--quiet"]
        if zone:
            cmd += ["--zone", zone]
        else:
            cmd += ["--region", region]
        # Deleting the Services above starts LoadBalancer teardown operations.
        # GKE refuses a cluster delete while one is in flight with a 400
        # "incompatible operation", which would otherwise leave the cluster
        # billing. Retry until the in-flight operation clears.
        loc = zone or region
        for attempt in range(6):
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                typer.echo(f" Cluster {cluster} deleted")
                break
            if "incompatible operation" in (result.stderr or "").lower():
                typer.echo("   Cluster busy with another operation, retrying in 20s...")
                time.sleep(20)
                continue
            typer.secho(f" Cluster delete failed: {result.stderr}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        else:
            typer.secho(
                f" Cluster delete still blocked after retries. Re-run: "
                f"gcloud container clusters delete {cluster} --location {loc} "
                f"--project {project} --quiet",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)
    else:
        typer.echo("\n Cluster left running. Pass --delete-cluster to also remove it.")


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
        "mlflow", "--service", "-s", help="Service type: mlflow, fastapi, or all"
    ),
    mlflow_uri: Optional[str] = typer.Option(
        None, "--mlflow-uri", "-m", help="MLflow URI (for FastAPI). Only used when service is fastapi."
    ),
    mlflow_image: Optional[str] = typer.Option(
        None, "--mlflow-image", help="MLflow image. Required when --service all. Defaults to --image when not provided."
    ),
):
    """
    Generate Kubernetes manifests for GKE.

    With --service mlflow or --service fastapi, renders one set of manifests in
    output_dir. With --service all, renders mlflow into output_dir/mlflow and
    fastapi into output_dir/fastapi so you can deploy both halves of the stack.
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
    elif service == "all":
        ml_img = mlflow_image or image
        ml_dir = output_dir / "mlflow"
        fa_dir = output_dir / "fastapi"
        generate_mlflow_manifests_gke(
            output_dir=ml_dir,
            image=ml_img,
            project_id=project,
            push_image=not ml_img.startswith("gcr.io/"),
        )
        # FastAPI will reach MLflow via the in-cluster service DNS.
        in_cluster_mlflow = mlflow_uri or "http://mlflow-service:5000"
        generate_fastapi_manifests_gke(
            output_dir=fa_dir,
            image=image,
            project_id=project,
            mlflow_tracking_uri=in_cluster_mlflow,
            push_image=not image.startswith("gcr.io/"),
        )
        typer.echo("\nNext steps:")
        typer.echo(f"  1. deployml gke-deploy -d {ml_dir} -c CLUSTER -p {project} -r REGION")
        typer.echo(f"  2. deployml gke-deploy -d {fa_dir} -c CLUSTER -p {project} -r REGION")
    else:
        typer.echo(f"Unknown service: {service}. Use 'mlflow', 'fastapi', or 'all'")
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

    config = _load_config_or_exit(config_path)
    
    # Validate deployment type
    deployment_type = config.get("deployment", {}).get("type")
    if deployment_type != "gke":
        typer.echo(f"This command is only for GKE deployments. Found: {deployment_type}")
        raise typer.Exit(code=1)
    
    workspace_name = config.get("name") or "default"
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
    # Optional namespace; MLflow and FastAPI share it so service DNS resolves.
    gke_namespace = gke_config.get("namespace")

    if not cluster_name:
        typer.echo("GKE cluster_name must be specified in config.gke.cluster_name")
        raise typer.Exit(code=1)
    
    if not zone and not region_gke:
        typer.echo("Either config.gke.zone or config.gke.region must be specified")
        raise typer.Exit(code=1)
    
    typer.echo(f" Applying GKE manifests")
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
            namespace=gke_namespace,
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
            namespace=gke_namespace,
        ):
            deployed_any = True
        else:
            raise typer.Exit(code=1)

    if deployed_any:
        typer.echo("\n GKE deployment complete!")
    else:
        typer.echo("\n No manifests found to deploy")
        typer.echo(f"   Check: {manifests_dir}")


@cli.command("build-images")
def build_images_command(
    config_path: Path = typer.Option(
        Path("config.yaml"),
        "--config-path",
        "-c",
        help="Path to YAML config file. Used to infer project and region automatically.",
    ),
    docker_root: Optional[Path] = typer.Option(
        None,
        "--docker-root",
        "-d",
        help="Path to folder containing subfolders with Dockerfiles. Defaults to the built-in deployml docker directory.",
    ),
    gcp_project: Optional[str] = typer.Option(
        None,
        "--gcp-project",
        "-p",
        help="If provided, images will be built using Cloud Build in this GCP project.",
    ),
    region: Optional[str] = typer.Option(
        None,
        "--region",
        help="GCP region for Artifact Registry. Inferred from config if not set.",
    ),
    repository: str = typer.Option(
        "mlops-images",
        "--repository",
        help="Artifact Registry repository name.",
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        "-t",
        help="Image tag to apply. Defaults to config.provider.image_tag or v{deployml_version}.",
    ),
    create_repo: bool = typer.Option(
        False,
        "--create-repo",
        help="Create the Artifact Registry repository if it does not exist (GCP mode only).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be built without executing Docker or gcloud commands.",
    ),
    platform: Optional[str] = typer.Option(
        None,
        "--platform",
        help="Local build platform. Defaults to host arch so images run on a local "
        "minikube node. Pass linux/amd64 only for a manual amd64 push. Ignored in GCP mode.",
    ),
):
    """
    Build all Docker images found in subdirectories of the given folder.

    Local mode:
        Builds using Docker.

    GCP mode:
        Uses Cloud Build and pushes to Artifact Registry.

    --dry-run prints commands without executing them.
    """

    if config_path and config_path.exists():
        config = _load_config_or_exit(config_path)
        if not gcp_project:
            gcp_project = config.get("provider", {}).get("project_id")
        if not region:
            region = config.get("provider", {}).get("region", "us-central1")
        if not tag:
            tag = config.get("provider", {}).get("image_tag")

    if not region:
        region = "us-central1"
    if not tag:
        tag = f"v{get_version()}"

    if create_repo and not gcp_project:
        typer.secho(
            "--create-repo can only be used with --gcp-project.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    if docker_root is None:
        docker_root = Path(str(pkg_resources.files("deployml") / "docker"))
        typer.echo(f"Using built-in docker directory: {docker_root}")

    try:
        build_images(
            docker_root=docker_root,
            gcp_project_id=gcp_project,
            region=region,
            repository=repository,
            tag=tag,
            create_repo=create_repo,
            dry_run=dry_run,
            platform=platform,
        )

        if not dry_run:
            typer.secho("Image build completed successfully.", fg=typer.colors.GREEN)

    except Exception as e:
        typer.secho(f"Error building images: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

def main():
    """
    Entry point for the DeployML CLI.
    """
    cli()


if __name__ == "__main__":
    main()
