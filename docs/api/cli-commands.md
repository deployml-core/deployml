# CLI Commands Reference

Complete reference for all deployml CLI commands.

## Core Commands

### `deployml deploy`

Deploy infrastructure based on a YAML configuration file.

**Usage:**

```bash
# Basic usage
deployml deploy --config-path config.yaml

# Skip confirmation prompts
deployml deploy --config-path config.yaml --yes

# Generate manifests only (GKE)
deployml deploy --config-path config.yaml --generate-only
```

**Options:**
- `--config-path`, `-c`: Path to YAML config file (required)
- `--yes`, `-y`: Skip confirmation prompts
- `--generate-only`, `-g`: Only generate manifests, do not apply (GKE)

**Example:**

```bash
# Deploy Cloud Run stack
deployml deploy -c cloud-run-config.yaml

# Deploy GKE stack with manifest generation only
deployml deploy -c gke-config.yaml --generate-only
```

### `deployml destroy`

Destroy infrastructure and optionally clean up workspace.

**Usage:**

```bash
# Destroy infrastructure
deployml destroy --config-path config.yaml

# Clean workspace after destroy
deployml destroy --config-path config.yaml --clean-workspace

# Skip confirmation
deployml destroy --config-path config.yaml --yes
```

**Options:**
- `--config-path`, `-c`: Path to YAML config file (required)
- `--workspace`: Override workspace name from config
- `--clean-workspace`: Remove entire workspace after destroy
- `--yes`, `-y`: Skip confirmation prompts

**Example:**

```bash
# Destroy and clean workspace
deployml destroy -c config.yaml --clean-workspace --yes
```

### `deployml init`

Initialize cloud project by enabling required APIs.

**Usage:**

```bash
# Initialize GCP project
deployml init --provider gcp --project-id YOUR_PROJECT_ID

# Initialize AWS project
deployml init --provider aws
```

**Options:**
- `--provider`, `-p`: Cloud provider (gcp, aws, azure)
- `--project-id`, `-j`: Project ID (for GCP)

**Example:**

```bash
deployml init -p gcp -j my-project-id
```

### `deployml generate`

Generate a deployment configuration YAML file interactively.

**Usage:**

```bash
deployml generate
```

**Example:**

```bash
# Interactive config generation
deployml generate
# Follow prompts to create config.yaml
```

### `deployml doctor`

Run system checks for required tools and authentication.

**Usage:**

```bash
# Basic check
deployml doctor

# Check GCP APIs
deployml doctor --project-id YOUR_PROJECT_ID
```

**Options:**
- `--project-id`, `-j`: Project ID (for GCP API checks)

**Example:**

```bash
deployml doctor --project-id my-project-id
```

## GKE Commands

### `deployml gke-init`

Generate Kubernetes manifests for GKE.

**Usage:**

```bash
# Generate MLflow manifests
deployml gke-init \
  --output-dir ./manifests/mlflow \
  --image mlflow-demo:latest \
  --project YOUR_PROJECT_ID \
  --service mlflow

# Generate FastAPI manifests
deployml gke-init \
  --output-dir ./manifests/fastapi \
  --image fastapi-demo:latest \
  --project YOUR_PROJECT_ID \
  --service fastapi \
  --mlflow-uri http://mlflow-service:5000
```

**Options:**
- `--output-dir`, `-o`: Directory to create Kubernetes manifests (required)
- `--image`, `-i`: Docker image name (local or GCR) (required)
- `--project`, `-p`: GCP project ID (required)
- `--service`, `-s`: Service type: mlflow or fastapi (default: mlflow)
- `--mlflow-uri`, `-m`: MLflow URI (for FastAPI)

**Example:**

```bash
deployml gke-init \
  -o ./manifests/mlflow \
  -i mlflow-demo:latest \
  -p my-project-id \
  -s mlflow
```

### `deployml gke-deploy`

Deploy Kubernetes manifests to GKE cluster.

**Usage:**

```bash
deployml gke-deploy \
  --manifest-dir ./manifests/mlflow \
  --cluster my-gke-cluster \
  --project YOUR_PROJECT_ID \
  --zone us-west1-a
```

**Options:**
- `--manifest-dir`, `-d`: Directory containing deployment.yaml and service.yaml (required)
- `--cluster`, `-c`: GKE cluster name (required)
- `--project`, `-p`: GCP project ID (required)
- `--zone`, `-z`: GKE cluster zone
- `--region`, `-r`: GKE cluster region

**Example:**

```bash
deployml gke-deploy \
  -d ./manifests/mlflow \
  -c my-cluster \
  -p my-project-id \
  -z us-west1-a
```

### `deployml gke-apply`

Apply previously generated manifests to GKE cluster.

**Usage:**

```bash
deployml gke-apply --config-path gke-config.yaml
```

