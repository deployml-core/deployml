"""Characterize the service discovery used by ``build_images``."""

from pathlib import Path


def test_build_images_discovers_exactly_the_current_gcp_services():
    docker_root = Path(__file__).parents[1] / "src" / "deployml" / "docker"
    services = {
        directory.name
        for directory in docker_root.iterdir()
        if directory.is_dir() and (directory / "Dockerfile").exists()
    }

    assert services == {"fastapi", "grafana-container", "mlflow"}, (
        "A new service directory requires per-provider filtering in build_images "
        "(correction C5) before it can land."
    )
