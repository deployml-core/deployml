# Build for Linux/amd64 platform (not Apple Silicon)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
# Uses PORT env var so it works on Cloud Run (PORT=8080) and locally (PORT=5000)
CMD mlflow server --host 0.0.0.0 --port ${PORT:-5000} --dev --allowed-hosts '*'

