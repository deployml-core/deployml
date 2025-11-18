# Teardown module - Creates Cloud Function and Cloud Scheduler for auto-teardown

resource "google_project_service" "required" {
  for_each = toset([
    "cloudfunctions.googleapis.com",
    "cloudscheduler.googleapis.com",
    "storage-api.googleapis.com"
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

data "google_project" "current" {}

# Archive Cloud Function source code
data "archive_file" "function_source" {
  type        = "zip"
  source_dir  = "${path.module}/cloud_function"
  output_path = "${path.module}/function.zip"
}

# Cloud Storage bucket for function source code
resource "google_storage_bucket" "function_source" {
  name     = "${var.project_id}-teardown-functions-${random_id.bucket_suffix.hex}"
  location = var.region
  project  = var.project_id

  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Upload function source code
resource "google_storage_bucket_object" "function_source" {
  name   = "teardown-function-${data.archive_file.function_source.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.function_source.output_path
}

# Cloud Function
resource "google_cloudfunctions_function" "teardown" {
  name        = "deployml-teardown-${var.workspace_name}"
  description = "Auto-teardown function for DeployML workspace: ${var.workspace_name}"
  runtime     = "python311"
  region      = var.region
  project     = var.project_id

  available_memory_mb   = 256
  source_archive_bucket = google_storage_bucket.function_source.name
  source_archive_object = google_storage_bucket_object.function_source.name
  trigger {
    http_trigger {
      security_level = "SECURE_ALWAYS"
    }
  }
  entry_point = "teardown_infrastructure"

  environment_variables = {
    PROJECT_ID = var.project_id
  }

  service_account_email = google_service_account.teardown.email

  depends_on = [google_project_service.required]
}

# Service account for Cloud Function
resource "google_service_account" "teardown" {
  account_id   = "deployml-teardown-${substr(replace(var.workspace_name, "-", ""), 0, 20)}"
  display_name = "DeployML Teardown Service Account"
  project      = var.project_id
}

# Grant permissions to service account
resource "google_project_iam_member" "teardown_permissions" {
  for_each = toset([
    "roles/run.admin",           # To destroy Cloud Run services
    "roles/compute.instanceAdmin.v1",  # To destroy VMs
    "roles/storage.admin",       # To destroy storage buckets
    "roles/cloudsql.admin",      # To destroy Cloud SQL instances
    "roles/iam.serviceAccountUser",  # To use service accounts
    "roles/resourcemanager.projectIamAdmin"  # To clean up IAM bindings
  ])
  
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.teardown.email}"
}

# Cloud Scheduler job
resource "google_cloud_scheduler_job" "teardown" {
  name        = "deployml-teardown-${var.workspace_name}"
  description = "Auto-teardown job for DeployML workspace: ${var.workspace_name}"
  schedule    = var.schedule
  time_zone   = var.time_zone
  region      = var.region
  project     = var.project_id

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions_function.teardown.https_trigger_url
    
    body = base64encode(jsonencode({
      workspace_name         = var.workspace_name
      project_id            = var.project_id
      terraform_state_bucket = var.terraform_state_bucket
      terraform_files_bucket = var.terraform_files_bucket
    }))
    
    headers = {
      "Content-Type" = "application/json"
    }
    
    oidc_token {
      service_account_email = google_service_account.teardown.email
    }
  }

  depends_on = [google_project_service.required]
}

# Outputs
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