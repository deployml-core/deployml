output "job_name" {
  description = "Name of the fairness monitoring Cloud Run job"
  value       = google_cloud_run_v2_job.fairness_checker.name
}

output "job_url" {
  description = "Console URL for the fairness monitoring job"
  value       = "https://console.cloud.google.com/run/jobs/details/${var.region}/${google_cloud_run_v2_job.fairness_checker.name}"
}

output "scheduler_name" {
  description = "Name of the Cloud Scheduler job"
  value       = google_cloud_scheduler_job.fairness_schedule.name
}

output "schedule" {
  description = "Cron schedule for fairness monitoring"
  value       = var.schedule
}

output "sensitive_attributes" {
  description = "List of sensitive attributes being monitored"
  value       = var.sensitive_attributes
}

output "fairness_metrics" {
  description = "List of fairness metrics being calculated"
  value       = var.fairness_metrics
}

output "job_id" {
  description = "Full resource ID of the Cloud Run job"
  value       = google_cloud_run_v2_job.fairness_checker.id
}

