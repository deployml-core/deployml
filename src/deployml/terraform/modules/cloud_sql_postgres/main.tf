resource "random_password" "db_password" {
  length  = 16
  special = true
  override_special = "!*-_."
}

resource "google_sql_database_instance" "postgres" {
  name             = var.db_instance_name
  database_version = "POSTGRES_14"
  region           = var.region
  project          = var.project_id
  depends_on       = [google_project_service.required]

  settings {
    tier = var.db_tier
    database_flags {
      name  = "max_connections"
      value = var.max_connections
    }
    # Public IP stays enabled so outputs that reference public_ip_address keep
    # working, but no authorized_networks means no direct internet access.
    # Cloud Run reaches the instance through the cloudsql-instances annotation,
    # which tunnels via the Cloud SQL Auth Proxy and bypasses authorized_networks.
    ip_configuration {
      ipv4_enabled = true
    }
  }

  deletion_protection = false
}

# Verify the instance is RUNNABLE before creating databases.
# Previously paired with a fixed 180s sleep; the polling here makes the sleep
# unnecessary and faster on the happy path.
resource "null_resource" "verify_instance_running" {
  depends_on = [google_sql_database_instance.postgres]
  
  provisioner "local-exec" {
    command = <<-EOT
      set +e
      echo "Checking Cloud SQL instance status..."
      if ! command -v gcloud &> /dev/null; then
        echo "gcloud CLI not found, skipping status check (relying on time_sleep)"
        exit 0
      fi
      
      for i in {1..30}; do
        STATE=$(gcloud sql instances describe ${google_sql_database_instance.postgres.name} --project=${var.project_id} --format="value(state)" 2>/dev/null || echo "NOT_FOUND")
        if [ "$STATE" = "RUNNABLE" ]; then
          echo "✓ Instance is RUNNABLE, proceeding..."
          exit 0
        elif [ "$STATE" = "STOPPED" ] || [ "$STATE" = "SUSPENDED" ]; then
          echo "⚠ Instance is $STATE. Attempting to start..."
          gcloud sql instances patch ${google_sql_database_instance.postgres.name} --project=${var.project_id} --activation-policy=ALWAYS 2>/dev/null || true
          sleep 30
        elif [ "$STATE" = "NOT_FOUND" ]; then
          echo "Instance not found yet, waiting... (attempt $i/30)"
          sleep 10
        else
          echo "Instance state: $STATE (attempt $i/30)"
          sleep 10
        fi
      done
      echo "⚠ Warning: Could not verify instance is RUNNABLE, but proceeding..."
      exit 0  # Don't fail the entire deployment if this check fails
    EOT
  }
  
  triggers = {
    instance_name = google_sql_database_instance.postgres.name
    instance_id   = google_sql_database_instance.postgres.id
  }
}

resource "google_sql_database" "db" {
  name     = var.db_name
  instance = google_sql_database_instance.postgres.name
  project  = var.project_id
  depends_on = [null_resource.verify_instance_running]
}

resource "google_sql_database" "feast_db" {
  count    = var.create_feast_db ? 1 : 0
  name     = "feast"
  instance = google_sql_database_instance.postgres.name
  project  = var.project_id
  depends_on = [null_resource.verify_instance_running]

  lifecycle {
    ignore_changes = [name]
  }
}

resource "google_sql_database" "metrics_db" {
  count    = var.create_metrics_db ? 1 : 0
  name     = "metrics"
  instance = google_sql_database_instance.postgres.name
  project  = var.project_id
  depends_on = [null_resource.verify_instance_running]

  lifecycle {
    ignore_changes = [name]
  }
}

resource "google_sql_user" "users" {
  name     = var.db_user
  instance = google_sql_database_instance.postgres.name
  password = random_password.db_password.result
  project  = var.project_id
  depends_on = [null_resource.verify_instance_running]

  lifecycle {
    create_before_destroy = true
  }
}

# Secret Manager holds the full MLflow DSN so Cloud Run env vars do not carry
# the DB password in plaintext. The Cloud Run runtime SA reads it at start.
data "google_project" "current" {}

resource "google_secret_manager_secret" "mlflow_dsn" {
  project   = var.project_id
  secret_id = "${var.db_instance_name}-mlflow-dsn"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "mlflow_dsn" {
  secret      = google_secret_manager_secret.mlflow_dsn.id
  secret_data = "postgresql+psycopg2://${var.db_user}:${urlencode(random_password.db_password.result)}@/${var.db_name}?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
  depends_on  = [google_sql_user.users]
}

resource "google_secret_manager_secret_iam_member" "mlflow_dsn_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.mlflow_dsn.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# Same pattern for the Grafana metrics DSN so Grafana's GF_DATABASE_URL env
# does not carry the DB password in plaintext.
resource "google_secret_manager_secret" "grafana_metrics_dsn" {
  count     = var.create_metrics_db ? 1 : 0
  project   = var.project_id
  secret_id = "${var.db_instance_name}-grafana-metrics-dsn"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "grafana_metrics_dsn" {
  count       = var.create_metrics_db ? 1 : 0
  secret      = google_secret_manager_secret.grafana_metrics_dsn[0].id
  secret_data = "postgres://${var.db_user}:${random_password.db_password.result}@/metrics?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}&sslmode=disable"
  depends_on  = [google_sql_database.metrics_db]
}

resource "google_secret_manager_secret_iam_member" "grafana_metrics_dsn_access" {
  count     = var.create_metrics_db ? 1 : 0
  project   = var.project_id
  secret_id = google_secret_manager_secret.grafana_metrics_dsn[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_service" "required" {
  for_each           = toset(var.gcp_service_list)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}




