"""
Step 4: Pull features from BigQuery and send prediction requests to FastAPI.
FastAPI automatically logs each prediction to the BigQuery predictions table.
"""
import os
import requests
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()

FASTAPI_URL = os.environ["FASTAPI_URL"]
PROJECT     = os.environ["BIGQUERY_PROJECT"]
DATASET     = os.getenv("BIGQUERY_DATASET", "mlops")
N_PREDICT   = 50

client  = bigquery.Client(project=PROJECT)
query   = f"""
    SELECT entity_id, bedrooms, bathrooms, area_sqft, lot_size, year_built, city, state
    FROM `{PROJECT}.{DATASET}.offline_features`
    LIMIT {N_PREDICT}
"""
rows = list(client.query(query).result())
print(f"✓ Fetched {len(rows)} rows from offline_features")

success = 0
for row in rows:
    payload = {
        "entity_id": row["entity_id"],
        "features": {
            "bedrooms":   row["bedrooms"],
            "bathrooms":  row["bathrooms"],
            "area_sqft":  row["area_sqft"],
            "lot_size":   row["lot_size"],
            "year_built": row["year_built"],
            "city":       row["city"],
            "state":      row["state"],
        }
    }
    resp = requests.post(f"{FASTAPI_URL}/predict", json=payload, timeout=10)
    if resp.status_code == 200 and resp.json().get("prediction", -1) != -1:
        success += 1

print(f"✓ {success}/{len(rows)} predictions successful")
print(f"  Predictions logged to {PROJECT}.{DATASET}.predictions by FastAPI")
