# GKE Deployment Guide

Complete guide for deploying MLflow and FastAPI to Google Kubernetes Engine (GKE) using deployml.

## Overview

GKE deployment uses Kubernetes manifests (similar to minikube) and automatically pushes Docker images to Google Container Registry (GCR).

## Prerequisites

### Required Software

```bash
# Verify installations
gcloud --version
kubectl version --client
docker --version
deployml --version
```

### GCP Setup

```bash
# Authenticate with GCP
gcloud auth login
gcloud auth application-default login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
deployml init --provider gcp --project-id YOUR_PROJECT_ID
```

## GKE Cluster Setup

### Create a New Cluster

```bash
gcloud container clusters create my-gke-cluster \
  --zone us-west1-a \
  --num-nodes 2 \
  --machine-type e2-medium \
  --project YOUR_PROJECT_ID
```

### Use Existing Cluster

```bash
# List existing clusters
gcloud container clusters list --project YOUR_PROJECT_ID
```

**Note:** If you have an existing company kubeconfig:
- **No manual setup needed** - `deployml deploy` handles everything automatically
- **Your company kubeconfig is safe** - `gcloud get-credentials` adds a new context, it doesn't delete existing ones
- **Context switching** - After deployment, kubectl will point to the GKE cluster. To switch back:
  ```bash
  kubectl config use-context YOUR_COMPANY_CONTEXT_NAME
  ```

### Cluster Sizing Recommendations

| Workload | Nodes | Machine Type | Total CPU | Total RAM |
|----------|-------|--------------|-----------|-----------|
| **Small** (MLflow only) | 1 | e2-medium | 2 vCPU | 4GB |
| **Medium** (MLflow + FastAPI) | 2 | e2-medium | 4 vCPU | 8GB |
| **Large** (Production) | 3+ | e2-standard-4 | 12+ vCPU | 16+ GB |

## Build and Push Docker Images

### Build MLflow Image

```bash
cd demo/mlflow
docker build --platform linux/amd64 -t mlflow-demo:latest .
cd ../..
```

### Build FastAPI Image

```bash
cd demo/fastapi
docker build --platform linux/amd64 -t fastapi-mlflow-demo:latest .
cd ../..
```

**Note:** The `deployml deploy` command will automatically push images if they're local, but you can also push manually.

## Configuration File

Create `gke-config.yaml`:

```yaml
name: gke-mlflow-fastapi
provider:
  name: gcp
  project_id: YOUR_PROJECT_ID
  region: us-west1

deployment:
  type: gke

gke:
  cluster_name: my-gke-cluster
  zone: us-west1-a  # For zonal cluster
  # OR use region for regional cluster:
  # region: us-west1

stack:
  - experiment_tracking:
      name: mlflow
      params:
        image: mlflow-demo:latest  # Local image name (will be pushed to GCR)
        backend_store_uri: sqlite:///mlflow.db
  
  - artifact_tracking:
      name: mlflow
      params:
        artifact_bucket: mlflow-artifacts-bucket
        create_artifact_bucket: true
  
  - model_registry:
      name: mlflow
      params:
        backend_store_uri: sqlite:///mlflow.db
  
  - model_serving:
      name: fastapi
      params:
        image: fastapi-mlflow-demo:latest
        mlflow_tracking_uri: http://mlflow-service:5000
```

### Key Configuration Points

- **`deployment.type: gke`** - Tells deployml to use Kubernetes manifests
- **`gke.cluster_name`** - Your GKE cluster name
- **`gke.zone`** - Cluster zone (or use `region` for regional clusters)
- **`image`** - Local Docker image name (will be converted to GCR format)
- **`mlflow_tracking_uri`** - Use `http://mlflow-service:5000` (Kubernetes internal DNS)

## Deployment Workflows

### Option 1: Generate and Deploy in One Step

```bash
# Deploy everything (generates manifests and applies them)
deployml deploy -c gke-config.yaml

# This will:
# 1. Connect to GKE cluster
# 2. Generate Kubernetes manifests
# 3. Push images to GCR (if local)
# 4. Deploy to GKE
# 5. Show LoadBalancer URLs
```

### Option 2: Two-Step Workflow (Generate, Review & Apply)

**Step 1: Generate Manifests Only**

```bash
# Generate manifests without applying
deployml deploy -c gke-config.yaml --generate-only

# Manifests are saved to:
# .deployml/<workspace>/manifests/mlflow/deployment.yaml
# .deployml/<workspace>/manifests/mlflow/service.yaml
# .deployml/<workspace>/manifests/fastapi/deployment.yaml
# .deployml/<workspace>/manifests/fastapi/service.yaml
```

