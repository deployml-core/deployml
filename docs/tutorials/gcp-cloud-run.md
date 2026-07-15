# GCP Cloud Run Tutorial

This tutorial walks you through deploying a full MLOps stack on GCP using Cloud Run. By the end you will have MLflow, FastAPI, and Grafana running in the cloud.

## Prerequisites

Run `deployml doctor --project-id YOUR_GCP_PROJECT_ID` first. It checks everything in the [installation guide](../installation.md). Make sure the IAM and API checks pass before you continue.

## 1. Create and prepare your GCP project

1. Create a project in the [GCP Console](https://console.cloud.google.com). Note the project ID.
2. Link a billing account. Verify with `gcloud billing projects describe YOUR_GCP_PROJECT_ID`. The output should include `billingEnabled: true`.
3. Confirm you have a sufficient IAM role on the project. `roles/owner` is the simplest. See the [installation guide](../installation.md) for the minimum explicit set.

## 2. Initialize the project

`init` enables the required GCP APIs and creates a local `docker/` folder and `config.yaml` template.

```bash
deployml init --provider gcp --project-id YOUR_GCP_PROJECT_ID
```

This only needs to be run once per project. API enablement takes a few minutes.

## 3. Review the configuration file

`init` already wrote a runnable `config.yaml` with your project ID filled in. Inspect it and adjust service names, region, or `image_tag` if you need to. The default looks like this:

```yaml
name: gcp-mlops-stack-mlflow
provider:
  name: gcp
  project_id: YOUR_GCP_PROJECT_ID
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
      params:
        artifact_bucket: mlflow-artifacts-YOUR_GCP_PROJECT_ID
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

- `experiment_tracking` + `artifact_tracking` + `model_registry` together deploy a single MLflow server backed by Cloud SQL Postgres for metadata and a GCS bucket for artifacts.
- `model_serving` deploys a FastAPI container that pulls the latest registered model from MLflow on startup.
- `model_monitoring` deploys Grafana connected to the Postgres `metrics` database.

## 4. Build Docker images

```bash
deployml build-images --create-repo
```

This reads your project ID and region from `config.yaml` and pushes images for MLflow, FastAPI, and Grafana to:
`us-west1-docker.pkg.dev/YOUR_GCP_PROJECT_ID/mlops-images/`

The first build creates the Artifact Registry repo. Subsequent runs reuse it. Builds run on Cloud Build, so you do not need a local Docker daemon for this step.

## 5. Deploy

```bash
deployml deploy --verbose
```

Deploy prompts `Do you want to deploy the stack? [y/N]` before applying. Type `y` to proceed. Pass `--yes` to skip the prompt in scripts.

`--verbose` streams Terraform output directly. The first deployment takes roughly 20 minutes because Cloud SQL Postgres provisioning is slow.

What gets created:

- Cloud SQL Postgres instance with `mlflow` and `metrics` databases. The public IP is allocated but no client network is authorized, so the DB is reachable only from Cloud Run via the Cloud SQL Auth Proxy tunnel.
- GCS bucket for MLflow artifacts
- Cloud Run services for MLflow, FastAPI, and Grafana. MLflow runs with `min_instances = 1` to avoid cold starts on the tracking server.
- BigQuery `mlops` dataset with four tables
- IAM service accounts and bindings

## 6. Costs

While the stack is up, expect rough monthly cost in the $30 to $80 range depending on usage:

- Cloud SQL Postgres `db-g1-small`: about $25 per month, even when idle.
- MLflow Cloud Run with `min_instances = 1`: about $5 per month for the warm instance.
- BigQuery storage: tiny until you load real data.
- Cloud Run for FastAPI and Grafana: scales to zero when idle.

Cloud Build minutes during `build-images` are pay-per-use and usually a few cents per cycle.

**Run `deployml destroy` as soon as you are done.** Cloud SQL keeps billing while running.

## 7. Get service URLs

```bash
deployml get-urls
```

This prints all service URLs and writes them to a `.env` file in the current directory. Database credentials are masked so the `.env` is safe to share with your IDE or commit to a local notebook.

Add `--show-secrets` to additionally print the Grafana admin password and the Cloud SQL Auth Proxy connection command:

```bash
deployml get-urls --show-secrets
```

## 8. Verify the stack

**MLflow**

```bash
curl https://YOUR_MLFLOW_URL/health   # returns OK
```

Open the MLflow URL in your browser to see the UI.

**FastAPI**

```bash
curl https://YOUR_FASTAPI_URL/health
```

The `/docs` endpoint shows the auto-generated OpenAPI UI.

**Grafana**

Open the Grafana URL in your browser. Username is `admin`. The password is auto-generated and stored in Secret Manager. Fetch it with:

```bash
deployml get-urls --show-secrets
```

The output prints the password directly and also gives the secret ID so you can rotate or re-fetch later.

**BigQuery**

```bash
bq ls --project_id=YOUR_GCP_PROJECT_ID mlops
```

You should see `offline_features`, `predictions`, `ground_truth`, and `drift_metrics`.

## 9. Run the end to end example

With the stack running, follow the [example walkthrough](example.md) to train a model, register it, serve predictions through FastAPI, and visualize drift metrics in Grafana.

## 10. Teardown

When you are done, destroy all infrastructure to stop billing:

```bash
deployml destroy --yes
```

`--yes` skips both the destroy confirm and the workspace cleanup prompt. This deletes all Cloud Run services, Cloud SQL instance, GCS bucket contents, and Terraform state files. It does not delete the Artifact Registry images or the GCP project itself.

To free up an active project slot, also run:

```bash
gcloud projects delete YOUR_GCP_PROJECT_ID
```

## Troubleshooting

**`build-images` fails with denied: User cannot access repository**

You skipped `gcloud auth configure-docker us-west1-docker.pkg.dev`. Run it and retry.

**`init` says Project not found or not accessible**

Either the project ID is wrong, or your gcloud account does not have access. Verify with `gcloud projects describe YOUR_GCP_PROJECT_ID`.

**Deploy hangs at MLflow Cloud Run creation**

Check the Cloud Run logs in the link the error prints. The most common cause is a misconfigured DB connection. If you are on a fork, confirm the template passes `connection_string_cloud_sql` to MLflow rather than `connection_string`.

**Terraform lock file error after an interrupted deploy**

```bash
rm .deployml/YOUR_CONFIG_NAME/terraform/.terraform.lock.hcl
deployml deploy --verbose
```

**Service logs**

```bash
gcloud run services logs read SERVICE_NAME --project YOUR_GCP_PROJECT_ID --region us-west1
```

**`Your active project does not match the quota project` warning**

Not cosmetic. If the ADC quota project points at a deleted or unrelated project, BigQuery and other Google client libraries fail with `403 USER_PROJECT_DENIED`. Always run this once per fresh project before using the example scripts:

```bash
gcloud auth application-default set-quota-project YOUR_GCP_PROJECT_ID
```

**`USER_PROJECT_DENIED` or `Project ... has been deleted` in example scripts**

Same root cause as above. Run the ADC quota project command.

**`The project cannot be created because you have exceeded your allotted project quota`**

GCP limits how many projects you can create. Each deleted project still counts against the quota during a 30-day grace period. If you are iterating on fresh test projects, you will hit this. Workarounds:

- Wait for the grace period to expire.
- Request a higher project creation quota in the [GCP Console](https://console.cloud.google.com/iam-admin/quotas).
- Reuse one project for multiple test runs, calling `deployml destroy` between them. The drift detection in `deployml deploy` makes this safe.

## GKE flow notes

The `deployml gke-*` commands are an alternative to Cloud Run for users who want a Kubernetes cluster. The flow is intentionally lighter than Cloud Run and has a few sharp edges:

**1. GKE uses gcr.io. Cloud Run uses Artifact Registry.**

`deployml build-images --create-repo` pushes to `{region}-docker.pkg.dev/{project}/mlops-images/` (Artifact Registry). The GKE flow expects images at `gcr.io/{project}/...`. These are different registries. If you ran `build-images` for the Cloud Run flow and then try `gke-init`, the GKE manifests reference an image that does not exist. For GKE, build and push manually:

```bash
docker build --platform linux/amd64 -t gcr.io/YOUR_GCP_PROJECT_ID/fastapi/fastapi:v0.0.42 ./docker/fastapi
docker push gcr.io/YOUR_GCP_PROJECT_ID/fastapi/fastapi:v0.0.42
```

**2. kubectl needs `gke-gcloud-auth-plugin`.**

`gcloud components install gke-gcloud-auth-plugin` installs the plugin but it may not be on PATH. Without it on PATH, `kubectl get nodes` fails with `executable gke-gcloud-auth-plugin not found`.

macOS with Homebrew gcloud (bash or zsh):

```bash
export PATH="/opt/homebrew/share/google-cloud-sdk/bin:$PATH"
```

Linux with gcloud installed system-wide is usually already on PATH.

Windows PowerShell:

```powershell
$env:PATH = "C:\Users\$env:USERNAME\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin;" + $env:PATH
```

Windows cmd:

```cmd
set PATH=C:\Users\%USERNAME%\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin;%PATH%
```

Adjust the path if your gcloud install is elsewhere.

**3. Cluster lifecycle and persistence.**

Create a cluster with `deployml gke-cluster-create --cluster NAME --project YOUR_GCP_PROJECT_ID --region us-west1`, which uses Autopilot by default, or `--standard` for a small zonal cluster. You can also use `gcloud container clusters create-auto` directly. MLflow on GKE provisions a PersistentVolumeClaim by default, so experiment data survives pod restarts. MLflow and FastAPI must share a namespace for in-cluster service DNS to resolve, so pass the same `--namespace` to both deploys if you do not use the default namespace. To tear down:

```bash
deployml gke-destroy --manifest-dir manifests --cluster gke-test --project YOUR_GCP_PROJECT_ID --region us-west1 --delete-cluster
```

`gke-destroy` deletes the manifests, the MLflow PVC so its PersistentDisk is reclaimed, and the referenced gcr.io image so nothing keeps billing. `--delete-cluster` also removes the cluster. `--keep-images` retains the image for a quick redeploy. Pass `--namespace` if you deployed into a non-default namespace.
