# Features Overview

deployml is a Python library that deploys a complete MLOps infrastructure in GCP with a single command. It was built for academic use — the goal is to get the infrastructure out of the way so students can focus on the ML.

## How it works

You define your stack in a YAML config file, run `deployml deploy`, and Terraform provisions everything in GCP. When you're done, `deployml destroy` tears it all down cleanly.

## Deployment targets

Cloud Run is the primary, fully supported target and is what the rest of this page describes. The same MLflow and FastAPI stack can also run on Kubernetes, selected by `deployment.type` in your config:

- `cloud_run` — serverless on GCP Cloud Run, the default.
- `gke` — a Google Kubernetes Engine cluster, where MLflow gets a PersistentVolumeClaim so experiment data survives pod restarts.
- Local **minikube**, for testing without GCP, via the `minikube-*` and `mlflow-*` commands.

See [CLI Commands](../api/cli-commands.md) and the [GKE flow notes](../tutorials/gcp-cloud-run.md#gke-flow-notes) for the Kubernetes paths.

## What gets deployed

### Experiment Tracking, Artifact Storage, and Model Registry — MLflow

A single MLflow server running in Cloud Run, backed by:
- Cloud SQL (Postgres) for experiment metadata
- GCS bucket for model artifacts

Use it to track experiments, store models, and manage model versions.

### Model Serving — FastAPI

A FastAPI container running in Cloud Run. On startup it pulls the latest registered model from MLflow and serves predictions at `/predict`.

### Model Monitoring — Grafana

A Grafana container running in Cloud Run, connected to a `metrics` Postgres database. Use it to build dashboards for tracking model performance over time.

### Feature and Monitoring Tables — BigQuery

Four BigQuery tables are created automatically in the `mlops` dataset:

| Table | Purpose |
|---|---|
| `offline_features` | Precomputed input features for training and serving |
| `predictions` | Model predictions logged at serving time |
| `ground_truth` | Actual outcomes, matched back to predictions |
| `drift_metrics` | Summary statistics for monitoring model drift |

## What's not included (yet)

- AWS and Azure support (planned)
- Data versioning
- LLMs / generative AI
- Scalable model training
