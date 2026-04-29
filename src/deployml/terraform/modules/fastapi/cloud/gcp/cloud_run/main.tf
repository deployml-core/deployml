data "google_project" "current" {}

resource "google_cloud_run_service" "fastapi" {
  name     = var.service_name
  location = var.region
  project  = var.project_id

  template {
    metadata {
      annotations = merge({
        "autoscaling.knative.dev/maxScale" = "10"
        "run.googleapis.com/cpu-throttling" = "false"
        "run.googleapis.com/execution-environment" = "gen2"
      }, var.use_postgres && var.cloudsql_instance_annotation != "" ? {
        "run.googleapis.com/cloudsql-instances" = var.cloudsql_instance_annotation
      } : {})
    }
    spec {
      service_account_name = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
      containers {
        image = var.image
        env {
          name  = "MLFLOW_TRACKING_URI"
          value = var.mlflow_tracking_uri
        }
        env {
          name  = "MODEL_URI"
          value = var.model_uri
        }
        env {
          name  = "BACKEND_STORE_URI"
          value = var.backend_store_uri
        }
        env {
          name  = "USE_POSTGRES"
          value = var.use_postgres ? "true" : "false"
        }
        env {
          name  = "DATABASE_URL"
          value = var.use_postgres ? (var.db_connection_string != "" ? var.db_connection_string : var.backend_store_uri) : "sqlite:///app.db"
        }
        env {
          name  = "FEAST_SERVICE_URL"
          value = var.feast_service_url
        }
        env {
          name  = "ENABLE_FEAST_CONNECTION"
          value = var.enable_feast_connection ? "true" : "false"
        }
        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = var.project_id
        }
        env {
          name  = "BIGQUERY_DATASET"
          value = var.bigquery_dataset
        }
        resources {
          limits = {
            cpu    = var.cpu_limit
            memory = var.memory_limit
          }
        }
        ports {
          container_port = 8080
        }
        
        # Health check
        liveness_probe {
          http_get {
            path = "/health"
            port = 8080
          }
          initial_delay_seconds = 30
          timeout_seconds = 10
          period_seconds = 30
          failure_threshold = 3
        }
        
        startup_probe {
          http_get {
            path = "/health"
            port = 8080
          }
          initial_delay_seconds = 10
          timeout_seconds = 10
          period_seconds = 10
          failure_threshold = 10
        }
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}

resource "google_cloud_run_service_iam_member" "public" {
  count    = var.allow_public_access ? 1 : 0
  location = google_cloud_run_service.fastapi.location
  project  = google_cloud_run_service.fastapi.project
  service  = google_cloud_run_service.fastapi.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_project_iam_member" "fastapi_storage_object_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "fastapi_storage_object_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "fastapi_bigquery_user" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "fastapi_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_storage_bucket_iam_member" "fastapi_mlflow_artifact_access" {
  count  = var.mlflow_artifact_bucket != "" && var.mlflow_bucket_exists ? 1 : 0
  bucket = var.mlflow_artifact_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
} 