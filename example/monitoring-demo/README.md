# 📊 DeployML Monitoring Demo

Complete end-to-end example demonstrating **online** and **offline monitoring** with DeployML.

**Project**: `mldeploy-468919`

> 📖 **See [ARCHITECTURE.md](./ARCHITECTURE.md)** for detailed diagram of what runs where (local vs cloud)

## 🎯 What's Included

- ✅ Model Training & Registration (MLflow)
- ✅ FastAPI Serving with Prediction Logging
- ✅ Drift Monitoring (PSI, KS tests)
- ✅ Offline Batch Scoring
- ✅ Grafana Dashboards
- ✅ PostgreSQL Metrics Storage

## 🚀 Quick Start

### 1. Setup GCP

```bash
gcloud config set project mldeploy-468919

# Enable APIs
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com

# Configure Docker
gcloud auth configure-docker gcr.io
```

### 2. Build & Push ALL Images

**Building everything yourself:**
- ✅ MLflow Server - Custom MLflow with PostgreSQL support
- ✅ Grafana Server - Pre-configured dashboards
- ✅ FastAPI Serving - Your model serving API
- ✅ Drift Monitoring - Drift detection script
- ✅ Offline Scoring - Batch scoring script

```bash
cd example/monitoring-demo
chmod +x build-and-push.sh
./build-and-push.sh
```

This builds and pushes **5 images** to your GCR.

### 3. Deploy with DeployML

```bash
deployml deploy deployml-config.yaml
```

This provisions:
- ☁️ Cloud SQL (PostgreSQL) with `metrics` database
- 🚀 MLflow server
- 🔥 FastAPI serving endpoint
- 📊 Grafana dashboard
- ⏰ Cloud Scheduler (drift monitoring + offline scoring)

### 4. Train & Register Model

**Important:** Training runs **locally** but connects to **deployed MLflow**

```bash
# Get MLflow URL from deployment output (something like):
# https://mlflow-server-abc123-uw.a.run.app

export MLFLOW_TRACKING_URI="https://mlflow-server-abc123-uw.a.run.app"

# Verify it's set
echo $MLFLOW_TRACKING_URI

# Run training locally, logs to deployed MLflow
cd model-training
pip install -r requirements.txt
python train.py
```

The model and metrics will be stored in your deployed MLflow server.

### 5. Test FastAPI

```bash
# Get FastAPI URL from deployment
export FASTAPI_URL="<fastapi-url>"

# Single prediction
curl -X POST "${FASTAPI_URL}/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "bedrooms": 3,
    "bathrooms": 2,
    "sqft": 2000,
    "age": 10
  }'

# Check stats
curl "${FASTAPI_URL}/stats"
```

### 6. Generate Test Traffic

```bash
chmod +x generate-traffic.sh
./generate-traffic.sh
```

### 7. Trigger Monitoring

```bash
# Drift monitoring (normally runs daily at 6 AM)
gcloud run jobs execute drift-monitoring --region=us-west1

# Offline scoring (normally runs 1st & 15th of month)
gcloud run jobs execute offline-scoring --region=us-west1
```

### 8. Access Grafana

```bash
# Get URL from deployment
open <grafana-url>

# Login: admin / admin (change on first login)
```

## 📊 Grafana Setup

### Add PostgreSQL Data Source

1. Configuration → Data Sources → Add PostgreSQL
2. Configure:
   - Host: `<cloud-sql-ip>:5432`
   - Database: `metrics`
   - User: `<db-user>`
   - Password: `<db-password>`

### Sample Queries

**Drift Over Time:**
```sql
SELECT timestamp, feature_name, drift_score
FROM drift_metrics
WHERE timestamp > NOW() - INTERVAL '7 days'
ORDER BY timestamp;
```

**Predictions Count:**
```sql
SELECT DATE_TRUNC('hour', timestamp) as hour,
       COUNT(*) as predictions,
       AVG(prediction) as avg_price
FROM prediction_logs
GROUP BY hour
ORDER BY hour;
```

**Drift Alerts:**
```sql
SELECT feature_name, drift_score, drift_detected
FROM drift_metrics
WHERE drift_detected = true
ORDER BY timestamp DESC;
```

## 🔍 The Flow

### Online Monitoring
```
Request → FastAPI → Predict → Log to DB → Return
```

### Offline Monitoring
```
Scheduler → Drift Job → Calculate Metrics → Store → Grafana
```

## 📈 Database Tables

- **prediction_logs**: Every prediction made
- **drift_metrics**: PSI/KS drift scores  
- **batch_predictions**: Offline scoring results

## 🎯 Drift Metrics

- **PSI** < 0.1: No drift
- **PSI** 0.1-0.2: Small change
- **PSI** > 0.2: ⚠️ Drift detected
- **KS p-value** < 0.05: ⚠️ Different distribution

## 🛠️ Troubleshooting

```bash
# Check logs
gcloud run services logs read house-price-api --region=us-west1

# Connect to database
gcloud sql connect <instance-name> --user=<db-user>
```

## 🧹 Cleanup

```bash
deployml destroy deployml-config.yaml
```

## 📚 Next Steps

Based on how this works, you can add:
- Explainability metrics (SHAP)
- Fairness monitoring
- Custom alerts
- Real data integration

**Now let's see how it works and improve DeployML based on your experience!** 🚀

