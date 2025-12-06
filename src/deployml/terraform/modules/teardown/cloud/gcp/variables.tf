variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "workspace_name" {
  description = "Name of the DeployML workspace to teardown"
  type        = string
}

variable "schedule" {
  description = "Cron schedule for teardown (e.g., '0 2 * * *' for daily at 2 AM)"
  type        = string
}

variable "time_zone" {
  description = "Time zone for the schedule"
  type        = string
  default     = "UTC"
}

variable "terraform_state_bucket" {
  description = "GCS bucket containing Terraform state (optional)"
  type        = string
  default     = ""
}

variable "terraform_files_bucket" {
  description = "GCS bucket containing Terraform files (optional, for teardown)"
  type        = string
  default     = ""
}

