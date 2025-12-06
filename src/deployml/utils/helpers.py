import shutil
import subprocess
from pathlib import Path
from typing import Optional
from google.cloud import storage
import random
import string
from deployml.utils.constants import ANIMAL_NAMES, FALLBACK_WORDS, TERRAFORM_DIR
import subprocess
import time
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)


def check_command(name: str) -> bool:
    """
    Check if a command is available in the system PATH.

    Args:
        name (str): The name of the command to check.

    Returns:
        bool: True if the command is found, False otherwise.
    """
    return shutil.which(name) is not None


def check(command: str) -> bool:
    """
    Alias for check_command for backward compatibility.
    """
    return check_command(command)


def check_gcp_auth() -> bool:
    """
    Check if the user is authenticated with GCP CLI.

    Returns:
        bool: True if authenticated, False otherwise.
    """
    try:
        result = subprocess.run(
            ["gcloud", "auth", "list"], capture_output=True, text=True
        )
        return "ACTIVE" in result.stdout
    except Exception:
        return False


def copy_modules_to_workspace(
    modules_dir: Path,
    stack: list | None = None,
    deployment_type: str | None = None,
    cloud: str = "gcp",
    teardown_enabled: bool = False,
) -> None:
    """
    Copy only the required Terraform module templates to the workspace directory.

    Args:
        modules_dir (Path): The destination directory for module templates.
        stack (list, optional): Stack configuration to determine which modules to copy.
        deployment_type (str, optional): The deployment type (cloud_run, cloud_vm, etc.)
                                         If None, copies all modules (backward compatibility).
        cloud (str): Cloud provider key (e.g., 'gcp', 'aws', 'azure'). Defaults to 'gcp'.
    """
    MODULE_TEMPLATES_DIR = TERRAFORM_DIR / "modules"
    if not MODULE_TEMPLATES_DIR.exists():
        raise FileNotFoundError(
            f"Module templates not found at: {MODULE_TEMPLATES_DIR}"
        )

    # If no stack provided, copy all modules (backward compatibility)
    if stack is None:
        for module_path in MODULE_TEMPLATES_DIR.iterdir():
            if module_path.is_dir():
                dest_path = modules_dir / module_path.name
                if dest_path.exists():
                    shutil.rmtree(dest_path)
                shutil.copytree(module_path, dest_path)
        return

    # Determine which modules are actually used in the stack
    used_modules = set()
    for stage in stack:
        for stage_name, tool in stage.items():
            tool_name = tool.get("name")
            if tool_name:
                used_modules.add(tool_name)
    
    # Add teardown module to used_modules if teardown is enabled
    if teardown_enabled:
        used_modules.add("teardown")

    # Only copy the modules that are being used, and only the specific deployment type
    for module_path in MODULE_TEMPLATES_DIR.iterdir():
        if module_path.is_dir() and module_path.name in used_modules:
            # Special case: always copy full cloud_sql_postgres module
            if module_path.name == "cloud_sql_postgres":
                dest_module_path = modules_dir / module_path.name
                if dest_module_path.exists():
                    shutil.rmtree(dest_module_path)
                shutil.copytree(module_path, dest_module_path)
                continue
            # Special case: always copy full teardown module (if it exists)
            if module_path.name == "teardown":
                dest_module_path = modules_dir / module_path.name
                if dest_module_path.exists():
                    shutil.rmtree(dest_module_path)
                shutil.copytree(module_path, dest_module_path)
                continue
            # Create the destination module directory
            dest_module_path = modules_dir / module_path.name
            if dest_module_path.exists():
                shutil.rmtree(dest_module_path)
            dest_module_path.mkdir(parents=True, exist_ok=True)

            # Copy only the specific deployment type if specified
            if deployment_type:
                deployment_source = (
                    module_path / "cloud" / cloud / deployment_type
                )
                if deployment_source.exists():
                    deployment_dest = (
                        dest_module_path / "cloud" / cloud / deployment_type
                    )
                    deployment_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(deployment_source, deployment_dest)
                else:
                    # Fallback: copy entire module if specific deployment type doesn't exist
                    shutil.copytree(
                        module_path, dest_module_path, dirs_exist_ok=True
                    )
            else:
                # Copy entire module if no deployment type specified
                shutil.copytree(
                    module_path, dest_module_path, dirs_exist_ok=True
                )


def bucket_exists(bucket_name: str, project_id: str) -> bool:
    """
    Check if a Google Cloud Storage bucket exists in the given project.

    Args:
        bucket_name (str): The name of the bucket to check.
        project_id (str): The GCP project ID.

    Returns:
        bool: True if the bucket exists, False otherwise.
    """
    client = storage.Client(project=project_id)
    try:
        client.get_bucket(bucket_name)
        return True
    except Exception:
        return False


