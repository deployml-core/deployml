# modules/offline_scoring/cloud/gcp/cloud_run/main.tf

resource "google_project_service" "required" {
  for_each           = toset(var.gcp_service_list)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

data "google_project" "current" {}

# Cloud Run Job for offline scoring
resource "google_cloud_run_v2_job" "offline_scoring" {
  count               = var.create_service && var.image != "" && var.service_name != "" ? 1 : 0
  name                = var.service_name
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
      
      containers {
        image = var.image
        
        # Environment variables for offline scoring
        env {
          name  = "FEAST_OFFLINE_STORE_PROJECT_ID"
          value = var.project_id
        }
        
        env {
          name  = "FEAST_OFFLINE_STORE_DATASET"
          value = var.bigquery_dataset != "" ? var.bigquery_dataset : ""
        }
        
        # Database connection for storing results
        dynamic "env" {
          for_each = var.database_url != "" ? [1] : []
          content {
            name  = "DATABASE_URL"
            value = var.database_url
          }
        }
        
        # MLflow configuration
        dynamic "env" {
          for_each = var.mlflow_tracking_uri != "" ? [1] : []
          content {
            name  = "MLFLOW_TRACKING_URI"
            value = var.mlflow_tracking_uri
          }
        }
        
        # Optional MLflow configuration - only set if provided
        dynamic "env" {
          for_each = var.model_name != "" ? [1] : []
          content {
            name  = "MODEL_NAME"
            value = var.model_name
          }
        }
        
        dynamic "env" {
          for_each = var.model_stage != "" ? [1] : []
          content {
            name  = "MODEL_STAGE"
            value = var.model_stage
          }
        }
        
        # Optional batch processing configuration - only set if provided
        dynamic "env" {
          for_each = var.batch_size != "" ? [1] : []
          content {
            name  = "BATCH_SIZE"
            value = var.batch_size
          }
        }
        
        dynamic "env" {
          for_each = var.days_lookback != "" ? [1] : []
          content {
            name  = "DAYS_LOOKBACK"
            value = var.days_lookback
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
        
        # Feast registry path (PostgreSQL connection for registry)
        dynamic "env" {
          for_each = var.feast_registry_path != "" ? [1] : []
          content {
            name  = "FEAST_REGISTRY_PATH"
            value = var.feast_registry_path
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

# Grant BigQuery permissions for reading feature data
resource "google_project_iam_member" "bigquery_data_viewer" {
  count   = var.create_service ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "bigquery_job_user" {
  count   = var.create_service ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# Cloud SQL client permissions are already granted to the compute service account
resource "google_project_iam_member" "cloudsql_client" {
  count   = var.create_service ? 1 : 0
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# Cloud Scheduler job for cron-based execution
resource "google_cloud_scheduler_job" "offline_scoring_cron" {
  count               = var.create_service && var.enable_cron ? 1 : 0
  name                = "${var.service_name}-cron"
  description         = "Scheduled offline scoring job"
  schedule            = var.cron_schedule
  time_zone           = var.time_zone
  region              = var.region
  project             = var.project_id
  deletion_protection = false
  depends_on          = [google_project_service.required]

  http_target {
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.offline_scoring[0].name}:run"
    http_method = "POST"
    
    oauth_token {
      service_account_email = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
    }
  }

  retry_config {
    retry_count = 3
  }
}

# Grant Cloud Scheduler permission to execute Cloud Run jobs
resource "google_project_iam_member" "scheduler_job_runner" {
  count   = var.create_service && var.enable_cron ? 1 : 0
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}