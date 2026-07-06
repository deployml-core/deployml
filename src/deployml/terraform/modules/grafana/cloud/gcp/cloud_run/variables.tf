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
  description = "Docker image URI for Grafana service"
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

variable "metrics_connection_string" {
  type        = string
  description = "Connection string for the metrics database. Used only when metrics_connection_string_secret_id is empty."
  default     = ""
}

variable "metrics_connection_string_secret_id" {
  type        = string
  description = "Secret Manager secret ID holding the Grafana metrics DSN. When set, GF_DATABASE_URL is sourced via value_from."
  default     = ""
}

variable "use_metrics_database" {
  type        = bool
  description = "Whether to use metrics database for Grafana"
  default     = false
}

variable "cloudsql_instance_annotation" {
  type        = string
  description = "Cloud SQL instance connection annotation"
  default     = ""
}