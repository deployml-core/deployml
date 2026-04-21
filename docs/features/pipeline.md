# MLOps Pipeline

deployml provisions a complete end-to-end MLOps pipeline on GCP. Here's how the components fit together.

## Architecture

```
                        ┌─────────────────────────────────────────────┐
                        │                   GCP (Cloud Run)            │
                        │                                              │
  Your Code ──────────▶ │  MLflow          FastAPI         Grafana     │
  (training,            │  (tracking +     (model          (monitoring │
   serving,             │   registry +     serving)        dashboard)  │
   monitoring)          │   artifacts)                                  │
                        │       │               │               │       │
                        │       ▼               ▼               ▼       │
                        │  Cloud SQL       BigQuery          BigQuery   │
                        │  (Postgres)      mlops dataset     metrics DB │
                        └─────────────────────────────────────────────┘
```

## Components

### MLflow
Handles experiment tracking, artifact storage, and model registry. All three share a single Cloud Run service backed by Cloud SQL for metadata and a GCS bucket for model files.

- Log experiments and compare runs
- Store model artifacts in GCS
- Register and version models
- Promote models through stages (Staging → Production)

### FastAPI
Serves predictions from the latest registered model in MLflow. Pulls the model on startup — no redeployment needed when you register a new model version.

- `GET /health` — health check
- `POST /predict` — run inference

### Grafana
Monitoring dashboard connected to the `metrics` Postgres database. Use it to visualize model performance, drift metrics, and prediction volume over time.

### BigQuery (`mlops` dataset)

Four tables are created automatically on deploy:

| Table | What goes in it |
|---|---|
| `offline_features` | Precomputed features used for training and serving |
| `predictions` | Model outputs logged when FastAPI serves a request |
| `ground_truth` | Actual outcomes matched back to predictions by ID |
| `drift_metrics` | Aggregated statistics for tracking model drift |

## Data Flow

```
Raw data
   │
   ▼
offline_features (BigQuery)
   │
   ├──▶ Training script ──▶ MLflow (log experiment) ──▶ Model Registry
   │
   └──▶ FastAPI (serve) ──▶ predictions (BigQuery)
                                    │
              ground_truth (BigQuery)┘
                                    │
                                    ▼
                          drift_metrics (BigQuery)
                                    │
                                    ▼
                              Grafana dashboard
```
