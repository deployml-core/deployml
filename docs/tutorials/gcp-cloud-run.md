# GCP Cloud Run Deployment

Deploy MLflow and FastAPI to Google Cloud Run using deployml.

## Overview

Cloud Run is a serverless container platform that automatically scales your applications. It's ideal for:

- Automatic scaling
- Pay per use
- No infrastructure management
- Fast deployment

## Quick Start

### 1. Create Configuration File

Create `cloud-run-config.yaml`:

```yaml
name: mlflow-cloud-run
provider:
  name: gcp
  project_id: YOUR_PROJECT_ID
  region: us-west1

deployment:
  type: cloud_run

stack:
  - experiment_tracking:
      name: mlflow
      params:
        service_name: mlflow-server
        allow_public_access: true
  
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
        service_name: fastapi-server
        mlflow_tracking_uri: http://mlflow-server:8080
```

### 2. Initialize GCP Project

```bash
# Initialize GCP project (first time only)
deployml init --provider gcp --project-id YOUR_PROJECT_ID
```

### 3. Deploy

```bash
# Deploy stack
deployml deploy --config-path cloud-run-config.yaml
```

### 4. Access Services

After deployment, you'll see URLs like:

```
MLflow URL: https://mlflow-server-xxxxx-uw.a.run.app
FastAPI URL: https://fastapi-server-xxxxx-uw.a.run.app
```

## Configuration Options

### MLflow with PostgreSQL

```yaml
stack:
  - experiment_tracking:
      name: mlflow
      params:
        backend_store_uri: postgresql://user:pass@host:5432/dbname
```

### Custom Resource Limits

```yaml
stack:
  - model_serving:
      name: fastapi
      params:
        memory: 2Gi
        cpu: 1000m
        max_instances: 10
```

### Auto-Teardown

```yaml
teardown:
  enabled: true
  duration_hours: 24
  time_zone: UTC
```

## Cost Management

```bash
# Enable cost analysis (default)
deployml deploy --config-path config.yaml

# Review costs before deploying
# deployml will show estimated monthly costs
```

## Testing

```bash
# Test MLflow health
curl https://mlflow-server-xxxxx-uw.a.run.app/health

# Test FastAPI health
curl https://fastapi-server-xxxxx-uw.a.run.app/health

# Test prediction endpoint
curl -X POST "https://fastapi-server-xxxxx-uw.a.run.app/predict" \
  -H "Content-Type: application/json" \
  -d '{"features": {...}}'
```

## Cleanup

```bash
# Destroy infrastructure
deployml destroy --config-path cloud-run-config.yaml

# Clean workspace
deployml destroy --config-path cloud-run-config.yaml --clean-workspace
```

## Troubleshooting

### Service Not Starting

```bash
# Check service logs
gcloud run services logs read SERVICE_NAME --region REGION

# Check service status
gcloud run services describe SERVICE_NAME --region REGION
```