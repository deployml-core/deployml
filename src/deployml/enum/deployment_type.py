from enum import Enum


class DeploymentType(Enum):
    """
    Supported deployment types for MLOps infrastructure
    """

    DOCKER_COMPOSE = "docker_compose"
    DOCKER = "docker"
    CLOUD_RUN = "cloud_run"
    CLOUD_VM = "cloud_vm"
    GKE = "gke"
