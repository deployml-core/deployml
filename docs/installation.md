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

deployml runs on macOS, Linux, and native Windows. The CLI commands are identical
across all three. The engine detects the operating system and adapts underneath, so
you type the same `deployml` commands everywhere.

### Windows

deployml works on native Windows in PowerShell or cmd. A few setup notes keep it
smooth and let it work out of the box:

- Toolchain. Install native Windows builds of Python 3.11 or newer, Git for
  Windows, the gcloud SDK, Terraform, and Docker Desktop. For the Kubernetes paths
  also install minikube and run `gcloud components install gke-gcloud-auth-plugin`.
  `deployml doctor` checks the core tools.
- Python. Install from python.org, then create the virtual environment with the
  launcher, `py -3.11 -m venv .venv`. A bare `python` on a fresh Windows often
  resolves to the Microsoft Store stub, which is not a usable interpreter.
- Git for Windows is required, not optional. It provides the `bash` that the Cloud
  SQL readiness step runs under during `deployml deploy`. Confirm `bash --version`
  resolves before you deploy.
- Keep the project and its working directory off OneDrive. OneDrive holds file
  handles open and can make workspace cleanup on `deployml destroy` fail with a
  PermissionError. A path such as `C:\dev\your-project` avoids this.
- gcloud, bq, and gsutil ship as `.cmd` wrappers on Windows. deployml resolves and
  invokes them correctly for you. If you run gcloud yourself in PowerShell and see
  "running scripts is disabled", call `gcloud.cmd` instead of `gcloud`, or run it
  from cmd.

### Path syntax across shells

- The `export PATH=...` examples in the tutorials are bash. In PowerShell use
  `$env:PATH = "...;" + $env:PATH`. In cmd use `set PATH=...;%PATH%`.

### Docker and line endings

- Docker Desktop on Windows uses the WSL2 backend by default. The Cloud Run path
  builds images with Cloud Build and does not need a local Docker daemon, so for
  Cloud Run you can skip local builds. Docker is needed only for the minikube path.
- If you clone the repo on Windows, the included `.gitattributes` forces shell
  scripts and Dockerfiles to LF line endings. Without this, `docker build` would
  fail inside containers with `exec format error`.

- [Get Started →](tutorials/overview.md)
