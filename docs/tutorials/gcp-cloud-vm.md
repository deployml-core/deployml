# GCP Cloud VM Deployment

Deploy MLflow to Google Cloud VM using deployml.

## Overview

Cloud VM deployment provides persistent storage and full control over your infrastructure. It's ideal for:

- Persistent storage
- Full control
- Cost-effective for long-running services
- Custom configurations

## Quick Start

### 1. Create Configuration File

Create `cloud-vm-config.yaml`:

```yaml
name: mlflow-cloud-vm
provider:
  name: gcp
  project_id: YOUR_PROJECT_ID
  region: us-west1
  zone: us-west1-a

deployment:
  type: cloud_vm

stack:
  - experiment_tracking:
      name: mlflow
      params:
        vm_name: mlflow-vm
        machine_type: e2-medium
        disk_size_gb: 20
        mlflow_port: 5000
        backend_store_uri: sqlite:///mlflow.db
  
  - artifact_tracking:
      name: mlflow
      params:
        artifact_bucket: mlflow-artifacts-bucket
        create_artifact_bucket: true
```

### 2. Initialize GCP Project

```bash
# Initialize GCP project (first time only)
deployml init --provider gcp --project-id YOUR_PROJECT_ID
```

### 3. Deploy

```bash
# Deploy stack
deployml deploy --config-path cloud-vm-config.yaml
```

### 4. Access VM

After deployment, you'll get the VM's external IP address. Access MLflow via:

```
http://VM_EXTERNAL_IP:5000
```

## Configuration Options

### Custom Machine Type

```yaml
stack:
  - experiment_tracking:
      name: mlflow
      params:
        machine_type: e2-standard-4  # 4 vCPU, 16GB RAM
        disk_size_gb: 50
```

### PostgreSQL Backend

```yaml
stack:
  - experiment_tracking:
      name: mlflow
      params:
        backend_store_uri: postgresql://user:pass@host:5432/dbname
```

## SSH Access

```bash
# SSH into VM
gcloud compute ssh mlflow-vm --zone us-west1-a

# Check MLflow status
sudo systemctl status mlflow

# View MLflow logs
sudo journalctl -u mlflow -f
```

## Cleanup

```bash
# Destroy infrastructure
deployml destroy --config-path cloud-vm-config.yaml

# Clean workspace
deployml destroy --config-path cloud-vm-config.yaml --clean-workspace
```

## Troubleshooting

### VM Not Accessible

```bash
# Check VM status
gcloud compute instances describe mlflow-vm --zone us-west1-a

# Check firewall rules
gcloud compute firewall-rules list --filter="name~mlflow"
```

### MLflow Not Running

```bash
# SSH into VM
gcloud compute ssh mlflow-vm --zone us-west1-a

# Check service status
sudo systemctl status mlflow

# Restart service
sudo systemctl restart mlflow
```

## Next Steps

- Learn about [Cloud Run deployment](gcp-cloud-run.md) for serverless
- Explore [GKE deployment](gke-deployment.md) for Kubernetes
- Check [CLI Commands](../api/cli-commands.md) reference

