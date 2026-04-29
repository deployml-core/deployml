"""
Step 1: Generate synthetic housing data and load into BigQuery offline_features table.
"""
import os
import uuid
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

PROJECT = os.environ["BIGQUERY_PROJECT"]
DATASET = os.getenv("BIGQUERY_DATASET", "mlops")
TABLE = f"{PROJECT}.{DATASET}.offline_features"
N_ROWS = 500
RANDOM_SEED = 42

np.random.seed(RANDOM_SEED)

cities = list(range(5))   # 0-4 representing 5 cities
states = list(range(3))   # 0-2 representing 3 states

bedrooms   = np.random.randint(1, 6, N_ROWS).astype(float)
bathrooms  = np.random.randint(1, 4, N_ROWS).astype(float)
area_sqft  = np.random.randint(800, 4000, N_ROWS).astype(float)
lot_size   = np.random.randint(2000, 10000, N_ROWS).astype(float)
year_built = np.random.randint(1960, 2023, N_ROWS).astype(float)
city       = np.random.choice(cities, N_ROWS).astype(float)
state      = np.random.choice(states, N_ROWS).astype(float)

now = datetime.now(timezone.utc)
rows = [
    {
        "entity_id": str(uuid.uuid4()),
        "event_timestamp": now.isoformat(),
        "bedrooms": bedrooms[i],
        "bathrooms": bathrooms[i],
        "area_sqft": area_sqft[i],
        "lot_size": lot_size[i],
        "year_built": year_built[i],
        "city": city[i],
        "state": state[i],
    }
    for i in range(N_ROWS)
]

client = bigquery.Client(project=PROJECT)
errors = client.insert_rows_json(TABLE, rows)

if errors:
    print(f"Errors inserting rows: {errors}")
else:
    print(f"✓ Loaded {N_ROWS} rows into {TABLE}")
