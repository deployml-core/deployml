#!/bin/bash
# Rebuild and push all Docker images for linux/amd64 (Cloud Run compatible)

set -e

PROJECT_ID="mldeploy-468919"

echo "🚀 Rebuilding ALL images for linux/amd64 platform"
echo ""

# MLflow Server
echo "📦 Building MLflow server image (amd64)..."
cd mlflow-server
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/mlflow-server:latest .
docker push gcr.io/$PROJECT_ID/mlflow-server:latest
cd ..
echo "✅ MLflow server image pushed"
echo ""

# Feast Server
echo "📦 Building Feast server image (amd64)..."
cd feast-server
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/feast-server:latest .
docker push gcr.io/$PROJECT_ID/feast-server:latest
cd ..
echo "✅ Feast server image pushed"
echo ""

# Grafana Server (already working, but rebuild for consistency)
echo "📦 Building Grafana server image (amd64)..."
cd grafana-server
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/grafana-server:latest .
docker push gcr.io/$PROJECT_ID/grafana-server:latest
cd ..
echo "✅ Grafana server image pushed"
echo ""

# FastAPI Serving
echo "📦 Building FastAPI serving image (amd64)..."
cd fastapi-serving
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/fastapi-serving:latest .
docker push gcr.io/$PROJECT_ID/fastapi-serving:latest
cd ..
echo "✅ FastAPI serving image pushed"
echo ""

# Drift Monitoring
echo "📦 Building drift monitoring image (amd64)..."
cd drift-monitoring
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/drift-monitoring:latest .
docker push gcr.io/$PROJECT_ID/drift-monitoring:latest
cd ..
echo "✅ Drift monitoring image pushed"
echo ""

# Offline Scoring
echo "📦 Building offline scoring image (amd64)..."
cd offline-scoring
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/offline-scoring:latest .
docker push gcr.io/$PROJECT_ID/offline-scoring:latest
cd ..
echo "✅ Offline scoring image pushed"
echo ""

echo "🎉 All amd64 images built and pushed successfully!"
echo ""
echo "Next steps:"
echo "  1. Update Cloud Run services to use new images:"
echo "     gcloud run services update mlflow-server --image=gcr.io/$PROJECT_ID/mlflow-server:latest --region=us-west1 --project=$PROJECT_ID"
echo "     gcloud run services update feast-server --image=gcr.io/$PROJECT_ID/feast-server:latest --region=us-west1 --project=$PROJECT_ID"
echo "     gcloud run services update grafana-dashboard --image=gcr.io/$PROJECT_ID/grafana-server:latest --region=us-west1 --project=$PROJECT_ID"
echo ""
echo "  2. Deploy missing FastAPI service:"
echo "     deployml deploy -c deployml-config.yaml"

