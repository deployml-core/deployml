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

output "terraform_files_bucket" {
  value       = google_storage_bucket.terraform_files.name
  description = "GCS bucket storing Terraform files and resource manifest for teardown"
}

output "cloud_run_job_name" {
  value       = google_cloud_run_v2_job.teardown.name
  description = "Name of the Cloud Run Job for teardown"
}

