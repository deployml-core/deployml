data "google_project" "current" {}

resource "google_cloud_run_service" "grafana" {
  name     = var.service_name
  location = var.region
  project  = var.project_id

  template {
    metadata {
      annotations = var.cloudsql_instance_annotation != "" ? {
        "run.googleapis.com/cloudsql-instances" = var.cloudsql_instance_annotation
      } : {}
    }
    
    spec {
      service_account_name = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
      containers {
        image = var.image
        resources {
          limits = {
            cpu    = var.cpu_limit
            memory = var.memory_limit
          }
        }
        ports {
          container_port = 8080
        }
        
        # Add metrics database connection if enabled
        dynamic "env" {
          for_each = var.use_metrics_database && var.metrics_connection_string != "" ? [1] : []
          content {
            name  = "GF_DATABASE_URL"
            value = var.metrics_connection_string
          }
        }
        
        dynamic "env" {
          for_each = var.use_metrics_database ? [1] : []
          content {
            name  = "GF_DATABASE_TYPE"
            value = "postgres"
          }
        }

        # Ensure Grafana listens on Cloud Run's port
        env {
          name  = "GF_SERVER_HTTP_PORT"
          value = "8080"
        }
        env {
          name  = "GF_SECURITY_ADMIN_USER"
          value = var.grafana_admin_user
        }
        env {
          name  = "GF_SECURITY_ADMIN_PASSWORD"
          value = var.grafana_admin_password
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
  location = google_cloud_run_service.grafana.location
  project  = google_cloud_run_service.grafana.project
  service  = google_cloud_run_service.grafana.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Allow service account to connect to Cloud SQL via socket
resource "google_project_iam_member" "grafana_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}