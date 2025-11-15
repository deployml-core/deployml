# Fairness Monitoring Cloud Run Job
# Runs on a schedule to detect bias and calculate fairness metrics

resource "google_cloud_run_v2_job" "fairness_checker" {
  name                = "${var.stack_name}-fairness-checker"
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
          name  = "SENSITIVE_ATTRIBUTES"
          value = jsonencode(var.sensitive_attributes)
        }
        
        env {
          name  = "FAIRNESS_METRICS"
          value = jsonencode(var.fairness_metrics)
        }
        
        env {
          name  = "DEMOGRAPHIC_PARITY_THRESHOLD"
          value = tostring(var.demographic_parity_threshold)
        }
        
        env {
          name  = "DISPARATE_IMPACT_THRESHOLD"
          value = tostring(var.disparate_impact_threshold)
        }
        
        env {
          name  = "ALERT_ON_VIOLATION"
          value = tostring(var.alert_on_violation)
        }
        
        dynamic "env" {
          for_each = var.alert_webhook_url != "" ? [1] : []
          content {
            name  = "ALERT_WEBHOOK_URL"
            value = var.alert_webhook_url
          }
        }
        
        dynamic "env" {
          for_each = var.protected_groups != null ? [1] : []
          content {
            name  = "PROTECTED_GROUPS"
            value = jsonencode(var.protected_groups)
          }
        }
      }
      
      service_account = var.service_account_email
      timeout         = "900s"  # 15 minutes max
    }
  }

  lifecycle {
    ignore_changes = [
      launch_stage,
    ]
  }
}

# Cloud Scheduler to trigger the fairness monitoring job
resource "google_cloud_scheduler_job" "fairness_schedule" {
  name                = "${var.stack_name}-fairness-checker-cron"
  description         = "Trigger fairness monitoring job"
  schedule            = var.schedule
  time_zone           = var.time_zone
  region              = var.region
  project             = var.project_id
  deletion_protection = false

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.fairness_checker.name}:run"
    
    oauth_token {
      service_account_email = var.service_account_email
    }
  }

  depends_on = [google_cloud_run_v2_job.fairness_checker]
}

# IAM binding to allow Cloud Scheduler to invoke the job
resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.fairness_checker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.service_account_email}"
}

