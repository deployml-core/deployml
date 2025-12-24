# Tutorials Overview

Learn how to deploy MLflow and FastAPI using deployml.

## Deployment Options

### Cloud Run (Serverless)
- Automatic scaling
- Pay per use
- No infrastructure management
- [Get Started →](gcp-cloud-run.md)

### GKE (Kubernetes)
- Production-ready
- Full control
- Custom configurations
- [Get Started →](gke-deployment.md)

### Cloud VM
- Persistent storage
- Full control
- Cost-effective for long-running services
- [Get Started →](gcp-cloud-vm.md)

### Minikube (Local)
- Local testing
- No cloud costs
- Fast iteration
- [Get Started →](minikube.md)

## Quick Start

1. **Install deployml**
   ```bash
   pip install deployml
   ```

2. **Initialize your cloud project**
   ```bash
   deployml init --provider gcp --project-id YOUR_PROJECT_ID
   ```

3. **Generate a config**
   ```bash
   deployml generate
   ```

4. **Deploy**
   ```bash
   deployml deploy --config-path your-config.yaml
   ```

## Choose Your Deployment Type

| Feature | Cloud Run | GKE | Cloud VM | Minikube |
|---------|-----------|-----|----------|----------|
| Scaling | Automatic | Manual | Manual | N/A |
| Cost | Pay per use | Per node | Per VM | Free |
| Best For | Production APIs | Production workloads | Long-running services | Development |

## Next Steps

- Read the [Installation Guide](../installation.md)
- Explore [CLI Commands](../api/cli-commands.md)
- Check [FAQ](../faq.md)

