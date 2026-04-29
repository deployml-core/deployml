"""
Step 5: Generate fake ground truth values for each prediction and store in BigQuery.
In production this would be real outcomes (e.g. actual sale price) matched back to predictions.
"""
import os
import numpy as np
from datetime import datetime, timezone
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()

PROJECT = os.environ["BIGQUERY_PROJECT"]
DATASET = os.getenv("BIGQUERY_DATASET", "mlops")
NOISE   = 15000  # std dev of fake noise around predicted value

client = bigquery.Client(project=PROJECT)

query = f"""
    SELECT entity_id, predicted_value, prediction_timestamp
    FROM `{PROJECT}.{DATASET}.predictions`
    ORDER BY prediction_timestamp DESC
"""
predictions = list(client.query(query).result())
print(f"✓ Found {len(predictions)} predictions to generate ground truth for")

np.random.seed(0)
now  = datetime.now(timezone.utc)
rows = [
    {
        "entity_id":       row["entity_id"],
        "event_timestamp": now.isoformat(),
        "actual_value":    float(row["predicted_value"]) + np.random.normal(0, NOISE),
    }
    for row in predictions
]

errors = client.insert_rows_json(f"{PROJECT}.{DATASET}.ground_truth", rows)
if errors:
    print(f"Errors: {errors}")
else:
    print(f"✓ Wrote {len(rows)} rows to {PROJECT}.{DATASET}.ground_truth")
