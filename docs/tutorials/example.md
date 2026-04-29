# End-to-End MLOps Example

This example walks through a complete MLOps workflow using a synthetic housing price dataset. By the end you will have a model trained and registered in MLflow, served via FastAPI, and monitored in Grafana with BigQuery as the data backend.

## Prerequisites

1. Deploy the infrastructure following the [GCP Cloud Run tutorial](gcp-cloud-run.md)
2. Run `deployml get-urls` to generate your `.env` file
3. Install Python dependencies:

```bash
pip install mlflow scikit-learn pandas numpy google-cloud-bigquery db-dtypes python-dotenv requests
```

## Environment

All scripts read from the `.env` file written by `deployml get-urls`. It should contain:

```
MLFLOW_URL=https://...
FASTAPI_URL=https://...
GRAFANA_URL=https://...
BIGQUERY_PROJECT=your-project-id
BIGQUERY_DATASET=mlops
```

## Scripts

Run in order from the project root (where `.env` lives):

### Step 1 — Load training data into BigQuery

```bash
python example/scripts/01_load_training_data.py
```

Generates 500 rows of synthetic housing data and loads them into the `offline_features` BigQuery table.

Verify:
```bash
bq query --use_legacy_sql=false 'SELECT COUNT(*) FROM `YOUR_PROJECT.mlops.offline_features`'
```

### Step 2 — Train a model with MLflow

```bash
python example/scripts/02_train_model.py
```

Pulls features from BigQuery, trains a RandomForestRegressor, and logs parameters, metrics, and the model artifact to MLflow.

Verify: open `MLFLOW_URL` in your browser — you should see the `housing-price-prediction` experiment with a completed run.

### Step 3 — Register the model

```bash
python example/scripts/03_register_model.py
```

Finds the best run by RMSE, registers it as `HousingPriceModel`, and promotes it to the **Production** stage.

Verify: in the MLflow UI, click **Models** → `HousingPriceModel` → Production stage should be set.

### Step 4 — Make predictions

```bash
python example/scripts/04_make_predictions.py
```

Pulls 50 rows from `offline_features` and sends each to FastAPI `/predict`. FastAPI loads the model from MLflow on startup and automatically logs each prediction to the `predictions` BigQuery table.

Verify:
```bash
bq query --use_legacy_sql=false 'SELECT COUNT(*) FROM `YOUR_PROJECT.mlops.predictions`'
```

Also check FastAPI is serving the model:
```bash
curl FASTAPI_URL/health
# model_loaded should be true
```

### Step 5 — Generate ground truth

```bash
python example/scripts/05_generate_ground_truth.py
```

For each prediction, generates a fake actual value (predicted value + noise) and writes it to the `ground_truth` table. In a real scenario this would be actual outcomes matched back by `entity_id`.

### Step 6 — Compute drift metrics

```bash
python example/scripts/06_compute_drift_metrics.py
```

Computes feature mean shift (training distribution vs recent data) and MAE (predictions vs ground truth). Writes results to the `drift_metrics` table.

### Step 7 — Set up Grafana dashboard

```bash
python example/scripts/07_setup_grafana.py
```

Provisions a monitoring dashboard in Grafana via the API showing:
- Prediction volume over time
- Mean predicted price over time
- Feature mean shift per feature
- MAE over time

Open `GRAFANA_URL` in your browser (login: `admin` / `admin`) to view the dashboard.

## Dataset

Synthetic housing data with features:

| Feature | Description |
|---|---|
| `bedrooms` | Number of bedrooms (1–5) |
| `bathrooms` | Number of bathrooms (1–3) |
| `area_sqft` | Living area in square feet (800–4000) |
| `lot_size` | Lot size in square feet (2000–10000) |
| `year_built` | Year the house was built (1960–2022) |
| `city` | City encoded as integer (0–4) |
| `state` | State encoded as integer (0–2) |

Target: `price` = `area_sqft * 200 + bedrooms * 15000 + bathrooms * 10000 + (2023 - year_built) * -500 + noise`
