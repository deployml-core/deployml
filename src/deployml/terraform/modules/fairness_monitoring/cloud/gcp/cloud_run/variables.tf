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
  description = "Docker image for fairness monitoring"
  type        = string
}

variable "database_url" {
  description = "PostgreSQL connection string"
  type        = string
  sensitive   = true
}

variable "schedule" {
  description = "Cron schedule for monitoring job (e.g., '0 8 * * *' for daily at 8 AM)"
  type        = string
  default     = "0 8 * * *"
}

variable "time_zone" {
  description = "Time zone for cron schedule"
  type        = string
  default     = "UTC"
}

variable "sensitive_attributes" {
  description = "List of sensitive attributes to monitor for fairness (e.g., ['location', 'age_group'])"
  type        = list(string)
  default     = []
}

variable "fairness_metrics" {
  description = "List of fairness metrics to calculate (demographic_parity, equal_opportunity, disparate_impact)"
  type        = list(string)
  default     = ["demographic_parity", "disparate_impact"]
}

variable "demographic_parity_threshold" {
  description = "Maximum allowed difference in positive rates between groups"
  type        = number
  default     = 0.1
}

variable "disparate_impact_threshold" {
  description = "Minimum required disparate impact ratio (80% rule = 0.8)"
  type        = number
  default     = 0.8
}

variable "alert_on_violation" {
  description = "Whether to send alerts when fairness violations are detected"
  type        = bool
  default     = true
}

variable "alert_webhook_url" {
  description = "Webhook URL for sending alerts (e.g., Slack, PagerDuty)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "protected_groups" {
  description = "Map of attribute to protected group values (e.g., {location: ['rural'], age_group: ['young']})"
  type        = map(list(string))
  default     = null
}

variable "service_account_email" {
  description = "Service account email for Cloud Run job"
  type        = string
}

