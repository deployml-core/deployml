FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install MLflow and dependencies
RUN pip install --no-cache-dir \
    mlflow==2.9.2 \
    psycopg2-binary==2.9.9 \
    boto3==1.28.85 \
    google-cloud-storage==2.10.0

# Expose MLflow port (Cloud Run uses PORT env var, defaults to 8080)
EXPOSE 8080

# Start MLflow server
# Environment variables will be injected by Cloud Run:
# - PORT (Cloud Run sets this to 8080)
# - MLFLOW_BACKEND_STORE_URI (PostgreSQL connection string)
# - MLFLOW_DEFAULT_ARTIFACT_ROOT (GCS bucket path)
CMD mlflow server \
    --host 0.0.0.0 \
    --port ${PORT:-8080} \
    --backend-store-uri ${MLFLOW_BACKEND_STORE_URI:-sqlite:///mlflow.db} \
    --default-artifact-root ${MLFLOW_DEFAULT_ARTIFACT_ROOT:-./mlruns}