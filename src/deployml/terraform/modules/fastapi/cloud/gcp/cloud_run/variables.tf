variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type        = string
  description = "GCP region for deployment"
}

variable "service_name" {
  type        = string
  description = "Name of the Cloud Run service"
}

variable "image" {
  type        = string
  description = "Docker image URI for FastAPI service"
}

variable "mlflow_tracking_uri" {
  type        = string
  description = "MLflow Tracking Server URI"
}

variable "model_uri" {
  type        = string
  description = "MLflow Model URI (can be registry or artifact path)"
  default     = "models:/MyModel/Production"
}

variable "cpu_limit" {
  type        = string
  description = "CPU limit for the container"
  default     = "1000m"
}

variable "memory_limit" {
  type        = string
  description = "Memory limit for the container"
  default     = "1Gi"
}

variable "allow_public_access" {
  type        = bool
  description = "Whether to allow public access to the FastAPI service"
  default     = true
}

variable "mlflow_artifact_bucket" {
  type        = string
  description = "MLflow artifact bucket name"
  default     = ""
}

variable "backend_store_uri" {
  type        = string
  description = "Backend store URI for MLflow (sqlite or postgresql)"
  default     = "sqlite:///mlflow.db"
}

variable "db_connection_string" {
  type        = string
  description = "Database connection string for the application"
  default     = ""
}

variable "use_postgres" {
  type        = bool
  description = "Whether to use PostgreSQL backend"
  default     = false
}

variable "cloudsql_instance_annotation" {
  type        = string
  description = "Cloud SQL instance connection name for annotation"
  default     = ""
}

variable "feast_service_url" {
  type        = string
  description = "Feast service URL for feature serving"
  default     = ""
}

variable "enable_feast_connection" {
  type        = bool
  description = "Whether to enable Feast connection"
  default     = false
}

variable "mlflow_bucket_exists" {
  type        = bool
  description = "Whether the MLflow artifact bucket already exists"
  default     = false
}

variable "bigquery_dataset" {
  type        = string
  description = "BigQuery dataset name for storing predictions"
  default     = "mlops"
}