def generate_unique_bucket_name(base_name: str, project_id: str) -> str:
    """
    Generate a unique GCS bucket name by appending a random suffix.

    Args:
        base_name (str): The base name for the bucket.
        project_id (str): The GCP project ID.

    Returns:
        str: A unique bucket name.
    """
    while True:
        suffix = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=6)
        )
        new_name = f"{base_name}-{suffix}"
        if not bucket_exists(new_name, project_id):
            return new_name


def generate_bucket_name(project_id: str) -> str:
    """
    Generate a random, human-readable GCS bucket name for the given project.

    Args:
        project_id (str): The GCP project ID.

    Returns:
        str: A generated bucket name.
    """
    if random.random() < 0.7:
        word = random.choice(ANIMAL_NAMES)
    else:
        word = random.choice(FALLBACK_WORDS)
    suffix = "".join(
        random.choices(string.ascii_lowercase + string.digits, k=4)
    )
    return f"{word}-bucket-{project_id}-{suffix}".replace("_", "-")


def estimate_terraform_time(plan_output: str, operation: str = "apply") -> str:
    """
    Estimate time for Terraform operations based on resource count and types.
    If PostgreSQL/Cloud SQL is present, estimate 20 minutes per instance.
    """
    import re

    # Match google_sql_database_instance resources even inside modules
    postgres_resource_pattern = (
        r"#.*google_sql_database_instance\.[^ ]+ will be created"
    )
    postgres_resources = set(re.findall(postgres_resource_pattern, plan_output))
    postgres_count = len(postgres_resources)
    if postgres_count > 0:
        total_minutes = 20 * postgres_count
        return f"~{total_minutes} minutes (Cloud SQL/PostgreSQL detected)"

    # Check for API propagation wait time
    if "time_sleep.wait_for_api_propagation" in plan_output:
        base_wait_time = 3  # Account for API propagation (2 min) + buffer
    else:
        base_wait_time = 0

    # Check for VM deployments (these take longer)
    if "google_compute_instance" in plan_output:
        base_wait_time += 3  # VMs take additional time for startup scripts

    # Otherwise, estimate by resource count
    resource_patterns = [
        r"# (\w+\.\w+) will be created",
        r"# (\w+\.\w+) will be destroyed",
        r"# (\w+\.\w+) will be updated",
        r"# (\w+\.\w+) will be replaced",
    ]
    resource_count = 0
    for pattern in resource_patterns:
        resource_count += len(re.findall(pattern, plan_output))

    if resource_count == 0:
        return f"~{max(1, base_wait_time)} minute{'s' if base_wait_time != 1 else ''}"
    elif resource_count <= 3:
        avg_time = 0.5
    elif resource_count <= 8:
        avg_time = 2
    else:
        avg_time = 5

    estimated_minutes = max(1, int(resource_count * avg_time) + base_wait_time)
    return f"~{estimated_minutes} minutes"


