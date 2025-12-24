# Minikube Local Deployment

Deploy MLflow and FastAPI locally using Minikube for testing and development.

## Overview

Minikube provides a local Kubernetes environment for testing and development. It's ideal for:

- ✅ Local testing
- ✅ No cloud costs
- ✅ Fast iteration
- ✅ Learning Kubernetes

## Prerequisites

```bash
# Install minikube
# macOS
brew install minikube

# Linux
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube

# Verify installation
minikube version
```

## Quick Start

### 1. Initialize Minikube for MLflow

```bash
# Generate MLflow manifests
deployml mlflow-init \
  --output-dir ./manifests/mlflow \
  --image mlflow-demo:latest \
  --backend-store-uri sqlite:///mlflow.db

# Deploy MLflow
deployml mlflow-deploy --manifest-dir ./manifests/mlflow
```

### 2. Initialize Minikube for FastAPI

```bash
# Generate FastAPI manifests
deployml minikube-init \
  --output-dir ./manifests/fastapi \
  --image fastapi-mlflow-demo:latest \
  --mlflow-uri http://mlflow-service:5000

# Deploy FastAPI
deployml minikube-deploy --manifest-dir ./manifests/fastapi
```

### 3. Access Services

```bash
# Get service URLs
minikube service mlflow-service --url
minikube service fastapi-service --url

# Or open in browser
minikube service mlflow-service
minikube service fastapi-service
```

## Two-Step Workflow

### Step 1: Generate Manifests

```bash
# MLflow
deployml mlflow-init \
  --output-dir ./manifests/mlflow \
  --image mlflow-demo:latest \
  --backend-store-uri sqlite:///mlflow.db

# FastAPI
deployml minikube-init \
  --output-dir ./manifests/fastapi \
  --image fastapi-mlflow-demo:latest \
  --mlflow-uri http://mlflow-service:5000
```

### Step 2: Edit Manifests (Optional)

```bash
# Edit deployment.yaml to adjust resources
nano ./manifests/mlflow/deployment.yaml

# Common edits:
# - Adjust CPU/memory requests/limits
# - Change replica count
# - Modify environment variables
```

### Step 3: Deploy

```bash
# Deploy MLflow
deployml mlflow-deploy --manifest-dir ./manifests/mlflow

# Deploy FastAPI
deployml minikube-deploy --manifest-dir ./manifests/fastapi
```

## Verify Deployment

```bash
# Check pods
kubectl get pods

# Check services
kubectl get svc

# View logs
kubectl logs -l app=mlflow --tail=50 -f
kubectl logs -l app=fastapi --tail=50 -f
```

## Testing

```bash
# Get MLflow URL
MLFLOW_URL=$(minikube service mlflow-service --url)

# Test health endpoint
curl $MLFLOW_URL/health

# Get FastAPI URL
FASTAPI_URL=$(minikube service fastapi-service --url)

# Test health endpoint
curl $FASTAPI_URL/health
```

## Cleanup

```bash
# Delete deployments
kubectl delete deployment mlflow-deployment fastapi-deployment

# Delete services
kubectl delete service mlflow-service fastapi-service

# Stop minikube
minikube stop

# Delete minikube cluster
minikube delete
```

## Troubleshooting

### Pod Not Starting

```bash
# Check pod status
kubectl get pods
kubectl describe pod POD_NAME

# Check logs
kubectl logs POD_NAME
```

### Image Not Found

```bash
# Load image into minikube
minikube image load mlflow-demo:latest
minikube image load fastapi-mlflow-demo:latest

# Or use minikube's Docker daemon
eval $(minikube docker-env)
docker build -t mlflow-demo:latest .
```

### Service Not Accessible

```bash
# Check service status
kubectl get svc

# Use minikube service command
minikube service SERVICE_NAME --url
```

## Next Steps

- Deploy to [GKE](gke-deployment.md) for production
- Learn about [Cloud Run](gcp-cloud-run.md) for serverless
- Check [CLI Commands](../api/cli-commands.md) reference

