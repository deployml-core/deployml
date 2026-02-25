# Tutorials Overview

Learn how to deploy a simple MLOps infrastructure using deployml.

## Quick Start

Once all dependencies are installed, there are six primary steps to using deployml:

1. Create a project in GCP (unless you are deploying everything locally with minikube).   
2. Initialize a project with `deployml init`. This will enable the necessary APIs in your GCP project. You can check that APIs are enabled by running `doctor`.  
3. Generate and edit a configuration yaml file. Use `deployml generate` to create the file and then open in a text editor to edit it.  
4. Deploy your infrastructure using `deployml deploy`.  
5. Develop, deploy, and maintain your ML model. See example tutorials below for more guidance on this step.  
6. Destroy the infrastructure using `deployml destroy`.  

```bash
# Initialize GCP project
deployml init --provider gcp --project-id YOUR_PROJECT_ID

# Check APIs
deployml doctor --project-id YOUR_PROJECT_ID

# Generate a sample config
deployml generate

# Deploy your stack
deployml deploy --config-path your-config.yaml
```

## Deployment Options

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

### Minikube (Local)

This infrastructure is limited to deploying MLFlow and FastAPI locally using minikube, and is only useful for practicing with Kubernetes locally before going to the cloud. This option is **not** for deploying a full pipeline, and still requires knowledge of minikube and kubectl commands.

- Local testing
- No cloud costs
- Fast iteration
- [Get Started →](minikube.md)