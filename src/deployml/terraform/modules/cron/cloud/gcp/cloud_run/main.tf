# modules/cron/cloud/gcp/cloud_run/main.tf
# Workflow orchestration module for multiple scheduled Cloud Run Jobs

resource "google_project_service" "required" {
  for_each           = toset(var.gcp_service_list)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

data "google_project" "current" {}

# Create a dedicated service account for Cloud Scheduler
resource "google_service_account" "scheduler_sa" {
  account_id   = "cloud-scheduler-sa"
  display_name = "Cloud Scheduler Service Account"
  project      = var.project_id
  depends_on   = [google_project_service.required]
}

# Create Cloud Run Jobs for each job configuration
resource "google_cloud_run_v2_job" "scheduled_jobs" {
  for_each = { for job in var.jobs : job.service_name => job }
  
  name                = each.value.service_name
  location            = var.region
  project             = var.project_id
  deletion_protection = false
  depends_on          = [google_project_service.required]

  template {
    task_count  = 1
    parallelism = 1
    
    template {
      max_retries     = 3
      service_account = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
      
      # Add Cloud SQL volume if connection name is provided
      dynamic "volumes" {
        for_each = var.cloud_sql_connection_name != "" ? [1] : []
        content {
          name = "cloudsql"
          cloud_sql_instance {
            instances = [var.cloud_sql_connection_name]
          }
        }
      }
      
      containers {
        image = each.value.image
        
        # Mount Cloud SQL socket if needed
        dynamic "volume_mounts" {
          for_each = var.cloud_sql_connection_name != "" ? [1] : []
          content {
            name       = "cloudsql"
            mount_path = "/cloudsql"
          }
        }
        
        # Common environment variables
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        
        env {
          name  = "REGION"
          value = var.region
        }
        
        # BigQuery dataset for offline scoring jobs
        dynamic "env" {
          for_each = can(each.value.bigquery_dataset) && each.value.bigquery_dataset != "" ? [1] : []
          content {
            name  = "BIGQUERY_DATASET"
            value = each.value.bigquery_dataset
          }
        }
        
        # Feast-specific environment variables for offline scoring
        dynamic "env" {
          for_each = can(each.value.bigquery_dataset) && contains(["offline-scoring"], each.value.service_name) ? [1] : []
          content {
            name  = "FEAST_OFFLINE_STORE_PROJECT_ID"
            value = var.project_id
          }
        }
        
        dynamic "env" {
          for_each = can(each.value.bigquery_dataset) && contains(["offline-scoring"], each.value.service_name) ? [1] : []
          content {
            name  = "FEAST_OFFLINE_STORE_DATASET"
            value = each.value.bigquery_dataset
          }
        }
        
        # MLflow configuration for both jobs
        dynamic "env" {
          for_each = var.mlflow_tracking_uri != "" ? [1] : []
          content {
            name  = "MLFLOW_TRACKING_URI"
            value = var.mlflow_tracking_uri
          }
        }
        
        # Database connection for storing results
        dynamic "env" {
          for_each = var.database_url != "" ? [1] : []
          content {
            name  = "DATABASE_URL"
            value = var.database_url
          }
        }
        
        # Feast online store configuration (PostgreSQL)
        dynamic "env" {
          for_each = var.feast_online_store_host != "" ? [1] : []
          content {
            name  = "FEAST_ONLINE_STORE_HOST"
            value = var.feast_online_store_host
          }
        }
        
        dynamic "env" {
          for_each = var.feast_online_store_port != "" ? [1] : []
          content {
            name  = "FEAST_ONLINE_STORE_PORT"
            value = var.feast_online_store_port
          }
        }
        
        dynamic "env" {
          for_each = var.feast_online_store_database != "" ? [1] : []
          content {
            name  = "FEAST_ONLINE_STORE_DATABASE"
            value = var.feast_online_store_database
          }
        }
        
        dynamic "env" {
          for_each = var.feast_online_store_user != "" ? [1] : []
          content {
            name  = "FEAST_ONLINE_STORE_USER"
            value = var.feast_online_store_user
          }
        }
        
        dynamic "env" {
          for_each = var.feast_online_store_password != "" ? [1] : []
          content {
            name  = "FEAST_ONLINE_STORE_PASSWORD"
            value = var.feast_online_store_password
          }
        }
        
        # Feast registry path
        dynamic "env" {
          for_each = var.feast_registry_path != "" ? [1] : []
          content {
            name  = "FEAST_REGISTRY_PATH"
            value = var.feast_registry_path
          }
        }
        
        # Monitoring-specific environment variables for drift monitoring
        dynamic "env" {
          for_each = contains(["drift-monitoring"], each.value.service_name) ? [1] : []
          content {
            name  = "MONITORING_MODE"
            value = "drift_detection"
          }
        }
        
        # Grafana configuration for drift monitoring
        dynamic "env" {
          for_each = var.grafana_url != "" && contains(["drift-monitoring"], each.value.service_name) ? [1] : []
          content {
            name  = "GRAFANA_URL"
            value = var.grafana_url
          }
        }
        
        dynamic "env" {
          for_each = var.grafana_api_key != "" && contains(["drift-monitoring"], each.value.service_name) ? [1] : []
          content {
            name  = "GRAFANA_API_KEY"
            value = var.grafana_api_key
          }
        }
        
        resources {
          limits = {
            cpu    = var.cpu_limit
            memory = var.memory_limit
          }
        }
      }
    }
  }
}

# Grant Cloud Run Invoker permission to the scheduler service account for each job
resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  for_each = { for job in var.jobs : job.service_name => job }
  
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.scheduled_jobs[each.key].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler_sa.email}"
}

