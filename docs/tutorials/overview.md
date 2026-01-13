# Tutorials Overview

Learn how to deploy a simple MLOps infrastructure using deployml.

## Deployment Options

### Minikube (Local)

This infrastructure will use minikube and will be deployed locally, which is useful for practicing with Kubernetes locally before going to the cloud. Note that this is limited to deploying MLFlow and FastAPI, and still requires knowledge of minikube and kubectl commands.

- Local testing
- No cloud costs
- Fast iteration
- [Get Started →](minikube.md)

### Cloud Run (Serverless)

This infrastructure will be deployed in the cloud using a serverless architecture.

- Automatic scaling
- Pay per use
- No infrastructure management
- [Get Started →](gcp-cloud-run.md)

### GKE (Kubernetes)

This infrastructure will be deployed in the cloud, with some components running in Kubernetes rather than serverless.

- Production-ready
- Full control
- Custom configurations
- [Get Started →](gke-deployment.md)

### Cloud VM

This infrastructure is launched entirely within a VM in the cloud. 

- Persistent storage
- Full control
- Cost-effective for long-running services
- [Get Started →](gcp-cloud-vm.md)

## Choose Your Deployment Type

| Feature | Cloud Run | GKE | Cloud VM | Minikube |
|---------|-----------|-----|----------|----------|
| Scaling | Automatic | Manual | Manual | N/A |
| Cost | Pay per use | Per node | Per VM | Free |
| Best For | Production APIs | Production workloads | Long-running services | Development |
