# deployml

A CLI tool that deploys a production MLOps stack on GCP with a single command. Built for academic ML courses so students can focus on building models, not infrastructure.

## What you get

- **MLflow** — experiment tracking, artifact storage, and model registry (backed by Cloud SQL Postgres + GCS)
- **FastAPI** — model serving endpoint that loads the latest registered model from MLflow automatically
- **Grafana** — monitoring dashboard connected to your metrics database
- **BigQuery** — `mlops` dataset with tables for features, predictions, ground truth, and drift metrics

All running on GCP Cloud Run — no servers to manage, scales to zero when idle.

## Quick Start

**1. Install**

```bash
pip install deployml-core
```

**2. Initialize your GCP project** (enables APIs, creates Artifact Registry)

```bash
deployml init --provider gcp --project-id YOUR_PROJECT_ID
```

**3. Configure**

```bash
cp config.example.yaml config.yaml
# Edit config.yaml and set your project_id
```

**4. Build images**

```bash
deployml build-images
```

**5. Deploy**

```bash
deployml deploy --verbose
```

First deploy takes ~20 minutes (Cloud SQL provisioning). Subsequent deploys are 1–2 minutes.

**6. Get your URLs**

```bash
deployml get-urls
```

Prints service URLs and writes a `.env` file with `MLFLOW_URL`, `FASTAPI_URL`, `GRAFANA_URL`, `BIGQUERY_PROJECT`, and `BIGQUERY_DATASET`.

## End-to-End Example

Once deployed, the `example/` directory walks through a complete MLOps workflow using a synthetic housing price dataset:

```bash
pip install mlflow scikit-learn pandas numpy google-cloud-bigquery db-dtypes python-dotenv requests

python example/scripts/01_load_training_data.py   # load 500 rows into BigQuery
python example/scripts/02_train_model.py           # train RandomForest, log to MLflow
python example/scripts/03_register_model.py        # register model as Production
python example/scripts/04_make_predictions.py      # serve 50 predictions via FastAPI
python example/scripts/05_generate_ground_truth.py # simulate actual outcomes
python example/scripts/06_compute_drift_metrics.py # compute feature drift + MAE
python example/scripts/07_setup_grafana.py         # provision monitoring dashboard
```

See [example/README.md](example/README.md) for details.

## Teardown

```bash
deployml destroy
```

Deletes all Cloud Run services, Cloud SQL, GCS bucket, and BigQuery dataset. Does not delete Artifact Registry images or the GCP project.

## Full Tutorial

See [docs/tutorials/gcp-cloud-run.md](docs/tutorials/gcp-cloud-run.md) for a step-by-step walkthrough.

## Requirements

- Python 3.10+
- `gcloud` CLI (authenticated)
- Docker (running)
- Terraform
