# Tutorials Overview

Learn how to deploy a full MLOps infrastructure using deployml.

## GCP Cloud Run

The primary supported deployment target is GCP using Cloud Run — a serverless architecture that scales automatically and is cost-effective for academic use.

**[Get Started with GCP Cloud Run →](gcp-cloud-run.md)**

## End-to-End Example

Once deployed, walk through a complete MLOps workflow using a synthetic housing price dataset — training, registration, serving, drift monitoring, and Grafana dashboards.

**[End-to-End Example →](example.md)**

## Kubernetes: local minikube and GKE

Prefer a Kubernetes cluster over Cloud Run? deployml can run the MLflow and FastAPI stack on a local minikube cluster for offline testing, or on GKE. MLflow keeps its data on a PersistentVolumeClaim so experiments survive pod restarts. The commands are `minikube-init` / `minikube-deploy`, `mlflow-init` / `mlflow-deploy`, and `gke-cluster-create`, `gke-init`, `gke-deploy` / `gke-apply`, `gke-destroy`.

**[GKE flow notes →](gcp-cloud-run.md#gke-flow-notes)** and the [CLI Commands reference](../api/cli-commands.md).

## Quick Reference

```bash
# 1. Check dependencies
deployml doctor

# 2. Enable GCP APIs
deployml init --provider gcp --project-id YOUR_GCP_PROJECT_ID

# 3. Build Docker images
deployml build-images --create-repo

# 4. Deploy the stack
deployml deploy --verbose

# 5. Get service URLs and write .env
deployml get-urls

# 6. Tear down when done
deployml destroy
```
