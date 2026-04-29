# MLOps Application — Project Plan

## Project Description

Easy-to-use, scalable, modular, and lightweight library for deploying MLOps infrastructure in the cloud, targeting academic use (GCP → AWS → Azure). Goal is to reduce friction for instructors and students so they can focus on building rather than debugging environment setup.

## Goals

- Software application with documentation and website
- Paper for publication (JOSS, pyopensci, or a journal)

## Phases

- **Phase 1** — GCP: one tool per MLOps stage, tested, documented, website with end-to-end example. Target: early September 2025.
- **Phase 2** — AWS: extend, test, update docs/website/example. Target: December 2025.
- **Phase 3** — Azure: lower priority.

## MLOps Tools

| Stage | Tool | Notes |
|---|---|---|
| Experiment Tracking | MLflow | Tracking server + Cloud SQL + database |
| Artifact Tracking | MLflow | GCS bucket + tracking server |
| Model Registry | MLflow | GCS bucket + tracking server |
| Model Serving | FastAPI (online) | Container in Cloud Run pulling latest registered model |
| Model Monitoring | From scratch | BigQuery/Postgres tables + Grafana dashboard + scheduled container for drift metrics |
| Operational Monitoring | Grafana | Cloud Run container connected to monitoring tables |
| Feature Store | From scratch | BigQuery tables |
| Data Versioning | Not included | — |

## App Commands

| Command | Description |
|---|---|
| `doctor` | System checks for local dependencies |
| `init` | Enable APIs, create empty config + example Dockerfiles |
| `build-images` | Build all images in `docker/` folder in GCP Artifact Registry |
| `deploy` | Render Terraform templates from config.yaml and apply |
| `get-urls` | Extract infra connection info / URLs |
| `destroy` | Terraform destroy wrapper |

## Repo Structure (relevant parts)

| Folder | Subfolder | Purpose |
|---|---|---|
| `docs/` | | MKdocs documentation files |
| `example/config/` | | Sample configs — focus on `gcp-sample.yaml` / `gcp-sample-slim.yaml` |
| `notebooks/` | | Test notebooks — focus on `notebook_cli_demo.ipynb` |
| `src/deployml/cli/` | | CLI command implementations |
| `src/deployml/diagnostics/` | | Doctor command |
| `src/deployml/docker/` | | Example Dockerfiles shipped with the app |
| `src/deployml/notebook/` | | Jupyter notebook API (non-CLI interface) |
| `src/deployml/templates/gcp/cloud_run/` | | Jinja2 Terraform templates — main focus |
| `src/deployml/terraform/modules/` | | Terraform modules: `bigquery/`, `cloud_sql_postgres/`, `fastapi/`, `mlflow/`, `grafana/`, `teardown/` |
| `src/deployml/utils/` | | Helper functions for CLI and notebook |

## What Needs to be Completed

### Cloud Run Services

- [x] **1. Grafana in Cloud Run** — working as of last session
- [x] **2. MLflow in Cloud Run** — working as of last session

### Infrastructure

- [x] **3. BigQuery table auto-creation** — wired into deploy; creates `mlops` dataset with all 4 tables
  - `offline_features`
  - `predictions`
  - `ground_truth`
  - `drift_metrics`
- [x] **4. .env file generation** — `deployml get-urls` prints URLs and writes `.env`

### End-to-End Example

- [ ] **5a.** Example training dataset → load into BigQuery
- [ ] **5b.** Training script with MLflow experiment tracking
- [ ] **5c.** Model registration in MLflow
- [ ] **5d.** Feature creation script → store in `offline_features` BigQuery table
- [ ] **5e.** Model scoring script for FastAPI container (pulls latest registered model from MLflow)
- [ ] **5f.** Prediction script → call deployed FastAPI, store results in `predictions` BigQuery table
- [ ] **5g.** Fake ground truth script → populate `ground_truth` BigQuery table
- [ ] **5h.** Drift metrics script → compute and store in `drift_metrics` BigQuery table
- [ ] **5i.** Grafana model monitoring dashboard

### Documentation

- [ ] MKdocs site with MKdocstrings for API docs
- [ ] End-to-end example page on website

## Notes / Known Issues

- Terraform state lives in `.deployml/<config_name>/`; lock file may need manual deletion between deploys
- Feast, cron, Weights & Biases, VM, and Local options exist in the repo but are deprioritized — may be removed later to streamline
- GCP deploy uses Cloud Run (no K8s)
- `pip install -e .` for local development
