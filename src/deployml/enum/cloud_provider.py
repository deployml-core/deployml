from enum import Enum

class CloudProvider(Enum):
    """
    Cloud provider identifiers used by config.provider.name and by the
    interactive `deployml generate` flow. Only `gcp` is fully implemented.
    `aws` and `azure` write skeleton configs from `deployml init`.
    `local` is reserved for minikube and other local Kubernetes flows.
    """
    LOCAL = "local"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
