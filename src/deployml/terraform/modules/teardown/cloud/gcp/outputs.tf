output "function_url" {
  value       = google_cloudfunctions_function.teardown.https_trigger_url
  description = "URL of the teardown Cloud Function"
}

output "scheduler_job_name" {
  value       = google_cloud_scheduler_job.teardown.name
  description = "Name of the Cloud Scheduler job"
}

output "scheduler_job_id" {
  value       = google_cloud_scheduler_job.teardown.id
  description = "ID of the Cloud Scheduler job"
}

output "service_account_email" {
  value       = google_service_account.teardown.email
  description = "Email of the service account used for teardown"
}

