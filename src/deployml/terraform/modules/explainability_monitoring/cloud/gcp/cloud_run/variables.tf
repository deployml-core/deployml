variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run job"
  type        = string
}

variable "stack_name" {
  description = "Name of the ML stack"
  type        = string
}

variable "image" {
  description = "Docker image for explainability monitoring"
  type        = string
}

variable "database_url" {
  description = "PostgreSQL connection string"
  type        = string
  sensitive   = true
}

variable "mlflow_tracking_uri" {
  description = "MLflow tracking server URL"
  type        = string
  default     = ""
}

variable "schedule" {
  description = "Cron schedule for monitoring job (e.g., '0 6 * * *' for daily at 6 AM)"
  type        = string
  default     = "0 6 * * *"
}

variable "time_zone" {
  description = "Time zone for cron schedule"
  type        = string
  default     = "UTC"
}

variable "importance_shift_threshold" {
  description = "Threshold for detecting significant feature importance shifts"
  type        = number
  default     = 0.3
}

variable "track_feature_importance" {
  description = "Whether to track feature importance over time"
  type        = bool
  default     = true
}

variable "alert_on_importance_shift" {
  description = "Whether to alert when feature importance shifts"
  type        = bool
  default     = true
}

variable "alert_webhook_url" {
  description = "Webhook URL for sending alerts (e.g., Slack, PagerDuty)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "service_account_email" {
  description = "Service account email for Cloud Run job"
  type        = string
}

