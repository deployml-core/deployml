"""
Step 1: Generate the synthetic housing dataset and load only the first
TRAIN_CUTOFF_FRACTION of it into BigQuery offline_features, holding the rest
back to be streamed in later by 04_simulate_stream.py.

Assumes a fresh mlops dataset (see README.md).
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from google.cloud import bigquery

from _dataset import generate_rows, N_ROWS

load_dotenv(Path.cwd() / ".env")

PROJECT = os.environ.get("BIGQUERY_PROJECT")
if not PROJECT:
    raise SystemExit(
        "BIGQUERY_PROJECT is not set. Run `deployml get-urls` after `deployml deploy` to write a .env "
        "with BIGQUERY_PROJECT, MLFLOW_URL, and others. Then re-run this script from the same directory."
    )
DATASET = os.getenv("BIGQUERY_DATASET", "mlops")
TABLE = f"{PROJECT}.{DATASET}.offline_features"
TRAIN_CUTOFF_FRACTION = 0.4

rows = generate_rows()
cutoff = int(N_ROWS * TRAIN_CUTOFF_FRACTION)
train_rows = rows[:cutoff]

client = bigquery.Client(project=PROJECT)
errors = client.insert_rows_json(TABLE, train_rows)

if errors:
    print(f"Errors inserting rows: {errors}")
else:
    print(f"✓ Loaded {len(train_rows)}/{N_ROWS} rows into {TABLE} (initial training cutoff)")
    print(f"  {N_ROWS - cutoff} rows held back for 04_simulate_stream.py")
