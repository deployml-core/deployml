import shutil
import subprocess
import sys
import importlib.resources as pkg_resources
from pathlib import Path
from typing import Optional
from google.cloud import storage
import random
import string
from deployml.utils.constants import TERRAFORM_DIR
from deployml.utils.platform_compat import run_tool, resolve_tool, terraform_env
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
        result = run_tool("gcloud", ["auth", "list"], capture_output=True, text=True)
        return "ACTIVE" in result.stdout
    except Exception:
        return False


def check_gcp_adc() -> bool:
    """Application Default Credentials are required by Terraform and client libs."""
    try:
        result = run_tool(
            "gcloud",
            ["auth", "application-default", "print-access-token"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def check_bq() -> bool:
    if not shutil.which("bq"):
        return False
    try:
        result = run_tool(
            "bq",
            ["version"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_terraform_version() -> Optional[tuple]:
    """Return (major, minor, patch) or None."""
    if not shutil.which("terraform"):
        return None
    try:
        import json as _json

        result = run_tool(
            "terraform",
            ["version", "-json"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        data = _json.loads(result.stdout)
        parts = data.get("terraform_version", "").split(".")
        return tuple(int(p) for p in parts[:3])
    except Exception:
        return None


def validate_gcp_project(project_id: str) -> bool:
    """Verify project exists and active gcloud account can access it."""
    try:
        result = run_tool(
            "gcloud",
            ["projects", "describe", project_id, "--format=value(projectId)"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == project_id
    except Exception:
        return False


_GCP_REGIONS_CACHE: Optional[set] = None


def validate_gcp_region(region: str, project_id: Optional[str] = None) -> bool:
    """Check region exists. Cached. Returns True on lookup failure to avoid blocking."""
    global _GCP_REGIONS_CACHE
    if _GCP_REGIONS_CACHE is None:
        cmd = ["gcloud", "compute", "regions", "list", "--format=value(name)"]
        if project_id:
            cmd += ["--project", project_id]
        try:
            result = run_tool(cmd[0], cmd[1:], capture_output=True, text=True)
            if result.returncode != 0:
                print(
                    f"Warning: could not verify region '{region}' "
                    "(gcloud compute regions list failed). Proceeding unvalidated; "
                    "a typo here surfaces later as a confusing Terraform error.",
                    file=sys.stderr,
                )
                return True
            _GCP_REGIONS_CACHE = set(result.stdout.strip().splitlines())
        except Exception:
            print(
                f"Warning: could not verify region '{region}' "
                "(gcloud unavailable). Proceeding unvalidated.",
                file=sys.stderr,
            )
            return True
    return region in _GCP_REGIONS_CACHE


def get_missing_iam_roles(project_id: str, required_roles: list) -> list:
    """Return roles the active account lacks. roles/owner short-circuits to empty."""
    try:
        import json as _json

        account_result = run_tool(
            "gcloud",
            ["config", "get-value", "account"],
            capture_output=True,
            text=True,
        )
        account = account_result.stdout.strip()
        if not account:
            return list(required_roles)

        result = run_tool(
            "gcloud",
            ["projects", "get-iam-policy", project_id, "--format=json"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return list(required_roles)

        policy = _json.loads(result.stdout)
        member_keys = {f"user:{account}", f"serviceAccount:{account}"}
        held = set()
        for binding in policy.get("bindings", []):
            if any(m in member_keys for m in binding.get("members", [])):
                held.add(binding["role"])

        if "roles/owner" in held:
            return []
        return [r for r in required_roles if r not in held]
    except Exception:
        return list(required_roles)


def check_docker_daemon() -> bool:
    """Returns True if docker daemon is reachable (not just binary present)."""
    if not shutil.which("docker"):
        return False
    try:
        result = run_tool(
            "docker",
            ["info"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
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

    # BigQuery is always included — provides the mlops dataset and tables
    used_modules.add("bigquery")

    # Only copy the modules that are being used, and only the specific deployment type
    for module_path in MODULE_TEMPLATES_DIR.iterdir():
        if module_path.is_dir() and module_path.name in used_modules:
            # Special case: always copy full bigquery module
            if module_path.name == "bigquery":
                dest_module_path = modules_dir / module_path.name
                if dest_module_path.exists():
                    shutil.rmtree(dest_module_path)
                shutil.copytree(module_path, dest_module_path)
                continue
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
                deployment_source = module_path / "cloud" / cloud / deployment_type
                if deployment_source.exists():
                    deployment_dest = (
                        dest_module_path / "cloud" / cloud / deployment_type
                    )
                    deployment_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(deployment_source, deployment_dest)
                else:
                    # Fallback: copy entire module if specific deployment type doesn't exist
                    shutil.copytree(module_path, dest_module_path, dirs_exist_ok=True)
            else:
                # Copy entire module if no deployment type specified
                shutil.copytree(module_path, dest_module_path, dirs_exist_ok=True)


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
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        new_name = f"{base_name}-{suffix}"
        if not bucket_exists(new_name, project_id):
            return new_name


def generate_bucket_name(project_id: str) -> str:
    """
    Generate a stable, deterministic GCS bucket name for the given project.
    Uses project_id (globally unique on GCP) so the name is consistent across deploys.

    Args:
        project_id (str): The GCP project ID.

    Returns:
        str: A deterministic bucket name.
    """
    return f"mlflow-artifacts-{project_id}".replace("_", "-")


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
    Terminate all Cloud SQL connections before destroy so Terraform can cleanly
    delete databases and users. We just restart the instance — that kills all
    active connections — and let Terraform handle the actual resource deletion.
    """
    import time as _time

    try:
        result = run_tool(
            "terraform",
            ["output", "-raw", "instance_connection_name"],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return

        instance_connection_name = result.stdout.strip()
        parts = instance_connection_name.split(":")
        instance_name = parts[2] if len(parts) == 3 else instance_connection_name

        print(
            f"🗄️  Restarting Cloud SQL instance to close active connections: {instance_name}"
        )
        run_tool(
            "gcloud",
            [
                "sql",
                "instances",
                "restart",
                instance_name,
                "--project",
                project_id,
                "--quiet",
            ],
            capture_output=True,
            text=True,
        )
        # Give the instance time to fully restart and drop all connections
        _time.sleep(30)
        print("✅ Cloud SQL connections cleared")

    except Exception as e:
        print(f"⚠️  Cloud SQL cleanup failed (continuing with destroy): {e}")


def cleanup_terraform_files(terraform_dir: Path):
    """
    Clean up Terraform state and lock files from the specified directory.
    """
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


def run_terraform_with_loading_bar(
    cmd, cwd, estimated_minutes, stack=None, verbose=False
):
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
    # Resolve the tool to its real path so the streaming Popen calls below work on
    # Windows, where a bare .cmd name would fail. terraform is a real .exe, but
    # resolving keeps this robust if the front tool ever changes.
    cmd = [resolve_tool(cmd[0]), *cmd[1:]]

    # On Windows, ensure terraform's local-exec bash interpreter resolves to Git
    # bash, not the WSL launcher in System32 which mangles quoting and breaks the
    # Cloud SQL readiness provisioner. None off Windows, so behavior is unchanged
    # on macOS and Linux.
    tf_env = terraform_env()

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

    if verbose:
        with open(log_file, "w", encoding="utf-8", errors="replace") as f:
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=tf_env,
            )
            for line in iter(process.stdout.readline, ""):
                print(line, end="", flush=True)
                f.write(line)
            returncode = process.wait()
        return returncode

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task(resource_msgs[0], total=100)

        # Open log file and keep it open until process completes
        f = open(log_file, "w", encoding="utf-8", errors="replace")
        try:
            process = subprocess.Popen(
                cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, env=tf_env
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
                    progress_percent = min(
                        95, 85 + int(excess_time / 30)
                    )  # +1% per 30 seconds

                # Choose message based on progress
                msg_idx = min(int(progress_percent / (100 / (n_msgs - 1))), n_msgs - 2)
                message = resource_msgs[msg_idx]
                progress.update(task, completed=progress_percent, description=message)
                time.sleep(1)

            # Wait for process to fully complete and flush all output
            returncode = process.wait()
            f.flush()  # Ensure all output is written

            # Only show 100% if returncode is 0 (success)
            if returncode == 0:
                progress.update(task, completed=100, description=resource_msgs[-1])
            else:
                progress.update(
                    task,
                    completed=progress_percent,
                    description=f"⚠️ Terraform apply returned code {returncode}",
                )

            return returncode
        finally:
            f.close()  # Always close the file


def _create_docker_folder(
    project_root: Path,
    overwrite: bool = False,
) -> None:
    docker_target = project_root / "docker"

    if docker_target.exists() and not overwrite:
        raise FileExistsError(
            f"{docker_target} already exists. Use --overwrite to replace."
        )

    if docker_target.exists():
        shutil.rmtree(docker_target)

    docker_target.mkdir(parents=True, exist_ok=True)

    templates = pkg_resources.files("deployml") / "docker"

    for item in templates.iterdir():
        if item.is_dir():
            shutil.copytree(item, docker_target / item.name)
