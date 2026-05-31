data "google_project" "current" {}

# Store the Feast DB password in Secret Manager so it is not visible as a
# plaintext env var in the Cloud Run console or Cloud Logging.
resource "google_secret_manager_secret" "feast_db_password" {
  count     = var.use_postgres && var.postgres_password != "" ? 1 : 0
  project   = var.project_id
  secret_id = "${var.service_name}-feast-db-password"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "feast_db_password" {
  count       = var.use_postgres && var.postgres_password != "" ? 1 : 0
  secret      = google_secret_manager_secret.feast_db_password[0].id
  secret_data = var.postgres_password
}

resource "google_secret_manager_secret_iam_member" "feast_db_password_access" {
  count     = var.use_postgres && var.postgres_password != "" ? 1 : 0
  project   = var.project_id
  secret_id = google_secret_manager_secret.feast_db_password[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_cloud_run_service" "feast" {
  name     = var.service_name
  location = var.region
  project  = var.project_id

  template {
    metadata {
      annotations = var.use_postgres && var.cloudsql_instance_annotation != "" ? {
        "autoscaling.knative.dev/maxScale"         = var.max_scale
        "run.googleapis.com/cloudsql-instances"    = var.cloudsql_instance_annotation
        "run.googleapis.com/execution-environment" = "gen2"
        "run.googleapis.com/memory"                = var.memory_limit
        "run.googleapis.com/cpu"                   = var.cpu_limit
        } : {
        "autoscaling.knative.dev/maxScale"         = var.max_scale
        "run.googleapis.com/execution-environment" = "gen2"
        "run.googleapis.com/memory"                = var.memory_limit
        "run.googleapis.com/cpu"                   = var.cpu_limit
      }
    }
    spec {
      service_account_name  = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
      container_concurrency = var.container_concurrency
      containers {
        image = var.image

        env {
          name  = "FEAST_REGISTRY_TYPE"
          value = var.use_postgres ? "sql" : "file"
        }

        env {
          name  = "FEAST_REGISTRY_PATH"
          value = var.backend_store_uri
        }

        env {
          name  = "FEAST_ONLINE_STORE_TYPE"
          value = var.use_postgres ? "postgres" : "sqlite"
        }

        env {
          name  = "FEAST_ONLINE_STORE_HOST"
          value = var.postgres_host
        }

        env {
          name  = "FEAST_ONLINE_STORE_PORT"
          value = var.postgres_port
        }

        env {
          name  = "FEAST_ONLINE_STORE_DATABASE"
          value = var.postgres_database
        }

        env {
          name  = "FEAST_ONLINE_STORE_USER"
          value = var.postgres_user
        }

        # Inject the DB password via Secret Manager so it does not appear in
        # Cloud Run env tab or Cloud Logging in plaintext.
        dynamic "env" {
          for_each = var.use_postgres && var.postgres_password != "" ? [1] : []
          content {
            name = "FEAST_ONLINE_STORE_PASSWORD"
            value_from {
              secret_key_ref {
                name = google_secret_manager_secret.feast_db_password[0].secret_id
                key  = "latest"
              }
            }
          }
        }

        env {
          name  = "USE_POSTGRES"
          value = var.use_postgres ? "true" : "false"
        }

        env {
          name  = "FEAST_OFFLINE_STORE_TYPE"
          value = var.offline_store
        }

        env {
          name  = "FEAST_ARTIFACT_BUCKET"
          value = var.artifact_bucket
        }

        env {
          name  = "FEAST_BIGQUERY_PROJECT"
          value = var.bigquery_project != "" ? var.bigquery_project : var.project_id
        }

        env {
          name  = "FEAST_BIGQUERY_DATASET"
          value = var.bigquery_dataset
        }

        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = var.bigquery_project != "" ? var.bigquery_project : var.project_id
        }

        env {
          name  = "FEAST_OFFLINE_STORE_DATASET"
          value = var.bigquery_dataset
        }

        env {
          name  = "FEAST_OFFLINE_STORE_PROJECT_ID"
          value = var.bigquery_project != "" ? var.bigquery_project : var.project_id
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

        startup_probe {
          http_get {
            path = "/health"
            port = 8080
          }
          failure_threshold     = 20  # Allow 20 failed attempts
          initial_delay_seconds = 240 # Wait 2 minutes before first check
          period_seconds        = 30  # Check every 30 seconds
          timeout_seconds       = 10  # Each check times out after 10 seconds
        }

        liveness_probe {
          http_get {
            path = "/health"
            port = 8080
          }
          initial_delay_seconds = 240
          timeout_seconds       = 25
          period_seconds        = 30
          failure_threshold     = 3
        }
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  depends_on = [
    google_project_service.feast_apis,
    google_secret_manager_secret_iam_member.feast_db_password_access,
  ]
}

resource "google_cloud_run_service_iam_member" "public" {
  count    = var.allow_public_access ? 1 : 0
  location = google_cloud_run_service.feast.location
  project  = google_cloud_run_service.feast.project
  service  = google_cloud_run_service.feast.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_project_service" "feast_apis" {
  for_each = toset([
    "run.googleapis.com",
    "bigquery.googleapis.com",
    "storage.googleapis.com"
  ])

  project = var.project_id
  service = each.value

  disable_on_destroy = false
}

resource "google_project_iam_member" "feast_storage_object_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "feast_bigquery_user" {
  project = var.project_id
  role    = "roles/bigquery.user"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "feast_bigquery_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "feast_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "feast_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_storage_bucket_iam_member" "feast_artifact_access" {
  count  = var.artifact_bucket != "" ? 1 : 0
  bucket = var.artifact_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

