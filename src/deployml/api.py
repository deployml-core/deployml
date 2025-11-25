"""
DeployML Python API

Programmatic interface for managing DeployML deployments and teardown schedules.

Example usage:
    import deployml.api as api
    
    # Get teardown status
    status = api.get_teardown_status(
        project_id="my-project",
        region="us-west1",
        workspace_name="my-stack"
    )
    
    # Update teardown schedule
    result = api.update_teardown_schedule(
        project_id="my-project",
        region="us-west1",
        workspace_name="my-stack",
        duration_hours=6
    )
    
    # Cancel teardown
    api.cancel_teardown(
        project_id="my-project",
        region="us-west1",
        workspace_name="my-stack"
    )
"""
import json
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from .utils.teardown import (
    calculate_cron_from_timestamp,
    load_deployment_metadata,
    save_deployment_metadata
)


def get_teardown_status(
    project_id: str,
    region: str,
    workspace_name: str,
    deployml_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Get teardown status from Cloud Scheduler.
    
    Args:
        project_id: GCP project ID
        region: GCP region
        workspace_name: Workspace name
        deployml_dir: Optional path to deployment directory for metadata
    
    Returns:
        Dictionary with status information including:
        - exists: bool - Whether the scheduler job exists
        - state: str - Job state (ENABLED, PAUSED, etc.)
        - schedule: str - Cron schedule
        - schedule_time: datetime - Next scheduled execution time
        - time_zone: str - Timezone
        - last_attempt_time: Optional[datetime] - Last execution time
        - metadata: Optional[Dict] - Local metadata if available
    """
    scheduler_job_name = f"deployml-teardown-{workspace_name}"
    
    result = subprocess.run(
        ["gcloud", "scheduler", "jobs", "describe", scheduler_job_name,
         "--project", project_id, "--location", region, "--format", "json"],
        capture_output=True,
        text=True,
    )
    
    status = {
        "exists": False,
        "scheduler_job_name": scheduler_job_name,
    }
    
    # Load local metadata if available
    if deployml_dir:
        metadata = load_deployment_metadata(deployml_dir)
        status["metadata"] = metadata
    
    if result.returncode != 0:
        return status
    
    try:
        job_info = json.loads(result.stdout)
        status["exists"] = True
        status["state"] = job_info.get("state", "UNKNOWN")
        status["schedule"] = job_info.get("schedule", "")
        status["time_zone"] = job_info.get("timeZone", "UTC")
        
        # Parse schedule time
        schedule_time = job_info.get("scheduleTime", "")
        if schedule_time:
            time_str = schedule_time.replace('Z', '+00:00')
            status["schedule_time"] = datetime.fromisoformat(time_str)
        
        # Parse last attempt time
        last_attempt_time = job_info.get("lastAttemptTime", "")
        if last_attempt_time and last_attempt_time != "1970-01-01T00:00:00Z":
            time_str = last_attempt_time.replace('Z', '+00:00')
            status["last_attempt_time"] = datetime.fromisoformat(time_str)
        
        return status
    except json.JSONDecodeError:
        return status


def update_teardown_schedule(
    project_id: str,
    region: str,
    workspace_name: str,
    duration_hours: int,
    deployml_dir: Optional[Path] = None,
    time_zone: str = "UTC"
) -> Dict[str, Any]:
    """
    Update teardown schedule programmatically.
    
    Args:
        project_id: GCP project ID
        region: GCP region
        workspace_name: Workspace name
        duration_hours: Hours until teardown
        deployml_dir: Optional path to deployment directory for metadata
        time_zone: Timezone (default: UTC)
    
    Returns:
        Dictionary with update result:
        - success: bool - Whether update succeeded
        - scheduled_time: datetime - New scheduled time
        - cron_schedule: str - Cron expression
        - error: Optional[str] - Error message if failed
    """
    scheduler_job_name = f"deployml-teardown-{workspace_name}"
    
    # Check if job exists and get current timezone
    result = subprocess.run(
        ["gcloud", "scheduler", "jobs", "describe", scheduler_job_name,
         "--project", project_id, "--location", region, "--format", "json"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        return {
            "success": False,
            "error": f"Cloud Scheduler job not found: {scheduler_job_name}"
        }
    
    # Get timezone from existing job if not provided
    try:
        job_info = json.loads(result.stdout)
        time_zone = job_info.get("timeZone", time_zone)
    except json.JSONDecodeError:
        pass
    
    # Calculate new teardown time
    now = datetime.now(timezone.utc)
    teardown_at = now + timedelta(hours=duration_hours)
    teardown_scheduled_timestamp = int(teardown_at.timestamp())
    new_cron_schedule = calculate_cron_from_timestamp(teardown_scheduled_timestamp)
    
    # Update Cloud Scheduler job
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
        return {
            "success": False,
            "error": update_result.stderr,
            "scheduled_time": teardown_at,
            "cron_schedule": new_cron_schedule
        }
    
    # Update local metadata if directory provided
    if deployml_dir:
        metadata = load_deployment_metadata(deployml_dir) or {}
        metadata.update({
            "deployed_at": metadata.get("deployed_at", now.isoformat()),
            "teardown_scheduled_at": teardown_at.isoformat(),
            "teardown_enabled": True,
            "duration_hours": duration_hours,
            "scheduler_job_name": scheduler_job_name
        })
        save_deployment_metadata(deployml_dir, metadata)
    
    return {
        "success": True,
        "scheduled_time": teardown_at,
        "cron_schedule": new_cron_schedule,
        "time_zone": time_zone
    }


def cancel_teardown(
    project_id: str,
    region: str,
    workspace_name: str,
    deployml_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Cancel scheduled teardown programmatically.
    
    Args:
        project_id: GCP project ID
        region: GCP region
        workspace_name: Workspace name
        deployml_dir: Optional path to deployment directory for metadata
    
    Returns:
        Dictionary with cancellation result:
        - success: bool - Whether cancellation succeeded
        - error: Optional[str] - Error message if failed
    """
    scheduler_job_name = f"deployml-teardown-{workspace_name}"
    
    result = subprocess.run(
        ["gcloud", "scheduler", "jobs", "delete", scheduler_job_name,
         "--project", project_id, "--location", region, "--quiet"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        return {
            "success": False,
            "error": result.stderr
        }
    
    # Update metadata if directory provided
    if deployml_dir:
        metadata = load_deployment_metadata(deployml_dir)
        if metadata:
            metadata["teardown_enabled"] = False
            save_deployment_metadata(deployml_dir, metadata)
    
    return {"success": True}


__all__ = [
    'get_teardown_status',
    'update_teardown_schedule',
    'cancel_teardown'
]