# Also grant invoker permission to the compute service account (for direct invocations)
resource "google_cloud_run_v2_job_iam_member" "compute_invoker" {
  for_each = { for job in var.jobs : job.service_name => job }
  
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.scheduled_jobs[each.key].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# Create Cloud Scheduler jobs for each scheduled job
resource "google_cloud_scheduler_job" "scheduled_cron_jobs" {
  for_each = { for job in var.jobs : job.service_name => job }
  
  name               = "${each.value.service_name}-cron"
  description        = "Scheduled job for ${each.value.service_name}"
  schedule           = each.value.cron_schedule
  time_zone          = var.time_zone
  region             = var.region
  project            = var.project_id
  
  depends_on = [
    google_project_service.required,
    google_cloud_run_v2_job.scheduled_jobs,
    google_cloud_run_v2_job_iam_member.scheduler_invoker
  ]

  http_target {
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.scheduled_jobs[each.key].name}:run"
    http_method = "POST"
    
    oauth_token {
      service_account_email = google_service_account.scheduler_sa.email
    }
    
    headers = {
      "Content-Type" = "application/json"
    }
  }

  retry_config {
    retry_count          = 3
    max_retry_duration   = "600s"
    min_backoff_duration = "5s"
    max_backoff_duration = "3600s"
    max_doublings        = 5
  }
}

# Grant required permissions to the compute service account

# BigQuery permissions for offline scoring jobs
resource "google_project_iam_member" "bigquery_data_viewer" {
  count   = length([for job in var.jobs : job if can(job.bigquery_dataset) && job.bigquery_dataset != ""]) > 0 ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "bigquery_job_user" {
  count   = length([for job in var.jobs : job if can(job.bigquery_dataset) && job.bigquery_dataset != ""]) > 0 ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# Cloud SQL client permissions
resource "google_project_iam_member" "cloudsql_client" {
  count   = var.database_url != "" ? 1 : 0
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# Grant Cloud Run Developer permission (for listing/describing jobs)
resource "google_project_iam_member" "run_developer" {
  count   = length(var.jobs) > 0 ? 1 : 0
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# Monitoring permissions for drift monitoring jobs
resource "google_project_iam_member" "monitoring_viewer" {
  count   = length([for job in var.jobs : job if contains(["drift-monitoring"], job.service_name)]) > 0 ? 1 : 0
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "monitoring_metric_writer" {
  count   = length([for job in var.jobs : job if contains(["drift-monitoring"], job.service_name)]) > 0 ? 1 : 0
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# Grant the scheduler service account the Cloud Scheduler Job Runner role
resource "google_project_iam_member" "scheduler_job_runner" {
  project = var.project_id
  role    = "roles/cloudscheduler.jobRunner"
  member  = "serviceAccount:${google_service_account.scheduler_sa.email}"
}

# Grant the scheduler service account permission to act as the compute service account
resource "google_service_account_iam_member" "scheduler_act_as" {
  service_account_id = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.scheduler_sa.email}"
}
