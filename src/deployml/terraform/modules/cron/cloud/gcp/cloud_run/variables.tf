# modules/cron/cloud/gcp/cloud_run/variables.tf

variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region for resources"
  type        = string
  default     = "us-west1"
}

variable "jobs" {
  description = "List of scheduled jobs to create"
  type = list(object({
    service_name     = string
    image           = string
    cron_schedule   = string
    bigquery_dataset = optional(string, "")
  }))
  default = []
}

variable "time_zone" {
  description = "Time zone for cron schedules"
  type        = string
  default     = "UTC"
}

variable "cpu_limit" {
  description = "CPU limit for containers"
  type        = string
  default     = "1000m"
}

variable "memory_limit" {
  description = "Memory limit for containers"
  type        = string
  default     = "2Gi"
}

variable "gcp_service_list" {
  description = "List of GCP APIs to enable"
  type        = list(string)
  default = [
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "bigquery.googleapis.com",
    "monitoring.googleapis.com"
  ]
}

# MLflow configuration
variable "mlflow_tracking_uri" {
  description = "MLflow tracking server URI"
  type        = string
  default     = ""
}

# Database configuration
variable "database_url" {
  description = "Database connection URL for storing results"
  type        = string
  default     = ""
}

# Feast configuration
variable "feast_online_store_host" {
  description = "Feast online store PostgreSQL host"
  type        = string
  default     = ""
}

variable "feast_online_store_port" {
  description = "Feast online store PostgreSQL port"
  type        = string
  default     = "5432"
}

variable "feast_online_store_database" {
  description = "Feast online store PostgreSQL database name"
  type        = string
  default     = ""
}

variable "feast_online_store_user" {
  description = "Feast online store PostgreSQL username"
  type        = string
  default     = ""
}

variable "feast_online_store_password" {
  description = "Feast online store PostgreSQL password"
  type        = string
  default     = ""
  sensitive   = true
}

variable "feast_registry_path" {
  description = "Feast registry path (PostgreSQL connection string)"
  type        = string
  default     = ""
  sensitive   = true
}

# Grafana configuration for monitoring
variable "grafana_url" {
  description = "Grafana server URL for drift monitoring"
  type        = string
  default     = ""
}

variable "grafana_api_key" {
  description = "Grafana API key for drift monitoring"
  type        = string
  default     = ""
  sensitive   = true
}

# Cloud SQL configuration
variable "cloud_sql_connection_name" {
  description = "Cloud SQL instance connection name (format: project:region:instance)"
  type        = string
  default     = ""
}