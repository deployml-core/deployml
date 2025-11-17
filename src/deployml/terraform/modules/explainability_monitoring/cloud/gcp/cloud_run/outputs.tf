output "job_name" {
  description = "Name of the explainability monitoring Cloud Run job"
  value       = google_cloud_run_v2_job.explainability_monitor.name
}

output "job_url" {
  description = "Console URL for the explainability monitoring job"
  value       = "https://console.cloud.google.com/run/jobs/details/${var.region}/${google_cloud_run_v2_job.explainability_monitor.name}"
}

output "scheduler_name" {
  description = "Name of the Cloud Scheduler job"
  value       = google_cloud_scheduler_job.explainability_schedule.name
}

output "schedule" {
  description = "Cron schedule for explainability monitoring"
  value       = var.schedule
}

output "job_id" {
  description = "Full resource ID of the Cloud Run job"
  value       = google_cloud_run_v2_job.explainability_monitor.id
}

