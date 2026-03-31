import subprocess
from pathlib import Path
from typing import Optional

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
    """

    docker_root = Path(docker_root)

    if not docker_root.exists():
        raise ValueError(f"Docker root does not exist: {docker_root}")

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
                subprocess.run(create_cmd, check=False)  # safe if already exists
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
                subprocess.run(build_cmd, check=True)
                print(f"Pushed: {image_uri}")
                print()

    # ----------------------------------------
    # LOCAL MODE
    # ----------------------------------------
    else:
        for service_dir in services:
            service_name = service_dir.name
            image_name = f"{service_name}:{tag}"

            build_cmd = [
                "docker", "build",
                "-t", image_name,
                str(service_dir),
            ]

            if dry_run:
                print("Would build locally:")
                print("  " + " ".join(build_cmd))
                print()
            else:
                print(f"Building {service_name} locally...")
                subprocess.run(build_cmd, check=True)
                print(f"Built: {image_name}")
                print()

    if dry_run:
        print("Dry run complete. No commands were executed.")

# -----------------------------
# Local Docker Build
# -----------------------------

def _validate_docker():
    try:
        subprocess.run(
            ["docker", "--version"],
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

        subprocess.run(
            [
                "docker",
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
        subprocess.run(
            ["gcloud", "--version"],
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

        subprocess.run(
            [
                "gcloud",
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