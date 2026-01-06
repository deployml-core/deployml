# Complete Deployment Guide: MLflow + FastAPI on Kubernetes

**Demo-ready guide for deploying MLflow and FastAPI to minikube using deployml**

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Kubeconfig Setup](#kubeconfig-setup)
3. [Minikube Setup](#minikube-setup)
4. [Deploy MLflow](#deploy-mlflow)
5. [Train and Register Models](#train-and-register-models)
6. [Deploy FastAPI](#deploy-fastapi)
7. [Testing and Verification](#testing-and-verification)
8. [Troubleshooting](#troubleshooting)
9. [Cleanup](#cleanup)
10. [Quick Reference](#quick-reference)

---

## Prerequisites

### Required Software

Before starting, ensure you have the following installed:

```bash
# Check installations
minikube version
kubectl version --client
docker --version
deployml --version
python --version

# Install if missing:
# - Minikube: https://minikube.sigs.k8s.io/docs/start/
# - kubectl: https://kubernetes.io/docs/tasks/tools/
# - Docker: https://docs.docker.com/get-docker/
# - deployml: pip install deployml-core (or poetry add deployml-core)
# - Python 3.9+: https://www.python.org/downloads/
```

### Verify Docker is Running

```bash
# Check Docker status
docker ps

# If Docker is not running, start Docker Desktop
# On macOS: Open Docker Desktop application
# On Linux: sudo systemctl start docker
```

---

## Kubeconfig Setup

### Understanding Kubeconfig

**Kubeconfig** is a configuration file that tells `kubectl` which Kubernetes cluster to connect to. It contains:
- Cluster information (server URLs, certificates)
- User credentials
- Contexts (which cluster + namespace to use)

**Default location:** `~/.kube/config`

### Step 1: Check Current Kubeconfig

```bash
# View current kubeconfig location
echo $KUBECONFIG

# If empty, it's using default: ~/.kube/config
# View current context
kubectl config current-context

# List all available contexts
kubectl config get-contexts
```

### Step 2: Set Kubeconfig for Minikube

```bash
# Option 1: Use default location (recommended)
# Minikube automatically configures ~/.kube/config when started
# No action needed - just start minikube

# Option 2: Use custom kubeconfig file
export KUBECONFIG=~/.kube/minikube-config

# Option 3: Use multiple configs (merged)
export KUBECONFIG=~/.kube/config:~/.kube/minikube-config
```

### Step 3: Verify Kubeconfig is Working

```bash
# Test kubectl connection
kubectl cluster-info

# Should show cluster information without errors
# If error, minikube may not be started yet
```

**Note:** Minikube automatically configures kubeconfig when you run `minikube start`. You don't need to manually set it unless you want a custom location.

---

## Minikube Setup

### Step 1: Start Minikube

```bash
# Start minikube cluster
minikube start

# This will:
# - Create a local Kubernetes cluster
# - Configure kubectl to use minikube
# - Set up networking and storage
```

**Expected output:**
```
😄  minikube v1.37.0 on Darwin 14.5 (arm64)
✨  Using the docker driver based on existing profile
👍  Starting "minikube" primary control-plane node in "minikube" cluster
🚜  Pulling base image...
```

### Step 2: Verify Minikube is Running

```bash
# Check minikube status
minikube status

# Should show:
# host: Running
# kubelet: Running
# apiserver: Running
# kubeconfig: Configured

# Verify kubectl can connect
kubectl get nodes

# Should show:
# NAME       STATUS   ROLES           AGE   VERSION
# minikube   Ready    control-plane   Xm   v1.XX.X
```

### Step 3: Configure Minikube (Optional but Recommended)

```bash
# Set recommended resources for MLflow + FastAPI
minikube config set memory 4096    # 4GB RAM
minikube config set cpus 4         # 4 CPUs
minikube config set disk-size 20g  # 20GB disk

# View configuration
minikube config view

# Restart minikube to apply changes
minikube stop
minikube start
```

### Step 4: Verify Kubernetes Context

```bash
# Check current context (should be minikube)
kubectl config current-context

# Should output: minikube

# If not minikube, switch context
kubectl config use-context minikube

# Verify you're on the right cluster
kubectl get nodes

# Should show: minikube (not AWS/GCP nodes)
```

**Important:** Make sure you're using the minikube context, not a remote cloud cluster!

---

## Deploy MLflow

### Step 1: Build MLflow Docker Image

**Why:** We need a containerized MLflow server that can run in Kubernetes.

```bash
# Navigate to MLflow directory
cd demo/mlflow

# Build Docker image for Linux/amd64 platform
# Note: --platform linux/amd64 is required even on Apple Silicon Macs
docker build --platform linux/amd64 -t mlflow-demo:latest .

# This creates a Docker image with:
# - Python 3.9
# - MLflow 2.8.1
# - Required dependencies
# - MLflow server configured

# Verify image was created
docker images | grep mlflow-demo

# Expected output:
# mlflow-demo    latest    <image-id>   X minutes ago   XXX MB

# Return to project root
cd ../..
```

**What this does:**
- Creates a Docker image containing MLflow server
- Configures MLflow to run on port 5000
- Sets up health checks
- Includes all necessary dependencies

### Step 2: Generate MLflow Kubernetes Manifests

**Why:** We need Kubernetes YAML files (deployment.yaml and service.yaml) to deploy MLflow.

```bash
# Generate Kubernetes manifests using deployml
deployml mlflow-init \
  --output-dir ./demo/k8s-mlflow \
  --image mlflow-demo:latest

# This command:
# - Creates deployment.yaml (defines MLflow pod)
# - Creates service.yaml (exposes MLflow on NodePort 30050)
# - Automatically loads Docker image into minikube
# - Configures MLflow with SQLite backend (default)

# Verify manifests were created
ls -la ./demo/k8s-mlflow/

# Should show:
# deployment.yaml
# service.yaml
```

**What gets created:**

**deployment.yaml:**
- Defines MLflow pod with 1 replica
- Sets resource limits (512Mi-1Gi memory, 250m-500m CPU)
- Configures health checks
- Uses SQLite backend by default

**service.yaml:**
- Exposes MLflow on NodePort 30050
- Maps port 5000 (container) → 30050 (host)
- Allows access from outside the cluster

### Step 3: Deploy MLflow to Minikube

```bash
# Deploy MLflow using the generated manifests
deployml mlflow-deploy --manifest-dir ./demo/k8s-mlflow

# This command:
# - Applies deployment.yaml (creates MLflow pod)
# - Applies service.yaml (creates MLflow service)
# - Loads Docker image if needed
# - Shows deployment status and URL

# Verify deployment
kubectl get pods -l app=mlflow

# Should show:
# NAME                                 READY   STATUS    RESTARTS   AGE
# mlflow-deployment-XXXXX-XXXXX       1/1     Running   0          Xs

# Check service
kubectl get svc mlflow-service

# Should show:
# NAME             TYPE       CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE
# mlflow-service   NodePort   10.XXX.XXX.XXX  <none>        5000:30050/TCP   Xs
```

**Wait for pod to be ready:**
```bash
# Watch pod status
kubectl get pods -l app=mlflow -w

# Press Ctrl+C when STATUS shows "Running" and READY shows "1/1"
```

### Step 4: Get MLflow URL

**Important:** On macOS with Docker driver, minikube creates a tunneled URL.

```bash
# Get tunneled URL (works from your Mac)
MLFLOW_URL=$(minikube service mlflow-service --url)
echo "MLflow URL: $MLFLOW_URL"

# Example output: http://127.0.0.1:64231

# Test MLflow health endpoint
curl $MLFLOW_URL/health

# Should return: {"status":"ok"}

# Open MLflow UI in browser
open $MLFLOW_URL

# Or manually navigate to: http://127.0.0.1:64231
```

**Understanding the URLs:**
- **From your Mac:** Use `http://127.0.0.1:XXXXX` (tunneled URL)
- **Inside Kubernetes pods:** Use `http://mlflow-service:5000` (service name)
- **Port may change:** If you restart minikube, get a fresh URL

### Step 5: Verify MLflow is Working

```bash
# Check pod logs
kubectl logs -l app=mlflow --tail=50

# Should show MLflow server starting messages

# Check service details
kubectl describe svc mlflow-service

# Test from inside cluster
kubectl exec -it $(kubectl get pod -l app=mlflow -o jsonpath='{.items[0].metadata.name}') -- curl http://localhost:5000/health
```

---

## Train and Register Models

### Step 1: Install Python Dependencies

```bash
# Install required packages
pip install mlflow pandas numpy scikit-learn

# Or if you have a requirements.txt
pip install -r requirements.txt

# Verify MLflow installation
python -c "import mlflow; print(f'MLflow version: {mlflow.__version__}')"
```

### Step 2: Understand the Training Script

The training script (`demo/register_model.py`) does the following:
1. Connects to MLflow tracking server
2. Creates/uses an experiment
3. Trains a RandomForest model
4. Logs metrics and parameters
5. Registers the model
6. Promotes model to Production stage

### Step 3: Run Training Script

```bash
# Make sure you have the MLflow URL
MLFLOW_URL=$(minikube service mlflow-service --url)
echo "Using MLflow at: $MLFLOW_URL"

# Run training script
python demo/register_model.py

# The script will:
# - Auto-detect MLflow URL from minikube
# - Create experiment: housing-price-prediction
# - Train model on synthetic housing data
# - Register model as: HousingPriceModel
# - Promote to Production stage
```

**Expected output:**
```
✅ Found MLflow URL via minikube service: http://127.0.0.1:64231
🔗 MLflow Tracking URI: http://127.0.0.1:64231
✅ Using existing experiment: housing-price-prediction
📊 Preparing data...
✅ Data prepared: 800 training samples, 200 test samples
🤖 Training model...
📊 Model Performance:
  Training RMSE: $XX,XXX.XX
  Test RMSE: $XX,XXX.XX
✅ Model logged! Run ID: xxxxx
🔄 Promoting model to Production...
✅ Model version 1 promoted to Production!
🎉 Training complete!
```

### Step 4: Verify Model Registration

**Option 1: Check in MLflow UI**
```bash
# Open MLflow UI
MLFLOW_URL=$(minikube service mlflow-service --url)
open $MLFLOW_URL

# Navigate to:
# 1. "Models" tab (top menu)
# 2. Find "HousingPriceModel"
# 3. Check version 1 is in "Production" stage
```

**Option 2: Check via Python**
```python
from mlflow.tracking import MlflowClient

mlflow.set_tracking_uri("http://127.0.0.1:64231")  # Your MLflow URL
client = MlflowClient()

# List registered models
models = client.search_registered_models()
for model in models:
    print(f"Model: {model.name}")
    for version in model.latest_versions:
        print(f"  Version {version.version}: {version.current_stage}")
```

**Option 3: Check via Command Line**
```bash
# Set tracking URI
export MLFLOW_TRACKING_URI=$(minikube service mlflow-service --url)

# List models (if mlflow CLI is available)
mlflow models list
```

### Step 5: Test Model Loading

```python
import mlflow.pyfunc
import pandas as pd

# Set tracking URI
mlflow.set_tracking_uri("http://127.0.0.1:64231")  # Your MLflow URL

# Load Production model
model = mlflow.pyfunc.load_model("models:/HousingPriceModel/Production")
print("✅ Model loaded successfully!")

# Make a test prediction
sample = pd.DataFrame({
    'bedrooms': [3],
    'bathrooms': [2],
    'area_sqft': [2000],
    'lot_size': [5000],
    'year_built': [2010],
    'city': [1],
    'state': [0]
})

prediction = model.predict(sample)
print(f"Predicted price: ${prediction[0]:,.2f}")
```

---

## Deploy FastAPI

### Step 1: Understand FastAPI Configuration

The FastAPI application (`demo/fastapi/main.py`) is configured to:
- Connect to MLflow at `http://mlflow-service:5000` (Kubernetes service name)
- Load `HousingPriceModel` from Production stage
- Accept prediction requests with housing features
- Return price predictions

**Key configuration:**
```python
MLFLOW_TRACKING_URI = "http://mlflow-service:5000"  # Kubernetes service name
MODEL_NAME = "HousingPriceModel"
```

**Why `mlflow-service:5000`?**
- Inside Kubernetes, pods communicate via service names
- `mlflow-service` is the Kubernetes service name
- Port `5000` is the MLflow container port
- This works from inside the FastAPI pod

### Step 2: Build FastAPI Docker Image

```bash
# Navigate to FastAPI directory
cd demo/fastapi

# Build Docker image
docker build --platform linux/amd64 -t fastapi-mlflow-demo:latest .

# This creates a Docker image with:
# - Python 3.9
# - FastAPI and Uvicorn
# - MLflow and scikit-learn
# - Your FastAPI application code

# Verify image
docker images | grep fastapi-mlflow-demo

# Return to project root
cd ../..
```

### Step 3: Generate FastAPI Kubernetes Manifests

**Important:** Use Kubernetes service name for MLflow URI, not the tunneled URL!

```bash
# Generate manifests with MLflow URI
# Use http://mlflow-service:5000 (Kubernetes service name)
deployml minikube-init \
  --output-dir ./demo/k8s-fastapi \
  --image fastapi-mlflow-demo:latest \
  --mlflow-uri http://mlflow-service:5000

# This creates:
# - deployment.yaml (FastAPI pod configuration)
# - service.yaml (exposes FastAPI on NodePort 30080)
# - Sets MLFLOW_TRACKING_URI environment variable
# - Loads Docker image into minikube

# Verify manifests
ls -la ./demo/k8s-fastapi/
```

**Why `http://mlflow-service:5000`?**
- `mlflow-service` is the Kubernetes service name (DNS resolvable)
- `5000` is the MLflow container port
- This allows FastAPI pod to communicate with MLflow pod internally

### Step 4: Deploy FastAPI to Minikube

```bash
# Deploy FastAPI
deployml minikube-deploy --manifest-dir ./demo/k8s-fastapi

# Verify deployment
kubectl get pods -l app=fastapi

# Should show:
# NAME                                 READY   STATUS    RESTARTS   AGE
# fastapi-deployment-XXXXX-XXXXX      1/1     Running   0          Xs

# Check service
kubectl get svc fastapi-service

# Should show:
# NAME             TYPE       CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE
# fastapi-service  NodePort   10.XXX.XXX.XXX  <none>        8000:30080/TCP   Xs
```

### Step 5: Verify Model Loading

```bash
# Check FastAPI logs (should show model loaded)
kubectl logs -l app=fastapi --tail=50

# Look for:
# ✓ Loaded model 'HousingPriceModel' from Production stage

# If you see errors, check:
kubectl describe pod -l app=fastapi
```

**Common issues:**
- Model not found → Check model name matches
- Connection refused → Check MLflow service is accessible
- Timeout → Check MLflow pod is running

### Step 6: Get FastAPI URL

```bash
# Get tunneled URL
FASTAPI_URL=$(minikube service fastapi-service --url)
echo "FastAPI URL: $FASTAPI_URL"

# Example: http://127.0.0.1:64750

# Test health endpoint
curl $FASTAPI_URL/health

# Expected response:
# {
#   "status": "healthy",
#   "mlflow_connected": true,
#   "model_loaded": true,
#   "timestamp": "2025-12-12T..."
# }
```

---

## Testing and Verification

### Test MLflow

```bash
# Get MLflow URL
MLFLOW_URL=$(minikube service mlflow-service --url)

# Test health
curl $MLFLOW_URL/health
# Should return: {"status":"ok"}

# Open UI
open $MLFLOW_URL

# In the UI, verify:
# 1. Experiment "housing-price-prediction" exists
# 2. Model "HousingPriceModel" is registered
# 3. Version 1 is in "Production" stage
```

### Test FastAPI Root Endpoint

```bash
FASTAPI_URL=$(minikube service fastapi-service --url)

# Test root endpoint
curl $FASTAPI_URL/

# Expected response:
# {
#   "service": "FastAPI Demo",
#   "version": "1.0.0",
#   "model_loaded": true,
#   "model_name": "HousingPriceModel",
#   "mlflow_uri": "http://mlflow-service:5000",
#   "endpoints": {...}
# }
```

### Test FastAPI Health Endpoint

```bash
curl $FASTAPI_URL/health

# Expected response:
# {
#   "status": "healthy",
#   "timestamp": "2025-12-12T...",
#   "port": 8000,
#   "mlflow_connected": true,
#   "model_loaded": true
# }
```

### Test Prediction Endpoint

```bash
# Make prediction request
curl -X POST "$FASTAPI_URL/predict" \
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

# Expected response:
# {
#   "prediction": 557545.45,
#   "timestamp": "2025-12-12T06:31:23.450973",
#   "model_used": "MLflow: HousingPriceModel"
# }
```

**If prediction returns -1:**
- Model not loaded → Check FastAPI logs
- Wrong features → Check feature names match model
- Connection error → Check MLflow service accessibility

### Test via Swagger UI

```bash
# Open interactive API documentation
open $FASTAPI_URL/docs

# Or ReDoc
open $FASTAPI_URL/redoc

# In Swagger UI:
# 1. Click "POST /predict"
# 2. Click "Try it out"
# 3. Enter features in JSON format
# 4. Click "Execute"
# 5. See prediction result
```

### Test Multiple Predictions

```bash
# Test with different inputs
curl -X POST "$FASTAPI_URL/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "features": {
      "bedrooms": 4,
      "bathrooms": 3,
      "area_sqft": 3000,
      "lot_size": 8000,
      "year_built": 2015,
      "city": 2,
      "state": 1
    }
  }'
```

---

## Troubleshooting

### Issue: Pod shows `ErrImageNeverPull`

**Symptoms:**
```
NAME                                 READY   STATUS              RESTARTS   AGE
fastapi-deployment-XXXXX-XXXXX      0/1     ErrImageNeverPull   0          Xs
```

**Causes:**
- Wrong Kubernetes context (deploying to remote cluster instead of minikube)
- Image not loaded into minikube
- ImagePullPolicy mismatch

**Solutions:**

```bash
# 1. Check current context
kubectl config current-context
# Should show: minikube

# If not, switch context
kubectl config use-context minikube

# 2. Reload image into minikube
minikube image load fastapi-mlflow-demo:latest

# 3. Verify image exists
minikube image ls | grep fastapi-mlflow-demo

# 4. Delete pods to recreate
kubectl delete pod -l app=fastapi

# 5. Check new pods
kubectl get pods -l app=fastapi
```

### Issue: Model not loading in FastAPI

**Symptoms:**
- Health endpoint shows `"model_loaded": false`
- Predictions return -1
- Logs show connection errors

**Solutions:**

```bash
# 1. Check FastAPI logs
kubectl logs -l app=fastapi --tail=100

# Look for errors like:
# - "Could not load model from MLflow"
# - "Connection refused"
# - "Model not found"

# 2. Verify MLflow service is accessible from FastAPI pod
kubectl exec -it $(kubectl get pod -l app=fastapi -o jsonpath='{.items[0].metadata.name}') -- curl http://mlflow-service:5000/health

# Should return: {"status":"ok"}

# 3. Check environment variables
kubectl exec -it $(kubectl get pod -l app=fastapi -o jsonpath='{.items[0].metadata.name}') -- env | grep MLFLOW

# Should show:
# MLFLOW_TRACKING_URI=http://mlflow-service:5000

# 4. Verify model exists in MLflow
# Open MLflow UI and check Models tab

# 5. Test model loading manually
python -c "
import mlflow.pyfunc
mlflow.set_tracking_uri('http://127.0.0.1:64231')  # Your MLflow URL
model = mlflow.pyfunc.load_model('models:/HousingPriceModel/Production')
print('Model loaded successfully')
"
```

### Issue: Wrong Kubernetes Context

**Symptoms:**
- Pods scheduled on AWS/GCP nodes instead of minikube
- `ErrImageNeverPull` errors
- Cannot access services

**Solutions:**

```bash
# 1. List all contexts
kubectl config get-contexts

# 2. Switch to minikube
kubectl config use-context minikube

# 3. Verify
kubectl get nodes
# Should show: minikube (not AWS/GCP nodes)

# 4. Redeploy
deployml minikube-deploy --manifest-dir ./demo/k8s-fastapi
```

### Issue: MLflow URL not accessible

**Symptoms:**
- Cannot connect to MLflow from training script
- Connection timeout errors

**Solutions:**

```bash
# 1. Get fresh URL (port may have changed)
MLFLOW_URL=$(minikube service mlflow-service --url)
echo $MLFLOW_URL

# 2. Test connectivity
curl $MLFLOW_URL/health

# 3. Check MLflow pod is running
kubectl get pods -l app=mlflow

# 4. Check MLflow logs
kubectl logs -l app=mlflow --tail=50

# 5. Use port-forward for stable port
kubectl port-forward svc/mlflow-service 5000:5000
# Then use: http://127.0.0.1:5000
```

### Issue: FastAPI returns -1

**Symptoms:**
- Prediction endpoint returns `{"prediction": -1}`

**Causes:**
- Model not loaded
- Wrong feature names
- Model loading error

**Solutions:**

```bash
# 1. Check FastAPI logs
kubectl logs -l app=fastapi --tail=100

# 2. Verify model is loaded
curl $FASTAPI_URL/health
# Check: "model_loaded": true

# 3. Verify feature names match
# Check model expects: bedrooms, bathrooms, area_sqft, lot_size, year_built, city, state

# 4. Test with correct features
curl -X POST "$FASTAPI_URL/predict" \
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
```

### Issue: Port number keeps changing

**Symptoms:**
- MLflow/FastAPI URL changes after restarting minikube

**Solutions:**

```bash
# 1. Always get fresh URL
MLFLOW_URL=$(minikube service mlflow-service --url)
FASTAPI_URL=$(minikube service fastapi-service --url)

# 2. Use port-forward for stable ports
kubectl port-forward svc/mlflow-service 5000:5000 &
kubectl port-forward svc/fastapi-service 8000:8000 &

# Then use:
# MLflow: http://127.0.0.1:5000
# FastAPI: http://127.0.0.1:8000
```

---

## Cleanup

### Delete Deployments

```bash
# Delete FastAPI
kubectl delete -f ./demo/k8s-fastapi/

# Delete MLflow
kubectl delete -f ./demo/k8s-mlflow/

# Or delete by label
kubectl delete deployment -l app=fastapi
kubectl delete svc -l app=fastapi
kubectl delete deployment -l app=mlflow
kubectl delete svc -l app=mlflow

# Verify deletion
kubectl get pods
kubectl get svc
```

### Stop Minikube

```bash
# Stop minikube (keeps data)
minikube stop

# Delete minikube cluster (removes everything)
minikube delete

# Confirm deletion
minikube status
```

### Remove Docker Images

```bash
# Remove local images
docker rmi mlflow-demo:latest
docker rmi fastapi-mlflow-demo:latest

# Remove from minikube (if minikube is running)
minikube image rm mlflow-demo:latest
minikube image rm fastapi-mlflow-demo:latest
```

---

## Quick Reference

### Complete Deployment Script

Save this as `deploy_all.sh`:

```bash
#!/bin/bash
set -e

echo "🚀 Complete MLflow + FastAPI Deployment"
echo "========================================"

# 1. Setup
echo "\n📋 Step 1: Setup"
kubectl config use-context minikube
minikube start
kubectl get nodes

# 2. Build MLflow
echo "\n📦 Step 2: Building MLflow Image"
cd demo/mlflow
docker build --platform linux/amd64 -t mlflow-demo:latest .
cd ../..

# 3. Deploy MLflow
echo "\n🚀 Step 3: Deploying MLflow"
deployml mlflow-init --output-dir ./demo/k8s-mlflow --image mlflow-demo:latest
deployml mlflow-deploy --manifest-dir ./demo/k8s-mlflow

# 4. Get MLflow URL
echo "\n🔗 Step 4: Getting MLflow URL"
MLFLOW_URL=$(minikube service mlflow-service --url)
echo "✅ MLflow: $MLFLOW_URL"
sleep 5  # Wait for MLflow to be ready

# 5. Train Model
echo "\n🤖 Step 5: Training Model"
python demo/register_model.py

# 6. Build FastAPI
echo "\n📦 Step 6: Building FastAPI Image"
cd demo/fastapi
docker build --platform linux/amd64 -t fastapi-mlflow-demo:latest .
cd ../..

# 7. Deploy FastAPI
echo "\n🚀 Step 7: Deploying FastAPI"
deployml minikube-init --output-dir ./demo/k8s-fastapi --image fastapi-mlflow-demo:latest --mlflow-uri http://mlflow-service:5000
deployml minikube-deploy --manifest-dir ./demo/k8s-fastapi

# 8. Get FastAPI URL
echo "\n🔗 Step 8: Getting FastAPI URL"
sleep 10  # Wait for FastAPI to start
FASTAPI_URL=$(minikube service fastapi-service --url)
echo "✅ FastAPI: $FASTAPI_URL"

# 9. Test
echo "\n🧪 Step 9: Testing"
curl -f "$FASTAPI_URL/health" && echo "✅ Health check passed!"
curl -X POST "$FASTAPI_URL/predict" \
  -H "Content-Type: application/json" \
  -d '{"features": {"bedrooms": 3, "bathrooms": 2, "area_sqft": 2000, "lot_size": 5000, "year_built": 2010, "city": 1, "state": 0}}'

echo "\n🎉 Deployment complete!"
echo "📊 MLflow UI: $MLFLOW_URL"
echo "🚀 FastAPI: $FASTAPI_URL"
```

### Common Commands Cheat Sheet

```bash
# Get service URLs
MLFLOW_URL=$(minikube service mlflow-service --url)
FASTAPI_URL=$(minikube service fastapi-service --url)

# Check pods
kubectl get pods -l app=mlflow
kubectl get pods -l app=fastapi

# View logs
kubectl logs -l app=mlflow --tail=50 -f
kubectl logs -l app=fastapi --tail=50 -f

# Restart services
kubectl rollout restart deployment/mlflow-deployment
kubectl rollout restart deployment/fastapi-deployment

# Check services
kubectl get svc

# Test endpoints
curl $MLFLOW_URL/health
curl $FASTAPI_URL/health
curl -X POST "$FASTAPI_URL/predict" -H "Content-Type: application/json" -d '{"features": {...}}'
```

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Your Mac (Host)                      │
│                                                          │
│  ┌──────────────┐         ┌──────────────┐            │
│  │ Training     │         │   Browser    │            │
│  │ Script       │────────▶│   (UI)       │            │
│  └──────────────┘         └──────────────┘            │
│         │                        │                      │
│         │ http://127.0.0.1:64231│                      │
│         │                        │                      │
└─────────┼────────────────────────┼──────────────────────┘
          │                        │
          │                        │
┌─────────▼────────────────────────▼──────────────────────┐
│              Minikube Kubernetes Cluster                  │
│                                                           │
│  ┌──────────────────┐      ┌──────────────────┐        │
│  │  MLflow Pod      │      │  FastAPI Pod     │        │
│  │  Port: 5000      │◀─────│  Port: 8000      │        │
│  │                  │      │                  │        │
│  │  Service:        │      │  Service:        │        │
│  │  mlflow-service  │      │  fastapi-service │        │
│  │  :5000           │      │  :8000           │        │
│  └──────────────────┘      └──────────────────┘        │
│         │                                                │
│         │ http://mlflow-service:5000                     │
│         │                                                │
│  ┌──────▼────────────────────────────────────┐          │
│  │     MLflow Model Registry                 │          │
│  │     - HousingPriceModel                   │          │
│  │     - Production Stage                    │          │
│  └───────────────────────────────────────────┘          │
└───────────────────────────────────────────────────────────┘
```

### Key Points Summary

1. **Kubeconfig:** Minikube automatically configures it when started
2. **Context:** Always use `minikube` context, not remote clusters
3. **MLflow URL:** 
   - From host: `http://127.0.0.1:XXXXX` (tunneled)
   - From pods: `http://mlflow-service:5000` (service name)
4. **Model:** Registered as `HousingPriceModel` in Production stage
5. **Features:** `bedrooms`, `bathrooms`, `area_sqft`, `lot_size`, `year_built`, `city`, `state`
6. **Ports:** May change after restarting minikube - always get fresh URLs

---

## Demo Flow

For your demo tomorrow, follow this flow:

1. **Setup (2 min)**
   - Show kubeconfig setup
   - Start minikube
   - Verify context

2. **Deploy MLflow (3 min)**
   - Build image
   - Generate manifests
   - Deploy
   - Show MLflow UI

3. **Train Model (2 min)**
   - Run training script
   - Show model in MLflow UI
   - Verify Production stage

4. **Deploy FastAPI (3 min)**
   - Build image
   - Deploy with MLflow connection
   - Show logs (model loading)

5. **Test (2 min)**
   - Health checks
   - Make predictions
   - Show Swagger UI

**Total: ~12 minutes**

---

## Support

If you encounter issues during the demo:

1. Check pod status: `kubectl get pods`
2. Check logs: `kubectl logs -l app=<service>`
3. Verify context: `kubectl config current-context`
4. Get fresh URLs: `minikube service <service> --url`

Good luck with your demo! 🚀

