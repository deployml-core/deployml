import subprocess
from pathlib import Path
from typing import Optional

from deployml.utils.helpers import check_docker_daemon
from deployml.utils.platform_compat import run_tool

class ImageBuildError(Exception):
    pass

def build_images(
    docker_root: Path,
    gcp_project_id: Optional[str] = None,
    region: str = "us-west1",
    repository: str = "mlops-images",
    tag: str = "latest",
    create_repo: bool = False,
    dry_run: bool = False,
    platform: Optional[str] = None,
) -> None:
    """
    Build all Docker images located in subdirectories of docker_root.

    Each subdirectory containing a Dockerfile will be built as a separate image.
    The image name will match the subdirectory name.

    Local mode:
        Builds images locally using Docker.

    GCP mode:
        Uses Cloud Build and pushes images to Artifact Registry.

    Args:
        docker_root: Root folder containing subfolders with Dockerfiles.
        gcp_project_id: If provided, use Cloud Build in this GCP project.
        region: GCP region for Artifact Registry.
        repository: Artifact Registry repository name.
        tag: Docker image tag.
        create_repo: Whether to create Artifact Registry repository (GCP mode only).
        dry_run: If True, print commands without executing them.
        platform: Local-mode docker build platform. Default None builds for the
            host architecture so images run on the local minikube node (arm64 on
            Apple Silicon). Pass "linux/amd64" only if you are building locally
            to push to an amd64 target like Cloud Run by hand. The GCP Cloud Build
            path always produces amd64 regardless of this flag.
    """

    docker_root = Path(docker_root)

    if not docker_root.exists():
        raise ValueError(f"Docker root does not exist: {docker_root}")

    # Local mode needs docker daemon. GCP mode uses Cloud Build, no local docker needed.
    if not gcp_project_id and not check_docker_daemon():
        raise ImageBuildError(
            "Docker daemon is not running or not reachable. Start Docker Desktop, "
            "or pass --gcp-project-id to build via Cloud Build."
        )

    # Discover services
    services = [
        d for d in docker_root.iterdir()
        if d.is_dir() and (d / "Dockerfile").exists()
    ]

    if not services:
        print("No Dockerfiles found.")
        return

    print(f"Found {len(services)} service(s):")
    for s in services:
        print(f"  - {s.name}")

    print()

    # ----------------------------------------
    # GCP MODE
    # ----------------------------------------
    if gcp_project_id:

        image_base = f"{region}-docker.pkg.dev/{gcp_project_id}/{repository}"

        # Create Artifact Registry repo if requested
        if create_repo:
            create_cmd = [
                "gcloud", "artifacts", "repositories", "create", repository,
                "--repository-format=docker",
                "--location", region,
                "--project", gcp_project_id,
            ]

            if dry_run:
                print("Would create Artifact Registry repository:")
                print("  " + " ".join(create_cmd))
                print()
            else:
                print("Ensuring Artifact Registry repository exists...")
                create_proc = run_tool(
                    create_cmd[0], create_cmd[1:], check=False,
                    capture_output=True, text=True,
                )
                stderr_lower = (create_proc.stderr or "").lower()
                if create_proc.returncode == 0:
                    print(f"Created repository: {repository}")
                elif "already exists" in stderr_lower or "alreadyexists" in stderr_lower:
                    print(f"Repository {repository} already exists, reusing.")
                else:
                    raise ImageBuildError(
                        f"Artifact Registry create failed: {create_proc.stderr.strip()}"
                    )
                print()

        # Build each service
        for service_dir in services:
            service_name = service_dir.name
            image_uri = f"{image_base}/{service_name}:{tag}"

            build_cmd = [
                "gcloud", "builds", "submit",
                str(service_dir),
                "--tag", image_uri,
                "--project", gcp_project_id,
            ]

            if dry_run:
                print("Would submit Cloud Build:")
                print("  " + " ".join(build_cmd))
                print()
            else:
                print(f"Building {service_name} via Cloud Build...")
                run_tool(build_cmd[0], build_cmd[1:], check=True)
                print(f"Pushed: {image_uri}")
                print()

    # ----------------------------------------
    # LOCAL MODE
    # ----------------------------------------
    else:
        for service_dir in services:
            service_name = service_dir.name
            image_name = f"{service_name}:{tag}"

            # Build for the host architecture by default so the image runs on the
            # local minikube node (arm64 on Apple Silicon). Local mode feeds
            # minikube; the Cloud Run path builds amd64 via Cloud Build above, so
            # there is no Cloud Run use case for a forced amd64 local build. Pass
            # platform explicitly only to override (e.g. a manual amd64 push).
            build_cmd = ["docker", "build"]
            if platform:
                build_cmd += ["--platform", platform]
            build_cmd += ["-t", image_name, str(service_dir)]

            if dry_run:
                print("Would build locally:")
                print("  " + " ".join(build_cmd))
                print()
            else:
                print(f"Building {service_name} locally...")
                run_tool(build_cmd[0], build_cmd[1:], check=True)
                print(f"Built: {image_name}")
                print()

    if dry_run:
        print("Dry run complete. No commands were executed.")

# -----------------------------
# Local Docker Build
# -----------------------------

def _validate_docker():
    try:
        run_tool(
            "docker", ["--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception:
        raise ImageBuildError("Docker is not installed or not available in PATH.")


def _build_locally(service_dirs: list[Path], tag: str):
    print("Building images locally with Docker...\n")

    for service_dir in service_dirs:
        service_name = service_dir.name
        image_name = f"{service_name}:{tag}"

        print(f"Building {image_name} ...")

        run_tool(
            "docker",
            [
                "build",
                "-t",
                image_name,
                str(service_dir),
            ],
            check=True,
        )

        print(f"Successfully built {image_name}\n")


# -----------------------------
# GCP Cloud Build
# -----------------------------

def _validate_gcloud():
    try:
        run_tool(
            "gcloud", ["--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception:
        raise ImageBuildError("gcloud CLI is not installed or not available in PATH.")


def _build_with_cloud_build(
    service_dirs: list[Path],
    gcp_project_id: str,
    region: str,
    repository: str,
    tag: str,
):
    print(f"Building images using Cloud Build in project '{gcp_project_id}'...\n")

    for service_dir in service_dirs:
        service_name = service_dir.name

        image_uri = (
            f"{region}-docker.pkg.dev/"
            f"{gcp_project_id}/"
            f"{repository}/"
            f"{service_name}:{tag}"
        )

        print(f"Submitting Cloud Build for {image_uri} ...")

        run_tool(
            "gcloud",
            [
                "builds",
                "submit",
                str(service_dir),
                "--tag",
                image_uri,
                "--project",
                gcp_project_id,
            ],
            check=True,
        )

        print(f"Successfully built and pushed {image_uri}\n")