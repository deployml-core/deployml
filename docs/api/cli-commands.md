# CLI Commands Reference

## `deployml doctor`

Check that all required local tools are installed and authenticated.

```bash
deployml doctor
```

Run this before anything else. Checks for `gcloud`, `docker`, `terraform`, and `bq`.

---

## `deployml init`

Enable required GCP APIs for a project and create the Artifact Registry repository. Run once per project.

```bash
deployml init --provider gcp --project-id YOUR_PROJECT_ID
```

**Options:**
- `--provider`, `-p`: Cloud provider — currently `gcp`
- `--project-id`, `-j`: GCP project ID

---

## `deployml build-images`

Build Docker images and push them to GCP Artifact Registry. Reads project ID and region from `config.yaml` by default.

```bash
deployml build-images
```

**Options:**
- `--config-path`, `-c`: Path to config YAML file (default: `config.yaml`)
- `--docker-root`, `-d`: Path to folder containing Dockerfiles (default: built-in package images)
- `--gcp-project`, `-p`: GCP project ID (default: inferred from config)
- `--region`: GCP region (default: inferred from config)
- `--repository`: Artifact Registry repository name (default: `mlops-images`)
- `--tag`: Image tag (default: `latest`)
- `--create-repo`: Create the Artifact Registry repository if it does not exist

---

## `deployml deploy`

Deploy infrastructure from a YAML config file.

```bash
deployml deploy --verbose
```

**Options:**
- `--config-path`, `-c`: Path to config YAML file (default: `config.yaml`)
- `--verbose`, `-v`: Stream Terraform logs instead of showing a progress bar
- `--yes`, `-y`: Skip confirmation prompts

---

## `deployml get-urls`

Print service URLs from the last deployment and write them to a `.env` file.

```bash
deployml get-urls
```

**Options:**
- `--config-path`, `-c`: Path to config YAML file (default: `config.yaml`)
- `--env-path`: Where to write the `.env` file (default: `.env`)

---

## `deployml destroy`

Tear down all infrastructure for a given config.

```bash
deployml destroy
```

**Options:**
- `--config-path`, `-c`: Path to config YAML file (default: `config.yaml`)
- `--clean-workspace`: Delete the local workspace folder after destroy
- `--yes`, `-y`: Skip confirmation prompts
