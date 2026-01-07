# API Reference Overview

deployml provides a command-line interface (CLI) for deploying and managing MLOps infrastructure. This section documents all available commands and their usage.

## Command Categories

### Core Commands

Core commands handle the primary deployment workflow. 

- The `deploy` command provisions infrastructure based on your YAML configuration file.  
- The `destroy` command tears down infrastructure and optionally cleans up workspace files.  
- The `init` command initializes your cloud project by enabling required APIs.  
- The `generate` command creates a deployment configuration interactively.  
- The `doctor` command runs system checks to verify required tools and authentication.

### Deployment Commands

Deployment-specific commands support different deployment types.  

- **GKE** commands handle Kubernetes deployments with a two-step workflow: generate manifests, then apply them.  
- **Minikube** commands support local development and testing.  
- **MLflow-specific** commands simplify MLflow deployment workflows.

### Management Commands

Management commands help you control deployed infrastructure. **Teardown** commands manage automatic infrastructure destruction, allowing you to schedule, cancel, check status, and update teardown schedules.

## Getting Started

To get started with deployml commands:  

- First install deployml.  
- Run the doctor command to verify your setup.  
- Then use the generate command to create a configuration file, or create one manually. 
- Finally, use the deploy command to provision your infrastructure.

For detailed command documentation, see the [CLI Commands](cli-commands.md) reference.

## Next Steps

- Explore [CLI Commands](cli-commands.md) for complete command reference
- Check [Installation Guide](../installation.md) for setup instructions
- Review [Tutorials](../tutorials/overview.md) for step-by-step guides