**Step 2: Review and Edit Manifests (Optional)**

```bash
# Edit manifests if needed (e.g., adjust resource limits)
nano .deployml/gke-mlflow-fastapi/manifests/mlflow/deployment.yaml

# Common edits:
# - Adjust CPU/memory requests/limits
# - Change replica count
# - Modify environment variables
```

**Step 3: Apply Manifests**

```bash
# Apply manifests to GKE cluster
deployml gke-apply -c gke-config.yaml

# Or apply manually:
kubectl apply -f .deployml/gke-mlflow-fastapi/manifests/mlflow/
kubectl apply -f .deployml/gke-mlflow-fastapi/manifests/fastapi/
```

**Benefits of Two-Step Workflow:**
- Review manifests before deployment
- Edit resource limits, replicas, or environment variables
- Version control manifests
- Apply changes incrementally
- Debug issues before deployment

## Verify Deployment

```bash
# Check pods
kubectl get pods -l app=mlflow
kubectl get pods -l app=fastapi

# Check services
kubectl get svc mlflow-service
kubectl get svc fastapi-service

# Get LoadBalancer IPs
MLFLOW_IP=$(kubectl get svc mlflow-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
FASTAPI_IP=$(kubectl get svc fastapi-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

echo "MLflow URL: http://$MLFLOW_IP:5000"
echo "FastAPI URL: http://$FASTAPI_IP:8000"
```

## Testing

```bash
# Test MLflow health
curl http://$MLFLOW_IP:5000/health

# Test FastAPI health
curl http://$FASTAPI_IP:8000/health

# View logs
kubectl logs -l app=mlflow --tail=50 -f
kubectl logs -l app=fastapi --tail=50 -f
```

## Troubleshooting

### Pod Stuck in Pending

```bash
# Check pod status
kubectl describe pod POD_NAME

# Common fixes:
# 1. Reduce resource requests
kubectl patch deployment mlflow-deployment -p '{"spec":{"template":{"spec":{"containers":[{"name":"mlflow","resources":{"requests":{"cpu":"100m","memory":"256Mi"}}}]}}}}'

# 2. Scale up cluster
gcloud container clusters resize CLUSTER_NAME --num-nodes 3 --zone ZONE
```

### Image Pull Errors

```bash
# Verify image exists in GCR
gcloud container images list-tags gcr.io/PROJECT_ID/mlflow/mlflow --project=PROJECT_ID

# Push image manually if needed
docker tag mlflow-demo:latest gcr.io/PROJECT_ID/mlflow/mlflow:latest
docker push gcr.io/PROJECT_ID/mlflow/mlflow:latest
```

## Resource Management

### Check Current Resource Usage

```bash
kubectl top nodes
kubectl top pods
kubectl describe nodes
```

### Reduce Resource Requests

```bash
# Edit deployment
kubectl edit deployment DEPLOYMENT_NAME

# Or patch deployment
kubectl patch deployment DEPLOYMENT_NAME -p '{"spec":{"template":{"spec":{"containers":[{"name":"CONTAINER_NAME","resources":{"requests":{"cpu":"100m","memory":"256Mi"}}}]}}}}'
```

### Recommended Resource Settings

**For Small Clusters (2 nodes × e2-medium):**

```yaml
# MLflow
resources:
  requests:
    cpu: "250m"
    memory: "512Mi"
  limits:
    cpu: "1000m"
    memory: "2Gi"

# FastAPI
resources:
  requests:
    cpu: "100m"
    memory: "256Mi"
  limits:
    cpu: "500m"
    memory: "1Gi"
```

## Cleanup

```bash
# Delete deployments
kubectl delete deployment mlflow-deployment fastapi-deployment

# Delete services
kubectl delete service mlflow-service fastapi-service

# Delete cluster (optional)
gcloud container clusters delete CLUSTER_NAME --zone ZONE
```

## Quick Reference

```bash
# Get service URLs
MLFLOW_IP=$(kubectl get svc mlflow-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
FASTAPI_IP=$(kubectl get svc fastapi-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Check pods
kubectl get pods -l app=mlflow
kubectl get pods -l app=fastapi

# View logs
kubectl logs -l app=mlflow --tail=50 -f
kubectl logs -l app=fastapi --tail=50 -f
```

## Next Steps

- Learn about [Cloud Run deployment](gcp-cloud-run.md)
- Explore [Minikube for local testing](minikube.md)
- Check [CLI Commands](../api/cli-commands.md) reference

