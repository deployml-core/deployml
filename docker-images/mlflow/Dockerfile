# Build for Linux/amd64 platform (not Apple Silicon)
FROM --platform=linux/amd64 python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install MLflow and dependencies
RUN pip install --no-cache-dir \
    mlflow==2.8.1 \
    psycopg2-binary \
    boto3 \
    google-cloud-storage

# Create non-root user
RUN useradd -m -s /bin/bash mlflow && \
    chown -R mlflow:mlflow /app

# Create directories for MLflow data
RUN mkdir -p /mlflow-artifacts && \
    chown -R mlflow:mlflow /mlflow-artifacts

# Switch to non-root user
USER mlflow

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Default command - MLflow server
CMD ["mlflow", "server", "--host", "0.0.0.0", "--port", "5000"]