**Options:**
- `--config-path`, `-c`: Path to YAML config file (required)
- `--yes`, `-y`: Skip confirmation prompts

**Example:**

```bash
# Apply manifests after editing
deployml gke-apply -c gke-config.yaml
```

## Minikube Commands

### `deployml minikube-init`

Initialize minikube and generate FastAPI Kubernetes manifests.

**Usage:**

```bash
deployml minikube-init \
  --output-dir ./manifests/fastapi \
  --image fastapi-demo:latest \
  --mlflow-uri http://mlflow-service:5000
```

**Options:**
- `--output-dir`, `-o`: Directory to create Kubernetes manifests (required)
- `--image`, `-i`: FastAPI Docker image (required)
- `--mlflow-uri`, `-m`: MLflow tracking URI (optional)
- `--start-cluster`: Start minikube cluster if not running (default: true)

**Example:**

```bash
deployml minikube-init \
  -o ./manifests/fastapi \
  -i fastapi-demo:latest \
  -m http://mlflow-service:5000
```

### `deployml minikube-deploy`

Deploy FastAPI to minikube using kubectl apply.

**Usage:**

```bash
deployml minikube-deploy --manifest-dir ./manifests/fastapi
```

**Options:**
- `--manifest-dir`, `-d`: Directory containing deployment.yaml and service.yaml (required)
- `--image-name`, `-i`: Docker image name to load into minikube (auto-detected if not provided)

**Example:**

```bash
deployml minikube-deploy -d ./manifests/fastapi
```

### `deployml mlflow-init`

Initialize minikube and generate MLflow Kubernetes manifests.

**Usage:**

```bash
deployml mlflow-init \
  --output-dir ./manifests/mlflow \
  --image mlflow-demo:latest \
  --backend-store-uri sqlite:///mlflow.db
```

**Options:**
- `--output-dir`, `-o`: Directory to create Kubernetes manifests (required)
- `--image`, `-i`: MLflow Docker image (required)
- `--backend-store-uri`, `-b`: Backend store URI (defaults to SQLite)
- `--artifact-root`, `-a`: Artifact root path (defaults to /mlflow-artifacts)
- `--start-cluster`: Start minikube cluster if not running (default: true)

**Example:**

```bash
deployml mlflow-init \
  -o ./manifests/mlflow \
  -i mlflow-demo:latest \
  -b sqlite:///mlflow.db
```

### `deployml mlflow-deploy`

Deploy MLflow to minikube using kubectl apply.

**Usage:**

```bash
deployml mlflow-deploy --manifest-dir ./manifests/mlflow
```

**Options:**
- `--manifest-dir`, `-d`: Directory containing deployment.yaml and service.yaml (required)
- `--image-name`, `-i`: Docker image name to load into minikube (auto-detected if not provided)

**Example:**

```bash
deployml mlflow-deploy -d ./manifests/mlflow
```

## Teardown Commands

### `deployml teardown`

Manage auto-teardown: cancel, status, update, or schedule.

**Usage:**

```bash
# Cancel scheduled teardown
deployml teardown cancel --config-path config.yaml

# Check teardown status
deployml teardown status --config-path config.yaml

# Update teardown schedule
deployml teardown update --config-path config.yaml

# Schedule new teardown
deployml teardown schedule --config-path config.yaml
```

**Options:**
- `--config-path`, `-c`: Path to YAML config file (required)

**Example:**

```bash
# Check teardown status
deployml teardown status -c config.yaml

# Cancel teardown
deployml teardown cancel -c config.yaml
```

## Complete Examples

### Complete GKE Deployment

```bash
# 1. Generate manifests
deployml deploy --config-path gke-config.yaml --generate-only

# 2. Review manifests
ls -la .deployml/gke-mlflow-fastapi/manifests/

# 3. Apply manifests
deployml gke-apply --config-path gke-config.yaml
```

### Cloud Run with Auto-Teardown

```bash
# Deploy with 24-hour auto-teardown
deployml deploy --config-path cloud-run-config.yaml

# Check teardown status
deployml teardown status --config-path cloud-run-config.yaml

# Cancel teardown
deployml teardown cancel --config-path cloud-run-config.yaml
```

### Minikube Local Development

```bash
# 1. Start minikube
minikube start

# 2. Generate MLflow manifests
deployml mlflow-init -o ./manifests/mlflow -i mlflow-demo:latest

# 3. Deploy MLflow
deployml mlflow-deploy -d ./manifests/mlflow

# 4. Generate FastAPI manifests
deployml minikube-init -o ./manifests/fastapi -i fastapi-demo:latest -m http://mlflow-service:5000

# 5. Deploy FastAPI
deployml minikube-deploy -d ./manifests/fastapi
```

## Next Steps

- Read [Installation Guide](../installation.md)
- Explore [Tutorials](../tutorials/overview.md)