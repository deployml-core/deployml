resource "google_bigquery_dataset" "mlops" {
  project    = var.project_id
  dataset_id = var.dataset_id
  location   = var.region
}

 resource "google_bigquery_table" "drift_metrics" {
  dataset_id = google_bigquery_dataset.mlops.dataset_id
  table_id   = "drift_metrics"
  project    = var.project_id

  schema = file("${path.module}/schemas/drift_metrics.json")
  deletion_protection = false
}

resource "google_bigquery_table" "ground_truth" {
  dataset_id = google_bigquery_dataset.mlops.dataset_id
  table_id   = "ground_truth"
  project    = var.project_id

  schema = file("${path.module}/schemas/ground_truth.json")
  deletion_protection = false
}

resource "google_bigquery_table" "offline_features" {
  dataset_id = google_bigquery_dataset.mlops.dataset_id
  table_id   = "offline_features"
  project    = var.project_id

  schema = file("${path.module}/schemas/offline_features.json")
  deletion_protection = false
}

resource "google_bigquery_table" "predictions" {
  dataset_id = google_bigquery_dataset.mlops.dataset_id
  table_id   = "predictions"
  project    = var.project_id

  schema = file("${path.module}/schemas/predictions.json")
  deletion_protection = false
}

