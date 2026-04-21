# API Reference Overview

deployml provides a command-line interface (CLI) for deploying and managing MLOps infrastructure on GCP.

## Commands

| Command | Description |
|---|---|
| `deployml doctor` | Check local dependencies |
| `deployml init` | Enable required GCP APIs |
| `deployml build-images` | Build and push Docker images to Artifact Registry |
| `deployml deploy` | Deploy the stack from a config file |
| `deployml get-urls` | Print service URLs and write `.env` file |
| `deployml destroy` | Tear down all infrastructure |

See [CLI Commands](cli-commands.md) for full usage details.
