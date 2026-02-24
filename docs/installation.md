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
deployml doctor
```

From here, install any tools that `doctor` says are not installed, and rerun the command.

- [Get Started →](tutorials/overview.md)