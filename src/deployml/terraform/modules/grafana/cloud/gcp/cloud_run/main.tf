data "google_project" "current" {}

# Auto-generated admin password. Lives in Secret Manager so the Grafana image
# does not carry a baked default credential.
resource "random_password" "grafana_admin" {
  length  = 20
  special = false
}

resource "google_secret_manager_secret" "grafana_admin" {
  project   = var.project_id
  secret_id = "${var.service_name}-admin-password"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "grafana_admin" {
  secret      = google_secret_manager_secret.grafana_admin.id
  secret_data = random_password.grafana_admin.result
}

resource "google_secret_manager_secret_iam_member" "grafana_admin_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.grafana_admin.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

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

        # Metrics DB URL. Prefer Secret Manager when secret_id is provided.
        dynamic "env" {
          for_each = var.use_metrics_database && var.metrics_connection_string != "" && var.metrics_connection_string_secret_id == "" ? [1] : []
          content {
            name  = "GF_DATABASE_URL"
            value = var.metrics_connection_string
          }
        }
        dynamic "env" {
          for_each = var.use_metrics_database && var.metrics_connection_string_secret_id != "" ? [1] : []
          content {
            name = "GF_DATABASE_URL"
            value_from {
              secret_key_ref {
                name = var.metrics_connection_string_secret_id
                key  = "latest"
              }
            }
          }
        }

        dynamic "env" {
          for_each = var.use_metrics_database ? [1] : []
          content {
            name  = "GF_DATABASE_TYPE"
            value = "postgres"
          }
        }

        env {
          name  = "GF_SERVER_HTTP_PORT"
          value = "8080"
        }

        env {
          name  = "GF_SECURITY_ADMIN_USER"
          value = "admin"
        }

        env {
          name = "GF_SECURITY_ADMIN_PASSWORD"
          value_from {
            secret_key_ref {
              name = google_secret_manager_secret.grafana_admin.secret_id
              key  = "latest"
            }
          }
        }
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  depends_on = [
    google_secret_manager_secret_iam_member.grafana_admin_access,
  ]
}

resource "google_cloud_run_service_iam_member" "public" {
  count    = var.allow_public_access ? 1 : 0
  location = google_cloud_run_service.grafana.location
  project  = google_cloud_run_service.grafana.project
  service  = google_cloud_run_service.grafana.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_project_iam_member" "grafana_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}
