variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type        = string
  description = "GCP region for deployment"
}

variable "db_instance_name" {
  type        = string
  description = "Name of the Cloud SQL instance"
  default     = "mlflow-postgres"
}

variable "db_name" {
  type        = string
  description = "Name of the database"
  default     = "mlflow"
}

variable "db_user" {
  type        = string
  description = "Database username"
  default     = "postgres"
}

variable "db_tier" {
  type        = string
  description = "Database tier for Cloud SQL instance"
  default     = "db-g1-small"
}

variable "max_connections" {
  type        = string
  description = "Maximum number of connections to the database"
  default     = "100"
}

variable "create_feast_db" {
  description = "Whether to create the Feast database"
  type        = bool
  default     = false
}

variable "create_metrics_db" {
  description = "Whether to create the Metrics database (for Grafana)"
  type        = bool
  default     = false
}

variable "gcp_service_list" {
  description = "The list of APIs necessary for MLflow with Cloud SQL"
  type        = list(string)
  default = [
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "compute.googleapis.com",                    # For VM instances
    "storage-api.googleapis.com",               # For Google Cloud Storage
    "storage-component.googleapis.com",         # Storage component API
    "sqladmin.googleapis.com",                  # Cloud SQL Admin API (essential)
    "sql-component.googleapis.com",             # Cloud SQL component API
    "servicenetworking.googleapis.com",         # For private service connections
    "cloudkms.googleapis.com",                  # For encryption keys (if using CMEK)
    "monitoring.googleapis.com",                # For Cloud SQL monitoring
    "logging.googleapis.com",                   # For Cloud SQL logging
  ]
} 