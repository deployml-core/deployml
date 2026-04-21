# Tutorials Overview

Learn how to deploy a full MLOps infrastructure using deployml.

## GCP Cloud Run

The primary supported deployment target is GCP using Cloud Run — a serverless architecture that scales automatically and is cost-effective for academic use.

**[Get Started with GCP Cloud Run →](gcp-cloud-run.md)**

## Quick Reference

```bash
# 1. Check dependencies
deployml doctor

# 2. Enable GCP APIs
deployml init --provider gcp --project-id YOUR_PROJECT_ID

# 3. Build Docker images
deployml build-images --docker-root docker --gcp-project YOUR_PROJECT_ID --region us-west1

# 4. Deploy the stack
deployml deploy --config-path config.yaml --verbose

# 5. Get service URLs and write .env
deployml get-urls --config-path config.yaml

# 6. Tear down when done
deployml destroy --config-path config.yaml
```
