
output "db_user" {
  value = var.db_user
}

output "db_password" {
  value     = random_password.db_password.result
  sensitive = true
}

output "db_name" {
  value = var.db_name
}

output "db_public_ip" {
  value = google_sql_database_instance.postgres.public_ip_address
}

output "connection_string" {
  value     = "postgresql+psycopg2://${var.db_user}:${urlencode(random_password.db_password.result)}@${google_sql_database_instance.postgres.public_ip_address}:5432/${var.db_name}"
  sensitive = true
}

output "instance_connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}

output "connection_string_cloud_sql" {
  value     = "postgresql+psycopg2://${var.db_user}:${urlencode(random_password.db_password.result)}@/mlflow?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
  sensitive = true
}

output "postgresql_credentials" {
  description = "All credentials and connection info for the Cloud SQL PostgreSQL instance."
  sensitive   = true
  value = {
    db_user                  = var.db_user
    db_password              = random_password.db_password.result
    db_name                  = var.db_name
    db_public_ip             = google_sql_database_instance.postgres.public_ip_address
    instance_connection_name = google_sql_database_instance.postgres.connection_name
    connection_string        = "postgresql+psycopg2://${var.db_user}:${urlencode(random_password.db_password.result)}@${google_sql_database_instance.postgres.public_ip_address}:5432/${var.db_name}"
  }
}

output "feast_connection_string" {
  value     = "postgresql+psycopg2://${var.db_user}:${urlencode(random_password.db_password.result)}@${google_sql_database_instance.postgres.public_ip_address}:5432/feast"
  sensitive = true
}

output "feast_connection_string_cloud_sql" {
  value     = "postgresql+psycopg2://${var.db_user}:${urlencode(random_password.db_password.result)}@/feast?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
  sensitive = true
}

output "metrics_connection_string" {
  value     = "postgresql+psycopg2://${var.db_user}:${urlencode(random_password.db_password.result)}@${google_sql_database_instance.postgres.public_ip_address}:5432/metrics"
  sensitive = true
}

output "metrics_connection_string_cloud_sql" {
  value     = "postgresql+psycopg2://${var.db_user}:${urlencode(random_password.db_password.result)}@/metrics?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
  sensitive = true
}

# Grafana-friendly connection URL using lib/pq style
output "grafana_connection_string_cloud_sql" {
  description = "Postgres connection URL suitable for Grafana using Cloud SQL Unix socket"
  sensitive   = true
  value = "postgres://${var.db_user}:${random_password.db_password.result}@/metrics?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}&sslmode=disable"
}

output "postgres_host" {
  value = google_sql_database_instance.postgres.public_ip_address
}

output "postgres_port" {
  value = "5432"
}

output "postgres_database" {
  value = "feast"
}

output "postgres_user" {
  value = var.db_user
}

output "postgres_password" {
  value     = random_password.db_password.result
  sensitive = true
}

output "instance_name" {
  value = google_sql_database_instance.postgres.name
}

output "mlflow_dsn_secret_id" {
  description = "Secret Manager ID holding the MLflow DSN. Cloud Run reads it via value_from instead of carrying the password in env."
  value       = google_secret_manager_secret.mlflow_dsn.secret_id
}

output "grafana_metrics_dsn_secret_id" {
  description = "Secret Manager ID holding the Grafana metrics DSN. Empty when create_metrics_db is false."
  value       = var.create_metrics_db ? google_secret_manager_secret.grafana_metrics_dsn[0].secret_id : ""
}
