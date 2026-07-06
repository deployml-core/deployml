# deployml

A CLI tool that deploys a production MLOps stack on GCP with a single command. Built for academic ML courses so students can focus on building models, not infrastructure.

## What you get

- **MLflow** — experiment tracking, artifact storage, and model registry (backed by Cloud SQL Postgres + GCS)
- **FastAPI** — model serving endpoint that loads the latest registered model from MLflow automatically
- **Grafana** — monitoring dashboard connected to your metrics database
- **BigQuery** — `mlops` dataset with tables for features, predictions, ground truth, and drift metrics

All running on GCP Cloud Run. No servers to manage. Cloud Run services scale to zero when idle. Cloud SQL and BigQuery storage incur baseline cost. See Costs below.

## Quick Start

**1. Install**

```bash
pip install deployml-core
```

**2. Initialize your GCP project** (enables APIs, creates Artifact Registry)

```bash
deployml init --provider gcp --project-id YOUR_GCP_PROJECT_ID
```

**3. Configure**

```bash
cp config.example.yaml config.yaml
# Edit config.yaml and set your project_id
```

**4. Build images**

```bash
deployml build-images --create-repo
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

Deletes all Cloud Run services, Cloud SQL, the GCS bucket, and the BigQuery dataset, and also removes the Artifact Registry repo and the Cloud Build staging bucket that `build-images` created, so a destroyed project leaves no billing residue. Does not delete the GCP project itself.

## Full Tutorial

See [docs/tutorials/gcp-cloud-run.md](docs/tutorials/gcp-cloud-run.md) for a step-by-step walkthrough.

## Other deployment targets

Cloud Run is the primary, fully supported path. The CLI also supports Kubernetes for users who want a cluster:

- **Local minikube**, for testing without GCP: `mlflow-init` and `mlflow-deploy`, or `minikube-init` and `minikube-deploy`.
- **GKE** on GCP: `gke-cluster-create`, `gke-init`, then `gke-deploy` or `gke-apply`, torn down with `gke-destroy`.

MLflow keeps its data on a PersistentVolumeClaim in both, so experiments survive pod restarts. See [CLI Commands](docs/api/cli-commands.md) and the [GKE flow notes](docs/tutorials/gcp-cloud-run.md#gke-flow-notes).

## Requirements

- Python 3.11 or newer
- `gcloud` CLI, authenticated with `gcloud auth login`, `gcloud auth application-default login`, and `gcloud auth configure-docker us-west1-docker.pkg.dev`
- Docker, running
- Terraform 1.0 or newer

Run `deployml doctor --project-id YOUR_GCP_PROJECT_ID` to verify auth, ADC, tool versions, enabled APIs, and IAM roles on your project.

## Costs

Cloud Run scales to zero when idle. Cloud SQL Postgres and BigQuery storage do not. Expect roughly $30 to $80 per month while the stack is up. MLflow runs with `min_instances = 1` by default for snappy UI, which adds about $5 per month. Set `min_instances` to 0 if you want zero idle cost in exchange for cold starts. Always run `deployml destroy` when done.
