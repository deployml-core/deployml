# GCP Cloud Run Tutorial

This tutorial walks you through deploying a full MLOps stack on GCP using Cloud Run. By the end you will have MLflow (experiment tracking, artifact storage, model registry), FastAPI (model serving), and Grafana (monitoring dashboard) running in the cloud.

## Prerequisites

Make sure `deployml doctor` passes before starting. You will need:

- `gcloud` CLI, authenticated (`gcloud auth login` and `gcloud auth application-default login`)
- Docker (running)
- Terraform

## 1. Create a GCP Project

Create a new project in the [GCP Console](https://console.cloud.google.com) and enable billing. Note your project ID — you will use it throughout this tutorial.

## 2. Initialize the Project

`init` enables the required GCP APIs and creates the Artifact Registry repository that your Docker images will be pushed to.

```bash
deployml init --provider gcp --project-id YOUR_PROJECT_ID
```

This only needs to be run once per project. It takes a few minutes while GCP enables APIs.

## 3. Create a Configuration File

Create a file called `config.yaml` in your project directory. This tells deployml which services to deploy.

```yaml
name: gcp-mlops-stack-mlflow
provider:
  name: gcp
  project_id: YOUR_PROJECT_ID
  region: us-west1
deployment:
  type: cloud_run
stack:
  - experiment_tracking:
      name: mlflow
      params:
        service_name: mlflow-server
  - artifact_tracking:
      name: mlflow
  - model_registry:
      name: mlflow
      params:
        backend_store_uri: postgresql
  - model_serving:
      name: fastapi
      params:
        service_name: fastapi-mlflow-server
  - model_monitoring:
      name: grafana
      params:
        service_name: grafana-server
```

**What each block does:**

- `experiment_tracking` + `artifact_tracking` + `model_registry` — these three together deploy a single MLflow server backed by Cloud SQL (Postgres) for metadata and a GCS bucket for artifacts
- `model_serving` — deploys a FastAPI container that pulls the latest registered model from MLflow on startup
- `model_monitoring` — deploys Grafana connected to the Postgres `metrics` database

## 4. Build Docker Images

deployml ships with example Dockerfiles for each service. Run `init` first to copy these into your project's `docker/` folder, then build and push them to Artifact Registry:

```bash
deployml build-images --docker-root docker --gcp-project YOUR_PROJECT_ID --region us-west1
```

This builds images for MLflow, FastAPI, and Grafana and pushes them to:
`us-west1-docker.pkg.dev/YOUR_PROJECT_ID/mlops-images/`

Building takes a few minutes. You only need to rebuild if you change a Dockerfile or the application code inside a container.

## 5. Deploy

```bash
deployml deploy --config-path config.yaml --verbose
```

`--verbose` streams Terraform output directly so you can see what's being created. Without it you get a progress bar. Deployment takes roughly 5–10 minutes.

What gets created:

- Cloud SQL Postgres instance with `mlflow` and `metrics` databases
- GCS bucket for MLflow artifacts
- Artifact Registry repository (if not already created by `init`)
- Cloud Run services for MLflow, FastAPI, and Grafana
- IAM service accounts and bindings
- VPC connector for private Cloud SQL access

## 6. Get Service URLs

```bash
deployml get-urls --config-path config.yaml
```

This prints all service URLs and writes them to a `.env` file in the current directory. Example output:

```
  experiment_tracking_mlflow_url: https://mlflow-server-xxxx-uw.a.run.app
  model_serving_fastapi_url: https://fastapi-mlflow-server-xxxx-uw.a.run.app
  model_monitoring_grafana_url: https://grafana-server-xxxx-uw.a.run.app

 .env written to /your/project/.env
```

You can source the `.env` in your shell or point your scripts at it to avoid hardcoding URLs:

```bash
source .env
```

## 7. Verify the Stack

**MLflow**

Open the MLflow URL in your browser — you should see the MLflow UI with no experiments yet.

```bash
curl https://YOUR_MLFLOW_URL/health
```

**FastAPI**

```bash
curl https://YOUR_FASTAPI_URL/health
```

The `/docs` endpoint gives you the auto-generated OpenAPI UI.

**Grafana**

Open the Grafana URL in your browser. Default credentials are `admin` / `admin`. You will be prompted to change the password on first login.

**BigQuery**

Verify the `mlops` dataset and all four tables were created:

```bash
bq ls --project_id=YOUR_PROJECT_ID mlops
```

You should see `offline_features`, `predictions`, `ground_truth`, and `drift_metrics`.

## 8. Teardown

When you are done, destroy all infrastructure to avoid ongoing charges:

```bash
deployml destroy --config-path config.yaml
```

This deletes all Cloud Run services, Cloud SQL instance, GCS bucket contents, and Terraform state. It does not delete the Artifact Registry images or the GCP project itself.

## Troubleshooting

**Terraform lock file error**

If a previous deploy was interrupted, you may see a lock file error. Delete the lock file and retry:

```bash
rm ~/.deployml/YOUR_CONFIG_NAME/.terraform.lock.hcl
deployml deploy --config-path config.yaml --verbose
```

**Service logs**

```bash
gcloud run services logs read SERVICE_NAME --project YOUR_PROJECT_ID --region us-west1
```

**Cloud SQL connection issues**

If destroy fails with an active connections error, the Cloud Run services may not have been fully shut down. Re-run destroy — it will retry the Cloud SQL cleanup.
