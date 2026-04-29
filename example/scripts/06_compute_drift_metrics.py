"""
Step 6: Compute drift metrics and MAE, store in BigQuery drift_metrics table.

Metrics computed:
- feature_mean_shift: difference between training mean and recent prediction mean per feature
- mae: mean absolute error between predictions and ground truth
"""
import os
import numpy as np
from datetime import datetime, timezone
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()

PROJECT      = os.environ["BIGQUERY_PROJECT"]
DATASET      = os.getenv("BIGQUERY_DATASET", "mlops")
FEATURE_COLS = ["bedrooms", "bathrooms", "area_sqft", "lot_size", "year_built", "city", "state"]

client = bigquery.Client(project=PROJECT)

# Training feature distributions (baseline)
train_query = f"SELECT {', '.join(FEATURE_COLS)} FROM `{PROJECT}.{DATASET}.offline_features`"
train_df    = client.query(train_query).to_dataframe()

# Recent predictions (simulate "serving" features by using training data subset as proxy)
# In production you'd log features alongside predictions and query those
recent_query = f"""
    SELECT {', '.join(FEATURE_COLS)}
    FROM `{PROJECT}.{DATASET}.offline_features`
    ORDER BY event_timestamp DESC
    LIMIT 50
"""
recent_df = client.query(recent_query).to_dataframe()

# MAE from ground truth vs predictions
mae_query = f"""
    SELECT p.predicted_value, g.actual_value
    FROM `{PROJECT}.{DATASET}.predictions` p
    JOIN `{PROJECT}.{DATASET}.ground_truth` g USING (entity_id)
"""
mae_df = client.query(mae_query).to_dataframe()

now        = datetime.now(timezone.utc)
window_end = now
window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
rows = []

# Feature mean shift per feature
for col in FEATURE_COLS:
    shift = float(recent_df[col].mean() - train_df[col].mean())
    rows.append({
        "metric_timestamp": now.isoformat(),
        "metric_type":      "feature_mean_shift",
        "feature_name":     col,
        "value":            shift,
        "window_start":     window_start.isoformat(),
        "window_end":       window_end.isoformat(),
        "model_version":    "HousingPriceModel/Production",
    })

# MAE
if len(mae_df) > 0:
    mae = float(np.mean(np.abs(mae_df["predicted_value"] - mae_df["actual_value"])))
    rows.append({
        "metric_timestamp": now.isoformat(),
        "metric_type":      "mae",
        "feature_name":     None,
        "value":            mae,
        "window_start":     window_start.isoformat(),
        "window_end":       window_end.isoformat(),
        "model_version":    "HousingPriceModel/Production",
    })
    print(f"  MAE: {mae:.2f}")

errors = client.insert_rows_json(f"{PROJECT}.{DATASET}.drift_metrics", rows)
if errors:
    print(f"Errors: {errors}")
else:
    print(f"✓ Wrote {len(rows)} drift metric rows to {PROJECT}.{DATASET}.drift_metrics")
