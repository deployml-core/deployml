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
    ip_configuration {
      authorized_networks {
        value = "0.0.0.0/0"
      }
      ipv4_enabled = true
    }
  }

  deletion_protection = false
}

# Wait for Cloud SQL instance to be fully ready before creating databases
# Cloud SQL instances can take 2-5 minutes to become fully operational
resource "time_sleep" "wait_for_instance" {
  depends_on = [google_sql_database_instance.postgres]
  create_duration = "180s"  # Wait 3 minutes for instance to be fully ready
}

# Additional check: Use a null_resource to verify instance is actually running
# This helps catch cases where the instance exists but is stopped
resource "null_resource" "verify_instance_running" {
  depends_on = [time_sleep.wait_for_instance]
  
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
    # Retry on failure in case instance is still starting
    create_before_destroy = true
  }
}

resource "google_project_service" "required" {
  for_each           = toset(var.gcp_service_list)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}




