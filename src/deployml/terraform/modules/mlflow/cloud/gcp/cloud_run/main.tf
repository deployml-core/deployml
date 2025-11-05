# modules/mlflow/cloud/gcp/cloud_run/main.tf

resource "google_project_service" "required" {
  for_each           = toset(var.gcp_service_list)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

data "google_project" "current" {}

# Cloud Run service - only create if explicitly requested
resource "google_cloud_run_service" "mlflow" {
  count    = var.create_service && var.image != "" && var.service_name != "" ? 1 : 0
  name     = var.service_name
  location = var.region
  project  = var.project_id
  depends_on = [google_project_service.required]

  template {
    metadata {
      annotations = merge({
        "autoscaling.knative.dev/maxScale" = "10"
        "run.googleapis.com/cpu-throttling" = "false"
      }, var.cloudsql_instance_annotation != "" ? {
        "run.googleapis.com/cloudsql-instances" = var.cloudsql_instance_annotation
      } : {})
    }
    
    spec {
      container_concurrency = 80
      timeout_seconds       = 300
      
      containers {
        image = var.image        
        # Always set basic MLflow environment
        env {
          name  = "MLFLOW_SERVER_HOST"
          value = "0.0.0.0"
        }
        
        env {
          name  = "MLFLOW_SERVER_PORT"
          value = "8080"
        }
        
        # Backend store URI
        dynamic "env" {
          for_each = var.backend_store_uri != "" ? [1] : []
          content {
            name  = "MLFLOW_BACKEND_STORE_URI"
            value = var.backend_store_uri
          }
        }
        
        # Artifact root - use bucket if provided, otherwise local
        env {
          name = "MLFLOW_DEFAULT_ARTIFACT_ROOT"
          value = var.artifact_bucket != "" ? "gs://${var.artifact_bucket}" : "/tmp/mlflow-artifacts"
        }

        ports {
          container_port = 8080
        }
        
        resources {
          limits = {
            cpu    = var.cpu_limit
            memory = var.memory_limit
          }
          requests = {
            cpu    = var.cpu_request
            memory = var.memory_request
          }
        }
      }
    }
  }
  
  traffic {
    percent         = 100
    latest_revision = true
  }
  
  autogenerate_revision_name = true
}

# Make the service publicly accessible
resource "google_cloud_run_service_iam_member" "public" {
  count    = var.create_service && var.image != "" && var.service_name != "" && var.allow_public_access ? 1 : 0
  location = google_cloud_run_service.mlflow[0].location
  project  = google_cloud_run_service.mlflow[0].project
  service  = google_cloud_run_service.mlflow[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Grant Cloud Run service account access to the artifact bucket
resource "google_storage_bucket_iam_member" "mlflow_service_access" {
  count  = var.artifact_bucket != "" && var.bucket_exists ? 1 : 0
  bucket = var.artifact_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}