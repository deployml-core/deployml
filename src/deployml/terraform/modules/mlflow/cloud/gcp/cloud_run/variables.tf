# modules/mlflow/cloud/gcp/cloud_run/variables.tf

variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type        = string
  description = "GCP region for deployment"
}

# Control what gets created
variable "create_service" {
  type        = bool
  description = "Whether to create the Cloud Run service"
  default     = true
}

variable "create_bucket" {
  type        = bool
  description = "Whether to create the storage bucket"
  default     = false
}

variable "allow_public_access" {
  type        = bool
  description = "Whether to allow public access to the MLflow service"
  default     = true
}

# Service configuration
variable "service_name" {
  type        = string
  description = "Name of the Cloud Run service"
  default     = "mlflow-server"
}

variable "image" {
  type        = string
  description = "Docker image URI for MLflow server"
  default     = ""
}

# Storage configuration
variable "artifact_bucket" {
  type        = string
  description = "GCS bucket name for storing MLflow artifacts"
  default     = ""
}

# MLflow configuration
variable "backend_store_uri" {
  type        = string
  description = "URI for MLflow backend store (database). Used only when backend_store_uri_secret_id is empty."
  default     = ""
}

variable "backend_store_uri_secret_id" {
  type        = string
  description = "Secret Manager secret ID holding the MLflow DSN. When set, the env var is sourced via value_from, keeping the password out of plain env."
  default     = ""
}

# Resource configuration
variable "cpu_limit" {
  type        = string
  description = "CPU limit for the container"
  default     = "2000m"
}

variable "memory_limit" {
  type        = string
  description = "Memory limit for the container"
  default     = "2Gi"
}

variable "cpu_request" {
  type        = string
  description = "CPU request for the container"
  default     = "1000m"
}

variable "memory_request" {
  type        = string
  description = "Memory request for the container"
  default     = "1Gi"
}

variable "max_scale" {
  type        = number
  description = "Maximum number of container instances"
  default     = 10
}

# Keep at least one warm MLflow instance to avoid cold starts on the tracking
# server, which makes the UI feel broken. Costs ~$5/mo per warm instance.
# Override to 0 if you accept cold starts in exchange for zero idle cost.
variable "min_instances" {
  type        = number
  description = "Minimum warm container instances. 1 avoids cold starts. 0 saves cost when idle."
  default     = 1
}

variable "startup_probe_path" {
  type        = string
  description = "HTTP path used for the Cloud Run startup probe."
  default     = "/health"
}

variable "request_timeout_seconds" {
  type        = number
  description = "Cloud Run request timeout. Long enough for MLflow log_artifact uploads and large queries."
  default     = 1800
}

variable "container_concurrency" {
  type        = number
  description = "Maximum number of concurrent requests per container"
  default     = 80
}

variable "bucket_exists" {
  type        = bool
  description = "Whether the artifact bucket already exists. If true, do not attempt to create it."
  default     = false
}

variable "cloudsql_instance_annotation" {
  type        = string
  default     = ""
  description = "Cloud SQL instance connection name for annotation."
}

variable "use_postgres" {
  type        = bool
  default     = false
  description = "Whether to use PostgreSQL (Cloud SQL) as the backend. If false, use SQLite."
}

variable "gcp_service_list" {
  description = "The list of APIs necessary for MLflow with Cloud Run"
  type        = list(string)
  default = [
    "run.googleapis.com",                      # Cloud Run
    "iam.googleapis.com",                      # IAM
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "compute.googleapis.com",
    "storage-api.googleapis.com",              # Google Cloud Storage
    "storage-component.googleapis.com",        # Storage component API
    "sqladmin.googleapis.com",                 # Cloud SQL Admin API (if using Cloud SQL)
    "sql-component.googleapis.com",            # Cloud SQL component API (if using Cloud SQL)
    "servicenetworking.googleapis.com",        # For private service connections (if using Cloud SQL)
    "cloudkms.googleapis.com",                 # For encryption keys (if using CMEK)
    "monitoring.googleapis.com",               # For monitoring
    "logging.googleapis.com",                  # For logging
  ]
}