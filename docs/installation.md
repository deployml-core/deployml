# Installation Guide

## Prerequisites

Before installing deployml, ensure you have:

- **Python 3.8+**
- **Docker** (for building container images)
- **Cloud CLI tools** (gcloud for GCP, aws-cli for AWS)
- **Terraform** (for infrastructure provisioning)
- **kubectl** (for Kubernetes deployments)

## Install deployml

### Using pip

```bash
pip install deployml-core
```

### From source

```bash
git clone https://github.com/deployml-core/deployml.git
cd deployml
pip install -e .
```

## Verify Installation

```bash
# Check version
deployml --version
```

Check that you have the right dependencies. By "dependencies" we do not simply mean python libraries. To make full use of this application, you will need other tools installed on your laptop, and the below command will tell you which tools you do not have installed. **Note:** in order for deployml to recognize Docker, you must have Docker running.

```
# Run system checks
deployml doctor --project-id YOUR_PROJECT_ID
```

## Quick Start

Once dependencies are installed, there are six primary steps to using deployml:

1. Create a project in GCP unless you are deploying things locally.   
2. Initialize a project with `deployml init`.   
3. Generate and edit a configuration yaml file. Use `deployml generate` to create the file and then open in a text editor to edit it.  
4. Deploy your infrastructure using `deployml deploy`.  
5. Develop, deploy, and maintain your ML model. See example in the tutorials section for more guidance on this step.  
6. Destroy the infrastructure using `deployml destroy`.  

```bash
# Initialize GCP project
deployml init --provider gcp --project-id YOUR_PROJECT_ID

# Generate a sample config
deployml generate

# Deploy your stack
deployml deploy --config-path your-config.yaml
```