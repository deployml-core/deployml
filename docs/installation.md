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

Check that you have the right dependencies.
```
# Run system checks
deployml doctor --project-id YOUR_PROJECT_ID
```

## Quick Start

```bash
# Initialize GCP project
deployml init --provider gcp --project-id YOUR_PROJECT_ID

# Generate a sample config
deployml generate

# Deploy your stack
deployml deploy --config-path your-config.yaml
```