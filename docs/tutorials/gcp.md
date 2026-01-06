# GCP Deployment Guide

DeployML supports multiple deployment types on Google Cloud Platform.

## Deployment Types

### Cloud Run (Serverless)
Serverless container deployment for MLflow and FastAPI services.

**Features:**
- Automatic scaling
- Pay per use
- No infrastructure management

[Get Started →](gcp-cloud-run.md)

### GKE (Google Kubernetes Engine)
Kubernetes-based deployment for production workloads.

**Features:**
- Production-ready
- Full control
- Custom configurations
- Two-step workflow (generate manifests, then apply)

[Get Started →](gke-deployment.md)

### Cloud VM
Virtual machine deployment for MLflow and other services.

**Features:**
- Persistent storage
- Full control
- Cost-effective for long-running services

[Get Started →](gcp-cloud-vm.md)

## Quick Start

1. **Install deployml**
   ```bash
   pip install deployml-core
   ```

2. **Initialize GCP project**
   ```bash
   deployml init --provider gcp --project-id YOUR_PROJECT_ID
   ```

3. **Choose your deployment type**
   - [Cloud Run](gcp-cloud-run.md) - Serverless, auto-scaling
   - [GKE](gke-deployment.md) - Kubernetes, production-ready
   - [Cloud VM](gcp-cloud-vm.md) - Persistent storage, full control

4. **Deploy**
   ```bash
   deployml deploy --config-path your-config.yaml
   ```

## Comparison

| Feature | Cloud Run | GKE | Cloud VM |
|---------|-----------|-----|----------|
| Scaling | Automatic | Manual | Manual |
| Cost | Pay per use | Per node | Per VM |
| Best For | Production APIs | Production workloads | Long-running services |
| Setup Time | Fast | Medium | Medium |

## Next Steps

- Read the [Installation Guide](../installation.md)
- Explore [CLI Commands](../api/cli-commands.md)
- Check [FAQ](../faq.md) for common issues

