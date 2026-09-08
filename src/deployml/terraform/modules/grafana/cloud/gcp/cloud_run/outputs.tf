output "service_url" {
  description = "URL of the Grafana service"
  value       = google_cloud_run_service.grafana.status[0].url
}

output "admin_password_secret_id" {
  description = "Secret Manager ID holding the Grafana admin password. Fetch with: gcloud secrets versions access latest --secret=ID --project=PROJECT"
  value       = google_secret_manager_secret.grafana_admin.secret_id
}

output "admin_password" {
  description = "Grafana admin password. Sensitive."
  value       = random_password.grafana_admin.result
  sensitive   = true
}
