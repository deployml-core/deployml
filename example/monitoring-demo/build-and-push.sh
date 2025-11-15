#!/bin/bash
# Build and push all Docker images for linux/amd64 (Cloud Run compatible)

set -e

PROJECT_ID="mldeploy-468919"

echo "🚀 Building and pushing ALL Docker images to gcr.io/$PROJECT_ID (linux/amd64)"
echo ""

# MLflow Server
echo "📦 Building MLflow server image..."
cd mlflow-server
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/mlflow-server:latest .
docker push gcr.io/$PROJECT_ID/mlflow-server:latest
cd ..
echo "✅ MLflow server image pushed"
echo ""

# Feast Server
echo "📦 Building Feast server image..."
cd feast-server
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/feast-server:latest .
docker push gcr.io/$PROJECT_ID/feast-server:latest
cd ..
echo "✅ Feast server image pushed"
echo ""

# Grafana Server
echo "📦 Building Grafana server image..."
cd grafana-server
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/grafana-server:latest .
docker push gcr.io/$PROJECT_ID/grafana-server:latest
cd ..
echo "✅ Grafana server image pushed"
echo ""

# FastAPI Serving
echo "📦 Building FastAPI serving image..."
cd fastapi-serving
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/fastapi-serving:latest .
docker push gcr.io/$PROJECT_ID/fastapi-serving:latest
cd ..
echo "✅ FastAPI serving image pushed"
echo ""

# Drift Monitoring
echo "📦 Building drift monitoring image..."
cd drift-monitoring
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/drift-monitoring:latest .
docker push gcr.io/$PROJECT_ID/drift-monitoring:latest
cd ..
echo "✅ Drift monitoring image pushed"
echo ""

# Offline Scoring
echo "📦 Building offline scoring image..."
cd offline-scoring
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/offline-scoring:latest .
docker push gcr.io/$PROJECT_ID/offline-scoring:latest
cd ..
echo "✅ Offline scoring image pushed"
echo ""

# Explainability Monitoring
echo "📦 Building explainability monitor image..."
cd explainability-monitor
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/explainability-monitor:latest .
docker push gcr.io/$PROJECT_ID/explainability-monitor:latest
cd ..
echo "✅ Explainability monitor image pushed"
echo ""

# Fairness Monitoring
echo "📦 Building fairness checker image..."
cd fairness-checker
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/fairness-checker:latest .
docker push gcr.io/$PROJECT_ID/fairness-checker:latest
cd ..
echo "✅ Fairness checker image pushed"
echo ""

echo "🎉 All images built and pushed successfully!"
echo ""
echo "Ready to deploy using Python API:"
echo "  import deployml"
echo "  deployml.deploy('deployment-config.yaml')"

