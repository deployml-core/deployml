# API Reference Overview

deployml provides a command-line interface (CLI) for deploying and managing MLOps infrastructure on GCP.

## Commands

| Command | Description |
|---|---|
| `deployml doctor` | Check local dependencies |
| `deployml init` | Enable required GCP APIs |
| `deployml build-images` | Build and push Docker images to Artifact Registry |
| `deployml deploy` | Deploy the stack from a config file |
| `deployml get-urls` | Print service URLs and write `.env` file |
| `deployml destroy` | Tear down all infrastructure |

### Kubernetes commands

For the optional Kubernetes paths, local minikube and GKE:

| Command | Description |
|---|---|
| `deployml minikube-init` / `minikube-deploy` | Generate and deploy FastAPI manifests to a local minikube cluster |
| `deployml mlflow-init` / `mlflow-deploy` | Generate and deploy MLflow to minikube, with a PersistentVolumeClaim for data |
| `deployml gke-cluster-create` | Create a GKE cluster, Autopilot by default |
| `deployml gke-init` | Generate Kubernetes manifests for GKE |
| `deployml gke-deploy` / `gke-apply` | Apply manifests to a GKE cluster |
| `deployml gke-destroy` | Remove manifests, the PVC, and the gcr.io image, optionally the cluster |

See [CLI Commands](cli-commands.md) for full usage details and flags.
