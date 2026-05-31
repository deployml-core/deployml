# CLI Commands Reference

Commands you use most live at the top. Advanced and experimental commands are listed at the bottom.

## `deployml doctor`

Check that required tools are installed and authenticated. Optionally checks enabled APIs and IAM roles on a project.

```bash
deployml doctor
deployml doctor --project-id YOUR_GCP_PROJECT_ID
```

**Options:**
- `--project-id`, `-j`: GCP project to probe for enabled APIs and IAM role coverage.

The doctor checks: tool versions for docker, terraform, gcloud, bq; gcloud auth and Application Default Credentials; Infracost (optional); and for a given project, required APIs and IAM roles.

---

## `deployml init`

Enable required GCP APIs for a project and create a local `docker/` folder plus a runnable `config.yaml` starter. Run once per project.

```bash
deployml init --provider gcp --project-id YOUR_GCP_PROJECT_ID
```

**Options:**
- `--provider`, `-p`: Cloud provider. Currently `gcp` is fully supported. `aws` and `azure` write skeleton configs.
- `--project-id`, `-j`: GCP project ID.
- `--path`: Directory where the project is initialized. Defaults to current directory.
- `--overwrite`: Overwrite an existing `docker/` folder or `config.yaml`.

The generated `config.yaml` includes a `provider.image_tag` field set to the deployml version. Override this to pin to a specific build tag.

---

## `deployml build-images`

Build Docker images and push them to GCP Artifact Registry. Reads project ID, region, and image_tag from `config.yaml` by default.

```bash
deployml build-images --create-repo
```

**Options:**
- `--config-path`, `-c`: Path to config YAML file. Default `config.yaml`.
- `--docker-root`, `-d`: Folder containing subfolders with Dockerfiles. Default is the built-in deployml docker directory.
- `--gcp-project`, `-p`: GCP project ID. Default inferred from config.
- `--region`: GCP region. Default inferred from config.
- `--repository`: Artifact Registry repository name. Default `mlops-images`.
- `--tag`, `-t`: Image tag. Default reads `config.provider.image_tag`, falls back to `v{deployml_version}`.
- `--create-repo`: Create the Artifact Registry repository on first run.
- `--dry-run`: Print commands without executing.

Builds run on Cloud Build, so a local Docker daemon is not required for GCP mode.

---

## `deployml deploy`

Deploy infrastructure from a YAML config file. Prompts for confirmation by default.

```bash
deployml deploy --verbose
deployml deploy --verbose --yes
```

**Options:**
- `--config-path`, `-c`: Path to config YAML. Default `config.yaml`.
- `--verbose`, `-v`: Stream Terraform logs to stdout. Without this you get a progress bar.
- `--yes`, `-y`: Skip the `[y/N]` deploy confirmation. Required for non-interactive scripts.
- `--generate-only`, `-g`: Only generate manifests, no apply. For GKE flow.

First-time deploy takes about 20 minutes because Cloud SQL Postgres provisioning is slow.

---

## `deployml get-urls`

Print service URLs from the last deployment and write them to a `.env` file. Database credentials are masked.

```bash
deployml get-urls
deployml get-urls --show-secrets
```

**Options:**
- `--config-path`, `-c`: Path to config YAML. Default `config.yaml`.
- `--env-path`: Where to write the `.env`. Default `.env`.
- `--show-secrets`: Additionally fetch and print the Grafana admin password and the Cloud SQL Auth Proxy connection command.

---

## `deployml destroy`

Tear down all infrastructure for a given config. Also removes the Artifact Registry repo created by build-images.

```bash
deployml destroy --yes
```

**Options:**
- `--config-path`, `-c`: Path to config YAML. Default `config.yaml`.
- `--clean-workspace`: Remove the local `.deployml/` workspace folder after destroy.
- `--yes`, `-y`: Skip both the destroy confirmation and the Terraform state cleanup prompt.
- `--workspace`: Override the workspace name from config.

On partial failure, Terraform state is preserved and the command prints recovery instructions including `gcloud asset search-all-resources` for finding residual resources.

---

## Config file reference

Top-level fields used by deploy and destroy:

```yaml
name: string                       # workspace name. defaults to "default" if omitted
provider:
  name: gcp | aws | azure
  project_id: string               # required for gcp
  region: string                   # required for gcp
  image_tag: string                # optional. default v{deployml_version}
deployment:
  type: cloud_run | cloud_vm | gke # required
stack:
  - <stage_name>:
      name: mlflow | fastapi | grafana | feast | cron
      params: {}                   # tool-specific
```

Supported stage names: `experiment_tracking`, `artifact_tracking`, `model_registry`, `model_serving`, `model_monitoring`, `feature_store`, `workflow_orchestration`.

---

## Advanced and experimental commands

These exist in the CLI but are not part of the documented happy path. Use at your own risk and inspect the source.

- `deployml generate`: Interactive YAML generator. Less useful since `init` now writes a runnable config.
- `deployml status`: Stub. Reports deployment status of current workspace.
- `deployml terraform`: Run raw terraform actions (plan, apply, destroy) on a rendered workspace.
- `deployml teardown`: Manage scheduled auto-teardown jobs.
- `deployml vm`: Placeholder for VM deployment.
- `deployml mlflow-init`, `deployml mlflow-deploy`: MLflow-only flows.
- `deployml minikube-init`, `deployml minikube-deploy`: Local Kubernetes flow for testing without GCP.
- `deployml gke-init`, `deployml gke-deploy`, `deployml gke-apply`, `deployml gke-destroy`: GKE deployment path. `gke-destroy` removes the deployed manifests and, with `--delete-cluster`, the cluster itself. See the [GKE flow notes](../tutorials/gcp-cloud-run.md#gke-flow-notes) in the tutorial.

The fully supported and tested path is GCP Cloud Run via `init`, `build-images`, `deploy`, `get-urls`, `destroy`.
