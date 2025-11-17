# Explainability Monitoring Cloud Run Job
# Runs on a schedule to analyze SHAP values and track feature importance

resource "google_cloud_run_v2_job" "explainability_monitor" {
  name                = "${var.stack_name}-explainability-monitor"
  location            = var.region
  project             = var.project_id
  deletion_protection = false

  template {
    template {
      containers {
        image = var.image
        
        env {
          name  = "DATABASE_URL"
          value = var.database_url
        }
        
        env {
          name  = "MLFLOW_TRACKING_URI"
          value = var.mlflow_tracking_uri
        }
        
        env {
          name  = "IMPORTANCE_SHIFT_THRESHOLD"
          value = tostring(var.importance_shift_threshold)
        }
        
        env {
          name  = "TRACK_FEATURE_IMPORTANCE"
          value = tostring(var.track_feature_importance)
        }
        
        env {
          name  = "ALERT_ON_SHIFT"
          value = tostring(var.alert_on_importance_shift)
        }
        
        dynamic "env" {
          for_each = var.alert_webhook_url != "" ? [1] : []
          content {
            name  = "ALERT_WEBHOOK_URL"
            value = var.alert_webhook_url
          }
        }
      }
      
      service_account = var.service_account_email
      timeout         = "600s"  # 10 minutes max
    }
  }

  lifecycle {
    ignore_changes = [
      launch_stage,
    ]
  }
}

# Cloud Scheduler to trigger the explainability monitoring job
resource "google_cloud_scheduler_job" "explainability_schedule" {
  name                = "${var.stack_name}-explainability-monitor-cron"
  description         = "Trigger explainability monitoring job"
  schedule            = var.schedule
  time_zone           = var.time_zone
  region              = var.region
  project             = var.project_id
  deletion_protection = false

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.explainability_monitor.name}:run"
    
    oauth_token {
      service_account_email = var.service_account_email
    }
  }

  depends_on = [google_cloud_run_v2_job.explainability_monitor]
}

# IAM binding to allow Cloud Scheduler to invoke the job
resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.explainability_monitor.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.service_account_email}"
}