def cleanup_cloud_sql_resources(terraform_dir: Path, project_id: str):
    """
    Clean up Cloud SQL database and user before destroying the instance.
    """
    import subprocess
    import time as _time

    try:
        # Get the instance name from terraform state
        result = subprocess.run(
            ["terraform", "output", "-raw", "instance_connection_name"],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            instance_connection_name = result.stdout.strip()
            # Extract instance name from connection name (format: project:region:instance)
            parts = instance_connection_name.split(":")
            instance_name = parts[2] if len(parts) == 3 else instance_connection_name

            print("🗄️  Cleaning up Cloud SQL resources (terminate connections, drop DBs, drop users)...")

            # Restart instance to terminate all connections (most reliable non-interactive method)
            restart_cmd = [
                "gcloud",
                "sql",
                "instances",
                "restart",
                instance_name,
                "--project",
                project_id,
                "--quiet",
            ]
            subprocess.run(restart_cmd, capture_output=True, text=True)
            _time.sleep(5)

            # List existing databases to avoid failing on non-existent ones
            list_db_cmd = [
                "gcloud",
                "sql",
                "databases",
                "list",
                "--instance",
                instance_name,
                "--project",
                project_id,
                "--format=value(name)",
            ]
            list_proc = subprocess.run(list_db_cmd, capture_output=True, text=True)
            existing_dbs = set(list_proc.stdout.strip().splitlines()) if list_proc.returncode == 0 else set()

            # Attempt to delete known course DBs if present
            target_dbs = ["mlflow", "feast", "metrics"]
            for db_name in target_dbs:
                if db_name in existing_dbs:
                    delete_db_cmd = [
                        "gcloud",
                        "sql",
                        "databases",
                        "delete",
                        db_name,
                        "--instance",
                        instance_name,
                        "--project",
                        project_id,
                        "--quiet",
                    ]
                    # Retry a few times in case connections are still draining
                    for attempt in range(3):
                        proc = subprocess.run(delete_db_cmd, capture_output=True, text=True)
                        if proc.returncode == 0:
                            break
                        _time.sleep(5)

            # Drop common users after DBs are removed
            target_users = ["mlflow", "feast", "metrics"]
            for user in target_users:
                drop_user_cmd = [
                    "gcloud",
                    "sql",
                    "users",
                    "delete",
                    user,
                    "--instance",
                    instance_name,
                    "--project",
                    project_id,
                    "--quiet",
                ]
                subprocess.run(drop_user_cmd, capture_output=True, text=True)

            print("✅ Cloud SQL cleanup completed (best-effort)")
    except Exception as e:
        print(f"⚠️  Cloud SQL cleanup failed (continuing with destroy): {e}")


def cleanup_terraform_files(terraform_dir: Path):
    """
    Clean up Terraform state and lock files from the specified directory.
    """
    import shutil

    cleanup_files = [
        ".terraform",
        "terraform.tfstate",
        "terraform.tfstate.backup",
        ".terraform.lock.hcl",
    ]

    for file in cleanup_files:
        file_path = terraform_dir / file
        if file_path.exists():
            if file_path.is_dir():
                shutil.rmtree(file_path)
            else:
                file_path.unlink()
            print(f"🗑️  Removed: {file}")

    print("✅ Cleanup completed")


def run_terraform_with_loading_bar(cmd, cwd, estimated_minutes, stack=None):
    """
    Run a subprocess command with a loading bar using rich.progress.
    Progress messages are based on the stack/resources from the YAML config if provided.
    Args:
        cmd (list): Command to run as a list.
        cwd (Path): Working directory.
        estimated_minutes (int): Estimated time in minutes for the operation.
        stack (list, optional): List of stages from the YAML config to generate contextual messages.
    Returns:
        int: The return code of the process.
    """
    # Default messages if stack is not provided
    default_msgs = [
        "DeployML: Preparing your cloud environment...",
        "DeployML: Creating resources, please hold on...",
        "DeployML: Almost there! Just a few more steps...",
        "DeployML: Wrapping up the deployment for you...",
        "DeployML: All done! Reviewing the results...",
    ]

    # If stack is provided, build contextual messages
    if stack:
        resource_msgs = ["DeployML: Preparing your cloud environment..."]
        for stage in stack:
            for stage_name, tool in stage.items():
                tool_name = tool.get("name", stage_name)
                msg = f"DeployML: Deploying {tool_name.replace('_', ' ').title()} ({stage_name.replace('_', ' ').title()})..."
                resource_msgs.append(msg)
        resource_msgs.append("DeployML: Wrapping up the deployment for you...")
        resource_msgs.append("DeployML: All done! Reviewing the results...")
    else:
        resource_msgs = default_msgs

    # Log output to file for debugging
    log_file = cwd / "terraform_apply.log"
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task(resource_msgs[0], total=100)
        
        # Open log file and keep it open until process completes
        f = open(log_file, "w")
        try:
            process = subprocess.Popen(
                cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT
            )
            start_time = time.time()
            estimated_seconds = estimated_minutes * 60
            n_msgs = len(resource_msgs)
            while process.poll() is None:
                elapsed = time.time() - start_time
                # More conservative progress calculation - don't hit 95% too early
                if elapsed < estimated_seconds:
                    progress_percent = int((elapsed / estimated_seconds) * 85)
                else:
                    # If we exceed estimated time, slowly approach 95%
                    excess_time = elapsed - estimated_seconds
                    progress_percent = min(95, 85 + int(excess_time / 30))  # +1% per 30 seconds
                
                # Choose message based on progress
                msg_idx = min(
                    int(progress_percent / (100 / (n_msgs - 1))), n_msgs - 2
                )
                message = resource_msgs[msg_idx]
                progress.update(
                    task, completed=progress_percent, description=message
                )
                time.sleep(1)
            
            # Wait for process to fully complete and flush all output
            returncode = process.wait()
            f.flush()  # Ensure all output is written
            
            # Only show 100% if returncode is 0 (success)
            if returncode == 0:
                progress.update(task, completed=100, description=resource_msgs[-1])
            else:
                progress.update(task, completed=progress_percent, description=f"⚠️ Terraform apply returned code {returncode}")
            
            return returncode
        finally:
            f.close()  # Always close the file
