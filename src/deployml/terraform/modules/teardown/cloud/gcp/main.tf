# Teardown module - Creates Cloud Run Job and Cloud Scheduler for auto-teardown

resource "google_project_service" "required" {
  for_each = toset([
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "storage-api.googleapis.com",
    "secretmanager.googleapis.com"
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

data "google_project" "current" {}

# GCS bucket for storing Terraform files and resource manifest
resource "google_storage_bucket" "terraform_files" {
  name     = "${var.project_id}-deployml-terraform-${random_id.bucket_suffix.hex}"
  location = var.region
  project  = var.project_id

  uniform_bucket_level_access = true
  force_destroy               = true
  
  versioning {
    enabled = true
  }
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Service account for Cloud Run Job
resource "google_service_account" "teardown" {
  # account_id must be 6-30 chars. "deployml-teardown-" is 18 chars, leaving 12 for workspace name
  account_id   = "deployml-teardown-${substr(replace(var.workspace_name, "-", ""), 0, 12)}"
  display_name = "DeployML Teardown Service Account"
  project      = var.project_id
}

# Grant permissions to service account
resource "google_project_iam_member" "teardown_permissions" {
  for_each = toset([
    "roles/run.admin",                    # To destroy Cloud Run services and jobs
    "roles/compute.instanceAdmin.v1",     # To destroy VMs
    "roles/storage.admin",                # To destroy storage buckets
    "roles/cloudsql.admin",               # To destroy Cloud SQL instances
    "roles/iam.serviceAccountUser",       # To use service accounts
    "roles/resourcemanager.projectIamAdmin", # To clean up IAM bindings
    "roles/storage.objectAdmin",          # To read/write files in GCS
    "roles/secretmanager.secretAccessor",  # To access secrets
    "roles/pubsub.admin",                 # To delete Pub/Sub topics
    "roles/cloudscheduler.admin",         # To delete scheduler jobs
    "roles/cloudbuild.builds.builder"     # To delete Cloud Build triggers (if any exist from old deployments)
  ])
  
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.teardown.email}"
}

# Upload teardown script to GCS
resource "google_storage_bucket_object" "teardown_script" {
  name   = "${var.workspace_name}/teardown.sh"
  bucket = google_storage_bucket.terraform_files.name
  source = "${path.module}/teardown_script.sh"
}

# Cloud Run Job for teardown
resource "google_cloud_run_v2_job" "teardown" {
  name                = "deployml-teardown-${var.workspace_name}"
  location            = var.region
  project             = var.project_id
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.teardown.email
      containers {
        image = "gcr.io/google.com/cloudsdktool/cloud-sdk:latest"
        
        command = ["bash"]
        args = [
          "-c",
          <<-EOT
            # Download teardown script
            gsutil cp gs://${google_storage_bucket.terraform_files.name}/${var.workspace_name}/teardown.sh /tmp/teardown.sh
            chmod +x /tmp/teardown.sh
            
            # Set environment variables
            export WORKSPACE_NAME="${var.workspace_name}"
            export PROJECT_ID="${var.project_id}"
            export REGION="${var.region}"
            
            # Run teardown script
            /tmp/teardown.sh
          EOT
        ]
        
        resources {
          limits = {
            cpu    = "2"
            memory = "2Gi"
          }
        }
      }
      
      timeout = "1800s"  # 30 minutes
    }
  }

  depends_on = [
    google_project_service.required,
    google_storage_bucket_object.teardown_script
  ]
}

# Grant Cloud Scheduler (via compute service account) permission to invoke the Cloud Run Job
resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.teardown.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# Cloud Scheduler job that triggers Cloud Run Job
resource "google_cloud_scheduler_job" "teardown" {
  name        = "deployml-teardown-${var.workspace_name}"
  description = "Auto-teardown job for DeployML workspace: ${var.workspace_name}"
  schedule    = var.schedule
  time_zone   = var.time_zone
  region      = var.region
  project     = var.project_id

  http_target {
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.teardown.name}:run"
    http_method = "POST"
    
    oauth_token {
      service_account_email = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
    }
  }

  depends_on = [
    google_project_service.required,
    google_cloud_run_v2_job_iam_member.scheduler_invoker
  ]
}
