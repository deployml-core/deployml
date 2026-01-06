# Complete GKE Deployment Guide: MLflow + FastAPI on Google Kubernetes Engine

**Step-by-step guide for deploying MLflow and FastAPI to GKE using deployml**

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [GKE Cluster Setup](#gke-cluster-setup)
3. [Build and Push Docker Images](#build-and-push-docker-images)
4. [Configuration File](#configuration-file)
5. [Deploy MLflow](#deploy-mlflow)
6. [Train and Register Models](#train-and-register-models)
7. [Deploy FastAPI](#deploy-fastapi)
8. [Testing and Verification](#testing-and-verification)
9. [Troubleshooting](#troubleshooting)
10. [Resource Management](#resource-management)
11. [Cleanup](#cleanup)
12. [Quick Reference](#quick-reference)

---

## Prerequisites

### Required Software

```bash
# Check installations
gcloud --version
kubectl version --client
docker --version
deployml --version

# Install if missing:
# - gcloud: https://cloud.google.com/sdk/docs/install
# - kubectl: https://kubernetes.io/docs/tasks/tools/
# - Docker: https://docs.docker.com/get-docker/
# - deployml: pip install deployml-core (or poetry add deployml-core)
```

**Important for users with existing kubeconfig (e.g., company clusters):**
- ✅ **No manual kubeconfig setup needed** - The `deployml deploy` command automatically configures kubectl via `gcloud get-credentials`
- ✅ **Your existing kubeconfig is safe** - The tool adds a new GKE context without deleting your company contexts
- ⚠️ **After deployment**, kubectl will be pointing to the GKE cluster. You can switch back anytime:
  ```bash
  kubectl config get-contexts  # List all contexts
  kubectl config use-context YOUR_COMPANY_CONTEXT  # Switch back
  ```

### GCP Authentication

```bash
# Authenticate with GCP
gcloud auth login
gcloud auth application-default login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Verify authentication
gcloud auth list
```

### Enable Required APIs

```bash
# Enable GKE API
gcloud services enable container.googleapis.com

# Enable Container Registry API
gcloud services enable containerregistry.googleapis.com

# Enable Compute Engine API
gcloud services enable compute.googleapis.com
```

---

## GKE Cluster Setup

### Option 1: Create New GKE Cluster

```bash
# Create a GKE cluster
gcloud container clusters create my-gke-cluster \
  --zone us-west1-a \
  --num-nodes 2 \
  --machine-type e2-medium \
  --project YOUR_PROJECT_ID

# This creates:
# - 2 nodes with e2-medium (2 vCPU, 4GB RAM each)
# - Total: 4 vCPU, 8GB RAM
# - Takes ~3-5 minutes
```

### Option 2: Use Existing Cluster

```bash
# List existing clusters
gcloud container clusters list --project YOUR_PROJECT_ID

# Connect to existing cluster
gcloud container clusters get-credentials CLUSTER_NAME \
  --zone ZONE \
  --project YOUR_PROJECT_ID

# Verify connection
kubectl cluster-info
kubectl get nodes
```

**Note:** If you have an existing company kubeconfig:
- ✅ **No manual setup needed** - `deployml deploy` handles everything automatically
- ✅ **Your company kubeconfig is safe** - `gcloud get-credentials` adds a new context, it doesn't delete existing ones
- ⚠️ **Context switching** - After deployment, kubectl will point to the GKE cluster. To switch back to your company cluster:
  ```bash
  kubectl config use-context YOUR_COMPANY_CONTEXT_NAME
  ```
- 📋 **View all contexts**: `kubectl config get-contexts`

### Cluster Sizing Recommendations

| Workload | Nodes | Machine Type | Total CPU | Total RAM |
|----------|-------|--------------|-----------|-----------|
| **Small** (MLflow only) | 1 | e2-medium | 2 vCPU | 4GB |
| **Medium** (MLflow + FastAPI) | 2 | e2-medium | 4 vCPU | 8GB |
| **Large** (Production) | 3+ | e2-standard-4 | 12+ vCPU | 16+ GB |

---

## Build and Push Docker Images

### Step 1: Build MLflow Image

```bash
# Navigate to MLflow directory
cd demo/mlflow

# Build for Linux/amd64 (required for GKE)
docker build --platform linux/amd64 -t mlflow-demo:latest .

# Verify image
docker images | grep mlflow-demo

cd ../..
```

### Step 2: Build FastAPI Image

```bash
# Navigate to FastAPI directory
cd demo/fastapi

# Build for Linux/amd64
docker build --platform linux/amd64 -t fastapi-mlflow-demo:latest .

# Verify image
docker images | grep fastapi-mlflow-demo

cd ../..
```

### Step 3: Push Images to Google Container Registry

```bash
# Set your project ID
export PROJECT_ID="YOUR_PROJECT_ID"

# Configure Docker for GCR
gcloud auth configure-docker

# Tag and push MLflow image
docker tag mlflow-demo:latest gcr.io/$PROJECT_ID/mlflow/mlflow:latest
docker push gcr.io/$PROJECT_ID/mlflow/mlflow:latest

# Tag and push FastAPI image
docker tag fastapi-mlflow-demo:latest gcr.io/$PROJECT_ID/fastapi/fastapi:latest
docker push gcr.io/$PROJECT_ID/fastapi/fastapi:latest

# Verify images in GCR
gcloud container images list --project=$PROJECT_ID
```

**Note:** The `deployml deploy` command will automatically push images if they're local, but you can also push manually as shown above.

---

## Configuration File

### Create GKE Config File

Create `gke-deploy-config.yaml`:

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
        backend_store_uri: sqlite:///mlflow.db  # or postgresql
  
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
        image: fastapi-mlflow-demo:latest  # Local image name
        mlflow_tracking_uri: http://mlflow-service:5000
```

### Key Configuration Points

- **`deployment.type: gke`** - Tells deployml to use Kubernetes manifests
- **`gke.cluster_name`** - Your GKE cluster name
- **`gke.zone`** - Cluster zone (or use `region` for regional clusters)
- **`image`** - Local Docker image name (will be converted to GCR format)
- **`mlflow_tracking_uri`** - Use `http://mlflow-service:5000` (Kubernetes internal DNS)

---

## Deploy MLflow

### Step 1: Deploy Using Config File

```bash
# Deploy MLflow (and FastAPI if in config)
deployml deploy -c gke-deploy-config.yaml

# This will:
# 1. Connect to GKE cluster
# 2. Generate Kubernetes manifests
# 3. Push images to GCR (if local)
# 4. Deploy to GKE
# 5. Show LoadBalancer URLs
```

### Step 2: Verify Deployment

```bash
# Check pods
kubectl get pods -l app=mlflow

# Should show:
# NAME                                 READY   STATUS    RESTARTS   AGE
# mlflow-deployment-XXXXX-XXXXX       1/1     Running   0          Xs

# Check service
kubectl get svc mlflow-service

# Should show:
# NAME             TYPE           CLUSTER-IP    EXTERNAL-IP      PORT(S)          AGE
# mlflow-service   LoadBalancer   10.XXX.XXX.X   34.XXX.XXX.XXX   5000:XXXXX/TCP   Xs
```

### Step 3: Get MLflow URL

```bash
# Get LoadBalancer IP
MLFLOW_IP=$(kubectl get svc mlflow-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "MLflow URL: http://$MLFLOW_IP:5000"

# Test health endpoint
curl http://$MLFLOW_IP:5000/health

# Open in browser
open http://$MLFLOW_IP:5000
```

---

## Train and Register Models

### Update Training Script

Update `demo/register_model.py` to use your MLflow URL:

```python
# Get MLflow URL from GKE
MLFLOW_IP = "34.182.23.6"  # Your LoadBalancer IP
mlflow.set_tracking_uri(f"http://{MLFLOW_IP}:5000")
```

### Run Training

```bash
# Run training script
python demo/register_model.py

# This will:
# - Connect to MLflow on GKE
# - Train model
# - Register model as "HousingPriceModel"
# - Promote to Production stage
```

### Verify Model Registration

```bash
# Open MLflow UI
MLFLOW_IP=$(kubectl get svc mlflow-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
open http://$MLFLOW_IP:5000

# Navigate to:
# 1. "Models" tab
# 2. Find "HousingPriceModel"
# 3. Verify Production stage
```

---

## Deploy FastAPI

### Step 1: Update Config File

Ensure FastAPI is in your config:

```yaml
stack:
  # ... MLflow config ...
  
  - model_serving:
      name: fastapi
      params:
        image: fastapi-mlflow-demo:latest
        mlflow_tracking_uri: http://mlflow-service:5000  # Kubernetes internal DNS
```

### Step 2: Deploy FastAPI

```bash
# Deploy (will deploy both MLflow and FastAPI)
deployml deploy -c gke-deploy-config.yaml

# Or deploy only FastAPI by commenting out MLflow in config
```

### Step 3: Verify FastAPI Deployment

```bash
# Check FastAPI pod
kubectl get pods -l app=fastapi

# Check FastAPI service
kubectl get svc fastapi-service

# Get FastAPI URL
FASTAPI_IP=$(kubectl get svc fastapi-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "FastAPI URL: http://34.82.236.4 :8000"

# Test health endpoint
curl http://34.82.236.4:8000/health

# Open Swagger UI
open http://$FASTAPI_IP:8000/docs
```

---

## Testing and Verification

### Test MLflow

```bash
# Get MLflow URL
MLFLOW_IP=$(kubectl get svc mlflow-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Test health
curl http://$MLFLOW_IP:5000/health

# Open UI
open http://$MLFLOW_IP:5000
```

### Test FastAPI

```bash
# Get FastAPI URL
FASTAPI_IP=$(kubectl get svc fastapi-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Test health
curl http://$FASTAPI_IP:8000/health

# Test root endpoint
curl http://$FASTAPI_IP:8000/

# Test prediction (if model is registered)
curl -X POST "http://$FASTAPI_IP:8000/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "features": {
      "bedrooms": 3,
      "bathrooms": 2,
      "area_sqft": 2000,
      "lot_size": 5000,
      "year_built": 2010,
      "city": 1,
      "state": 0
    }
  }'

# Open Swagger UI
open http://$FASTAPI_IP:8000/docs
```

### Check Logs

```bash
# MLflow logs
kubectl logs -l app=mlflow --tail=50 -f

# FastAPI logs
kubectl logs -l app=fastapi --tail=50 -f

# Check if model loaded in FastAPI
kubectl logs -l app=fastapi | grep -i "model"
```

---

## Troubleshooting

### Issue: Pod Stuck in `Pending` Status

**Symptoms:**
```
NAME                                 READY   STATUS    RESTARTS   AGE
fastapi-deployment-XXXXX-XXXXX      0/1     Pending   0          30m
```

**Diagnosis:**

```bash
# Check why pod is pending
kubectl describe pod POD_NAME

# Look for Events section - common causes:
# - "Insufficient cpu" or "Insufficient memory"
# - "ImagePullBackOff" or "ErrImagePull"
# - "0/2 nodes are available"
```

**Solutions:**

#### Solution 1: Insufficient CPU/Memory

**Reduce Resource Requests:**

```bash
# Patch deployment to reduce CPU/memory requests
kubectl patch deployment DEPLOYMENT_NAME -p '{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "CONTAINER_NAME",
          "resources": {
            "requests": {
              "cpu": "100m",
              "memory": "256Mi"
            },
            "limits": {
              "cpu": "500m",
              "memory": "1Gi"
            }
          }
        }]
      }
    }
  }
}'

# Example for FastAPI:
kubectl patch deployment fastapi-deployment -p '{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "fastapi",
          "resources": {
            "requests": {
              "cpu": "100m",
              "memory": "256Mi"
            }
          }
        }]
      }
    }
  }
}'

# Delete pending pod (will recreate with new resources)
kubectl delete pod POD_NAME
```

**Or Edit Deployment:**

```bash
# Edit deployment interactively
kubectl edit deployment DEPLOYMENT_NAME

# Change resources section:
resources:
  requests:
    cpu: "100m"      # Reduced from 250m
    memory: "256Mi"  # Reduced from 512Mi
  limits:
    cpu: "500m"
    memory: "1Gi"
```

**Scale Up Cluster:**

```bash
# Add more nodes to cluster
gcloud container clusters resize CLUSTER_NAME \
  --num-nodes 3 \
  --zone ZONE \
  --project PROJECT_ID

# Or use larger machine types
gcloud container node-pools create larger-pool \
  --cluster CLUSTER_NAME \
  --machine-type e2-standard-4 \
  --num-nodes 2 \
  --zone ZONE \
  --project PROJECT_ID
```

#### Solution 2: Image Pull Error

**Check if Image Exists:**

```bash
# Check if image is in GCR
gcloud container images list-tags gcr.io/PROJECT_ID/SERVICE/IMAGE --project=PROJECT_ID

# Example:
gcloud container images list-tags gcr.io/mldeploy-468919/fastapi/fastapi --project=mldeploy-468919
```

**Push Image Manually:**

```bash
# Build image
cd demo/fastapi
docker build --platform linux/amd64 -t fastapi-mlflow-demo:latest .

# Tag for GCR
docker tag fastapi-mlflow-demo:latest gcr.io/PROJECT_ID/fastapi/fastapi:latest

# Push to GCR
docker push gcr.io/PROJECT_ID/fastapi/fastapi:latest

# Delete pod to retry image pull
kubectl delete pod POD_NAME
```

#### Solution 3: Check Node Resources

```bash
# Check node capacity
kubectl describe nodes

# Check current resource usage
kubectl top nodes
kubectl top pods

# Check what's using resources
kubectl get pods --all-namespaces -o wide
```

### Issue: Pod in `ImagePullBackOff` Status

**Symptoms:**
```
NAME                                 READY   STATUS             RESTARTS   AGE
fastapi-deployment-XXXXX-XXXXX      0/1     ImagePullBackOff  0          5m
```

**Solutions:**

```bash
# 1. Check if image exists in GCR
gcloud container images list-tags gcr.io/PROJECT_ID/fastapi/fastapi --project=PROJECT_ID

# 2. If missing, push image
docker tag fastapi-mlflow-demo:latest gcr.io/PROJECT_ID/fastapi/fastapi:latest
docker push gcr.io/PROJECT_ID/fastapi/fastapi:latest

# 3. Check image pull secrets (usually not needed for GCR)
kubectl get secrets

# 4. Delete pod to retry
kubectl delete pod POD_NAME
```

### Issue: Pod in `CrashLoopBackOff` Status

**Symptoms:**
```
NAME                                 READY   STATUS             RESTARTS   AGE
mlflow-deployment-XXXXX-XXXXX      0/1     CrashLoopBackOff   5          10m
```

**Solutions:**

```bash
# 1. Check pod logs
kubectl logs POD_NAME --tail=100

# 2. Check previous container logs (if restarted)
kubectl logs POD_NAME --previous

# 3. Describe pod for events
kubectl describe pod POD_NAME

# 4. Common fixes:
#    - Increase memory limits (OOM errors)
#    - Fix environment variables
#    - Check application logs for errors
```

### Issue: LoadBalancer IP Stuck in `<pending>`

**Symptoms:**
```
NAME             TYPE           CLUSTER-IP    EXTERNAL-IP   PORT(S)
fastapi-service  LoadBalancer   10.XXX.XXX.X  <pending>     8000:XXXXX/TCP
```

**Solutions:**

```bash
# 1. Wait (can take 2-5 minutes)
kubectl get svc fastapi-service -w

# 2. Check service events
kubectl describe svc fastapi-service

# 3. Verify pod is running first
kubectl get pods -l app=fastapi

# 4. Check firewall rules (usually auto-created)
gcloud compute firewall-rules list --filter="name~gke"

# 5. If stuck >10 minutes, delete and recreate service
kubectl delete svc fastapi-service
kubectl apply -f service.yaml
```

### Issue: FastAPI Can't Connect to MLflow

**Symptoms:**
- FastAPI logs show: "Could not load model from MLflow"
- Health endpoint shows `"model_loaded": false`

**Solutions:**

```bash
# 1. Verify MLflow service exists
kubectl get svc mlflow-service

# 2. Test from FastAPI pod
kubectl exec -it FASTAPI_POD_NAME -- curl http://mlflow-service:5000/health

# 3. Check FastAPI environment variables
kubectl exec FASTAPI_POD_NAME -- env | grep MLFLOW

# 4. Verify MLflow pod is running
kubectl get pods -l app=mlflow

# 5. Check network policies (if any)
kubectl get networkpolicies
```

---

## Resource Management

### Check Current Resource Usage

```bash
# Node resources
kubectl top nodes

# Pod resources
kubectl top pods

# Detailed node info
kubectl describe nodes
```

### Reduce Resource Requests (Fix Pending Pods)

**Method 1: Patch Deployment**

```bash
# Reduce CPU and memory requests
kubectl patch deployment DEPLOYMENT_NAME -p '{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "CONTAINER_NAME",
          "resources": {
            "requests": {
              "cpu": "100m",
              "memory": "256Mi"
            },
            "limits": {
              "cpu": "500m",
              "memory": "1Gi"
            }
          }
        }]
      }
    }
  }
}'
```

**Method 2: Edit Deployment**

```bash
# Edit deployment
kubectl edit deployment DEPLOYMENT_NAME

# Change resources:
resources:
  requests:
    cpu: "100m"      # Minimum: 100m
    memory: "256Mi"  # Minimum: 256Mi
  limits:
    cpu: "500m"
    memory: "1Gi"
```

**Method 3: Update Manifest File**

```bash
# Edit generated manifest
nano .deployml/gke-mlflow-test/manifests/fastapi/deployment.yaml

# Change resources section, then apply:
kubectl apply -f .deployml/gke-mlflow-test/manifests/fastapi/deployment.yaml
```

### Increase Resource Requests

```bash
# Increase CPU and memory
kubectl patch deployment DEPLOYMENT_NAME -p '{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "CONTAINER_NAME",
          "resources": {
            "requests": {
              "cpu": "500m",
              "memory": "1Gi"
            },
            "limits": {
              "cpu": "2000m",
              "memory": "4Gi"
            }
          }
        }]
      }
    }
  }
}'
```

### Scale Up Cluster (Add More Resources)

```bash
# Add more nodes
gcloud container clusters resize CLUSTER_NAME \
  --num-nodes 3 \
  --zone ZONE \
  --project PROJECT_ID

# Or create node pool with larger machines
gcloud container node-pools create larger-pool \
  --cluster CLUSTER_NAME \
  --machine-type e2-standard-4 \
  --num-nodes 2 \
  --zone ZONE \
  --project PROJECT_ID
```

### Scale Down Cluster (Reduce Costs)

```bash
# Reduce number of nodes
gcloud container clusters resize CLUSTER_NAME \
  --num-nodes 1 \
  --zone ZONE \
  --project PROJECT_ID
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
    cpu: "100m"      # Reduced to fit
    memory: "256Mi"  # Reduced to fit
  limits:
    cpu: "500m"
    memory: "1Gi"
```

**For Medium Clusters (3+ nodes):**

```yaml
# MLflow
resources:
  requests:
    cpu: "500m"
    memory: "1Gi"
  limits:
    cpu: "2000m"
    memory: "4Gi"

# FastAPI
resources:
  requests:
    cpu: "250m"
    memory: "512Mi"
  limits:
    cpu: "1000m"
    memory: "2Gi"
```

---

## Cleanup

### Delete Kubernetes Resources

```bash
# Delete deployments (also deletes pods and ReplicaSets automatically)
kubectl delete deployment fastapi-deployment
kubectl delete deployment mlflow-deployment

# Delete services
kubectl delete service fastapi-service
kubectl delete service mlflow-service

# Verify deletion
kubectl get pods
kubectl get services
kubectl get deployments
```

### Delete Using Labels

```bash
# Delete all FastAPI resources
kubectl delete all -l app=fastapi

# Delete all MLflow resources
kubectl delete all -l app=mlflow
```

### Delete Docker Images from GCR

```bash
# Delete FastAPI image
gcloud container images delete gcr.io/PROJECT_ID/fastapi/fastapi:latest \
  --project PROJECT_ID

# Delete MLflow image
gcloud container images delete gcr.io/PROJECT_ID/mlflow/mlflow:latest \
  --project PROJECT_ID

# List remaining images
gcloud container images list --project PROJECT_ID
```

### Delete GKE Cluster (Complete Cleanup)

```bash
# Delete entire cluster
gcloud container clusters delete CLUSTER_NAME \
  --zone ZONE \
  --project PROJECT_ID

# This deletes:
# - All pods
# - All services
# - All deployments
# - The cluster itself
```

### Clean Up Local Files

```bash
# Delete generated manifests (optional)
rm -rf .deployml/gke-mlflow-test

# Delete local Docker images (optional)
docker rmi mlflow-demo:latest
docker rmi fastapi-mlflow-demo:latest
```

---

## Quick Reference

### Common Commands

```bash
# Get service URLs
MLFLOW_IP=$(kubectl get svc mlflow-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
FASTAPI_IP=$(kubectl get svc fastapi-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Check pods
kubectl get pods
kubectl get pods -l app=mlflow
kubectl get pods -l app=fastapi

# Check services
kubectl get svc
kubectl get svc mlflow-service
kubectl get svc fastapi-service

# View logs
kubectl logs -l app=mlflow --tail=50 -f
kubectl logs -l app=fastapi --tail=50 -f

# Restart deployments
kubectl rollout restart deployment/mlflow-deployment
kubectl rollout restart deployment/fastapi-deployment

# Describe resources
kubectl describe pod POD_NAME
kubectl describe deployment DEPLOYMENT_NAME
kubectl describe svc SERVICE_NAME
```

### Resource Management Commands

```bash
# Check resource usage
kubectl top nodes
kubectl top pods

# Reduce resources (fix pending pods)
kubectl patch deployment DEPLOYMENT_NAME -p '{"spec":{"template":{"spec":{"containers":[{"name":"CONTAINER_NAME","resources":{"requests":{"cpu":"100m","memory":"256Mi"}}}]}}}}'

# Scale cluster
gcloud container clusters resize CLUSTER_NAME --num-nodes 3 --zone ZONE --project PROJECT_ID
```

### Deployment Commands

```bash
# Deploy everything
deployml deploy -c gke-deploy-config.yaml

# Deploy only MLflow (comment out FastAPI in config)
deployml deploy -c gke-deploy-config.yaml

# Deploy only FastAPI (comment out MLflow in config)
deployml deploy -c gke-deploy-config.yaml
```

### Testing Commands

```bash
# Test MLflow
curl http://MLFLOW_IP:5000/health
open http://MLFLOW_IP:5000

# Test FastAPI
curl http://FASTAPI_IP:8000/health
curl -X POST "http://FASTAPI_IP:8000/predict" -H "Content-Type: application/json" -d '{"features": {...}}'
open http://FASTAPI_IP:8000/docs
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Your Local Machine                    │
│                                                          │
│  ┌──────────────┐         ┌──────────────┐            │
│  │ Training     │         │   Browser    │            │
│  │ Script       │────────▶│   (UI)       │            │
│  └──────────────┘         └──────────────┘            │
│         │                        │                      │
│         │ http://34.182.23.6:5000│                      │
│         │                        │                      │
└─────────┼────────────────────────┼──────────────────────┘
          │                        │
          │                        │
┌─────────▼────────────────────────▼──────────────────────┐
│              GKE Kubernetes Cluster                       │
│                                                           │
│  ┌──────────────────┐      ┌──────────────────┐       │
│  │  MLflow Pod      │      │  FastAPI Pod      │       │
│  │  Port: 5000      │◀─────│  Port: 8000       │       │
│  │                  │      │                  │       │
│  │  Service:        │      │  Service:        │       │
│  │  mlflow-service  │      │  fastapi-service │       │
│  │  :5000           │      │  :8000           │       │
│  └──────────────────┘      └──────────────────┘       │
│         │                                                │
│         │ http://mlflow-service:5000                     │
│         │                                                │
│  ┌──────▼────────────────────────────────────┐          │
│  │     MLflow Model Registry                 │          │
│  │     - HousingPriceModel                   │          │
│  │     - Production Stage                    │          │
│  └──────────────────────────────────────────┘          │
└───────────────────────────────────────────────────────────┘
```

---

## Key Points Summary

1. **GKE Cluster:** Must exist before deployment (create with `gcloud container clusters create`)
2. **Images:** Must be pushed to GCR (done automatically by deployml or manually)
3. **Service Names:** Use Kubernetes internal DNS (`mlflow-service:5000`) for pod-to-pod communication
4. **LoadBalancer IPs:** Use external IPs (`34.182.23.6:5000`) for browser/local access
5. **Resource Limits:** Adjust if pods are pending due to insufficient CPU/memory
6. **Deployment:** Use `deployml deploy -c config.yaml` (same command for all deployment types)

---

## Support

If you encounter issues:

1. Check pod status: `kubectl get pods`
2. Check logs: `kubectl logs POD_NAME`
3. Describe pod: `kubectl describe pod POD_NAME`
4. Check events: `kubectl get events --sort-by='.lastTimestamp'`
5. Verify cluster: `kubectl cluster-info`
6. Check resources: `kubectl top nodes` and `kubectl top pods`

Good luck with your GKE deployment! 🚀

