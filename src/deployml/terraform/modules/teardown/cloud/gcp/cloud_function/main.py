"""
Cloud Function to automatically teardown DeployML infrastructure.
Triggered by Cloud Scheduler.

This function uses the DeployML CLI approach: it calls terraform destroy
on the workspace directory stored in GCS, or uses terraform remote state.
"""
import os
import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from google.cloud import storage as gcs
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def teardown_infrastructure(request):
    """
    Cloud Function entry point.
    Expects JSON payload with:
    - workspace_name: Name of the workspace to destroy
    - project_id: GCP project ID
    - terraform_files_bucket: (optional) GCS bucket with Terraform files
    - terraform_state_bucket: (optional) GCS bucket with Terraform state
    """
    try:
        # Parse request
        request_json = request.get_json(silent=True)
        if not request_json:
            return {'error': 'No JSON payload provided'}, 400
        
        workspace_name = request_json.get('workspace_name')
        project_id = request_json.get('project_id')
        terraform_files_bucket = request_json.get('terraform_files_bucket', '')
        terraform_state_bucket = request_json.get('terraform_state_bucket', '')
        
        if not workspace_name or not project_id:
            return {'error': 'Missing required fields: workspace_name, project_id'}, 400
        
        logger.info(f"Starting teardown for workspace: {workspace_name}")
        
        # Create temporary directory for terraform
        with tempfile.TemporaryDirectory() as tmpdir:
            terraform_dir = Path(tmpdir) / "terraform"
            terraform_dir.mkdir(parents=True, exist_ok=True)
            
            # Download terraform files from GCS if provided
            if terraform_files_bucket:
                download_terraform_files(terraform_files_bucket, workspace_name, terraform_dir)
            
            # Download terraform state if stored in GCS
            if terraform_state_bucket:
                download_terraform_state(terraform_state_bucket, workspace_name, terraform_dir)
            
            # Install terraform if not available (Cloud Functions don't have it by default)
            # We'll use a workaround: call terraform via a container or use gcloud commands
            # For now, we'll assume terraform is available or use alternative method
            
            # Set GCP project
            try:
                subprocess.run(
                    ['gcloud', 'config', 'set', 'project', project_id],
                    cwd=terraform_dir,
                    check=True,
                    capture_output=True,
                    timeout=30
                )
            except Exception as e:
                logger.warning(f"Could not set gcloud project: {e}")
            
            # Try to initialize terraform (if files exist)
            if (terraform_dir / "main.tf").exists():
                # Initialize terraform
                init_result = subprocess.run(
                    ['terraform', 'init'],
                    cwd=terraform_dir,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if init_result.returncode != 0:
                    logger.warning(f"Terraform init failed: {init_result.stderr}")
                    # Try alternative: use terraform with remote state only
                    return destroy_via_remote_state(project_id, workspace_name, terraform_state_bucket)
                
                # Run terraform destroy
                destroy_result = subprocess.run(
                    ['terraform', 'destroy', '-auto-approve'],
                    cwd=terraform_dir,
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minutes timeout
                )
                
                if destroy_result.returncode == 0:
                    logger.info(f"Successfully destroyed infrastructure for {workspace_name}")
                    return {
                        'status': 'success',
                        'message': f'Infrastructure destroyed for workspace: {workspace_name}',
                        'workspace': workspace_name
                    }, 200
                else:
                    logger.error(f"Terraform destroy failed: {destroy_result.stderr}")
                    return {
                        'status': 'error',
                        'message': f'Destroy failed: {destroy_result.stderr}',
                        'workspace': workspace_name
                    }, 500
            else:
                # No terraform files found, try alternative approach
                logger.info("No terraform files found, attempting alternative teardown method")
                return destroy_via_remote_state(project_id, workspace_name, terraform_state_bucket)
                
    except subprocess.TimeoutExpired:
        logger.error("Terraform operation timed out")
        return {
            'status': 'error',
            'message': 'Teardown operation timed out'
        }, 500
    except Exception as e:
        logger.error(f"Error in teardown function: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }, 500


def download_terraform_files(bucket_name: str, workspace_name: str, terraform_dir: Path):
    """Download Terraform files from GCS bucket."""
    try:
        storage_client = gcs.Client()
        bucket = storage_client.bucket(bucket_name)
        
        # List and download all terraform files
        prefix = f"{workspace_name}/terraform/"
        blobs = bucket.list_blobs(prefix=prefix)
        
        for blob in blobs:
            # Get relative path
            relative_path = blob.name.replace(prefix, "")
            if relative_path:  # Skip the prefix itself
                local_path = terraform_dir / relative_path
                local_path.parent.mkdir(parents=True, exist_ok=True)
                blob.download_to_filename(local_path)
                logger.info(f"Downloaded {blob.name} to {local_path}")
    except Exception as e:
        logger.warning(f"Could not download terraform files: {e}")


def download_terraform_state(bucket_name: str, workspace_name: str, terraform_dir: Path):
    """Download Terraform state files from GCS bucket."""
    try:
        storage_client = gcs.Client()
        bucket = storage_client.bucket(bucket_name)
        
        # Download terraform.tfstate if exists
        blob_name = f"{workspace_name}/terraform/terraform.tfstate"
        blob = bucket.blob(blob_name)
        if blob.exists():
            blob.download_to_filename(terraform_dir / "terraform.tfstate")
            logger.info(f"Downloaded terraform state from {blob_name}")
    except Exception as e:
        logger.warning(f"Could not download terraform state: {e}")


def destroy_via_remote_state(project_id: str, workspace_name: str, state_bucket: str):
    """
    Alternative teardown method using terraform with remote state backend.
    Creates a minimal terraform config that uses remote state.
    """
    try:
        logger.info("Attempting teardown via remote state")
        # This would require creating a backend config and running terraform destroy
        # For now, return an error suggesting manual teardown
        return {
            'status': 'error',
            'message': f'Could not automatically teardown. Please run: deployml destroy --config-path <config-file>',
            'workspace': workspace_name
        }, 500
    except Exception as e:
        logger.error(f"Remote state teardown failed: {e}")
        return {
            'status': 'error',
            'message': str(e)
        }, 500