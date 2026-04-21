# CLI Commands Reference

## `deployml doctor`

Check that all required local tools are installed and authenticated.

```bash
deployml doctor
```

Run this before anything else. Checks for `gcloud`, `docker`, `terraform`, and `bq`.

---

## `deployml init`

Enable required GCP APIs for a project. Run once per project.

```bash
deployml init --provider gcp --project-id YOUR_PROJECT_ID
```

**Options:**
- `--provider`, `-p`: Cloud provider — currently `gcp`
- `--project-id`, `-j`: GCP project ID

---

## `deployml build-images`

Build Docker images from your `docker/` folder and push them to GCP Artifact Registry.

```bash
deployml build-images --docker-root docker --gcp-project YOUR_PROJECT_ID --region us-west1
```

**Options:**
- `--docker-root`, `-d`: Path to folder containing Dockerfiles (required)
- `--gcp-project`, `-p`: GCP project ID
- `--region`: GCP region (default: `us-central1`)
- `--repository`: Artifact Registry repository name (default: `mlops-images`)
- `--tag`: Image tag (default: `latest`)

---

## `deployml deploy`

Deploy infrastructure from a YAML config file.

```bash
deployml deploy --config-path config.yaml --verbose
```

**Options:**
- `--config-path`, `-c`: Path to config YAML file (required)
- `--verbose`, `-v`: Stream Terraform logs instead of showing a progress bar
- `--yes`, `-y`: Skip confirmation prompts

---

## `deployml get-urls`

Print service URLs from the last deployment and write them to a `.env` file.

```bash
deployml get-urls --config-path config.yaml
```

**Options:**
- `--config-path`, `-c`: Path to config YAML file (required)
- `--env-path`: Where to write the `.env` file (default: `.env`)

---

## `deployml destroy`

Tear down all infrastructure for a given config.

```bash
deployml destroy --config-path config.yaml
```

**Options:**
- `--config-path`, `-c`: Path to config YAML file (required)
- `--clean-workspace`: Delete the local workspace folder after destroy
- `--yes`, `-y`: Skip confirmation prompts
