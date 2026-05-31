# Installation Guide

## Prerequisites

Install these tools first. `deployml doctor` checks all of them.

- Python 3.11 or newer
- Docker, running
- Terraform 1.0 or newer
- gcloud CLI

## Project setup checklist

Set up the project FIRST so the auth steps below can reference your project ID.

1. Create a GCP project. Either in the [GCP Console](https://console.cloud.google.com) or via CLI:
   ```bash
   gcloud projects create YOUR_GCP_PROJECT_ID --name="Your Project Name"
   ```
2. Link a billing account. Verify with `gcloud billing projects describe YOUR_GCP_PROJECT_ID`. Expect `billingEnabled: true`.
3. Confirm you have a sufficient IAM role on the project. `roles/owner` is the simplest. Or this explicit set:
   - `roles/serviceusage.serviceUsageAdmin`
   - `roles/artifactregistry.admin`
   - `roles/cloudsql.admin`
   - `roles/run.admin`
   - `roles/storage.admin`
   - `roles/bigquery.admin`
   - `roles/iam.serviceAccountAdmin`
   - `roles/iam.serviceAccountUser`

## Authenticate gcloud

Four commands. Run them after the project exists so you can pass its ID.

```bash
gcloud auth login                                                              # user auth
gcloud auth application-default login                                          # ADC for Terraform and client libs
gcloud auth application-default set-quota-project YOUR_GCP_PROJECT_ID          # bills BigQuery and client lib calls to the right project
gcloud auth configure-docker us-west1-docker.pkg.dev                           # Docker push to Artifact Registry
```

Replace `us-west1` with the region you plan to deploy in. The third command is critical. Skipping it leaves ADC pointing at whatever project you used last, and the example scripts fail with `USER_PROJECT_DENIED` if that project was deleted. The fourth command lets Docker push to Artifact Registry. Skipping it makes `deployml build-images` fail with `denied: User cannot access repository`.

## Install deployml

```bash
pip install deployml-core
```

## Verify

```bash
deployml doctor --project-id YOUR_GCP_PROJECT_ID
```

The doctor checks tool versions, authentication, ADC, the `bq` CLI, enabled APIs, and your IAM roles on the project. Install any missing tool and rerun until every line is green.

## Platform notes

deployml is tested on macOS and Linux. Windows users can run it with these caveats:

- The auth commands above and all `deployml` CLI calls work the same in PowerShell, cmd, and WSL.
- `export PATH=...` examples in the tutorials are bash. On PowerShell use `$env:PATH = "..." + $env:PATH`. On cmd use `set PATH=...;%PATH%`.
- Docker Desktop on Windows uses the WSL2 backend by default. `deployml build-images` against Cloud Build does not need a local Docker daemon, so the safest path is to skip local builds and let Cloud Build do the work.
- If you clone the repo on Windows, the included `.gitattributes` forces shell scripts and Dockerfiles to LF line endings. Without this, `docker build` would fail inside containers with `exec format error`.

- [Get Started →](tutorials/overview.md)
