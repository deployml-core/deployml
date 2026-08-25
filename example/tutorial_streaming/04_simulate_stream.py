"""
Step 4: Simulate new incoming data arriving in batches. Each batch is scored
via FastAPI /predict immediately, then its ground truth is written after a
short delay, so the predictions and ground_truth tables fill in at different
times like a real stream.

ponytail: BATCH_DELAY_SECONDS is a real wall-clock sleep, not a simulated
one, so total runtime is tied to demo time. Upgrade path: write ground truth
with backdated event_timestamps instead of sleeping, so the full time series
is visible immediately regardless of how long the script takes to run.
"""

import os
import time
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import requests
from dotenv import load_dotenv
from google.cloud import bigquery

from _dataset import generate_rows, split_into_batches, N_ROWS

load_dotenv(Path.cwd() / ".env")

FASTAPI_URL = os.environ.get("FASTAPI_URL")
PROJECT = os.environ.get("BIGQUERY_PROJECT")
DATASET = os.getenv("BIGQUERY_DATASET", "mlops")
TRAIN_CUTOFF_FRACTION = 0.4
N_BATCHES = 5
BATCH_DELAY_SECONDS = 30
GROUND_TRUTH_NOISE = 15000  # std dev of fake noise around predicted value


def score_batch(batch: list[dict]) -> int:
    success = 0
    for row in batch:
        payload = {
            "entity_id": row["entity_id"],
            "features": {
                "bedrooms": row["bedrooms"],
                "bathrooms": row["bathrooms"],
                "area_sqft": row["area_sqft"],
                "lot_size": row["lot_size"],
                "year_built": row["year_built"],
                "city": row["city"],
                "state": row["state"],
            },
        }
        resp = requests.post(f"{FASTAPI_URL}/predict", json=payload, timeout=10)
        if resp.status_code == 200 and resp.json().get("prediction", -1) != -1:
            success += 1
    return success


def write_ground_truth(client: bigquery.Client, batch: list[dict]) -> None:
    entity_ids = [row["entity_id"] for row in batch]
    query = f"""
        SELECT entity_id, predicted_value
        FROM `{PROJECT}.{DATASET}.predictions`
        WHERE entity_id IN UNNEST(@entity_ids)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("entity_ids", "STRING", entity_ids)]
    )
    predictions = list(client.query(query, job_config=job_config).result())

    now = datetime.now(timezone.utc)
    rows = [
        {
            "entity_id": row["entity_id"],
            "event_timestamp": now.isoformat(),
            "actual_value": float(row["predicted_value"]) + np.random.normal(0, GROUND_TRUTH_NOISE),
        }
        for row in predictions
    ]
    errors = client.insert_rows_json(f"{PROJECT}.{DATASET}.ground_truth", rows)
    if errors:
        print(f"  Errors writing ground truth: {errors}")
    else:
        print(f"  ✓ Wrote ground truth for {len(rows)} rows")


if __name__ == "__main__":
    if not FASTAPI_URL or not PROJECT:
        raise SystemExit(
            "FASTAPI_URL or BIGQUERY_PROJECT missing. Run `deployml get-urls` to write .env."
        )

    all_rows = generate_rows()
    cutoff = int(N_ROWS * TRAIN_CUTOFF_FRACTION)
    stream_rows = all_rows[cutoff:]
    batches = split_into_batches(stream_rows, N_BATCHES)

    client = bigquery.Client(project=PROJECT)
    for i, batch in enumerate(batches, start=1):
        print(f"Batch {i}/{len(batches)}: scoring {len(batch)} rows")
        success = score_batch(batch)
        print(f"  ✓ {success}/{len(batch)} predictions successful")

        print(f"  Waiting {BATCH_DELAY_SECONDS}s before ground truth arrives...")
        time.sleep(BATCH_DELAY_SECONDS)
        write_ground_truth(client, batch)
