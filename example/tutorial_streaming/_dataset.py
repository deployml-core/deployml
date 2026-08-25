"""Shared synthetic housing data generator for the streaming tutorial.

Same feature distributions and formula as example/scripts/01_load_training_data.py,
factored out so 01_load_and_cutoff.py and 04_simulate_stream.py can both
regenerate the identical 500 rows (same seed) without persisting anything
to disk between script runs.
"""

import uuid
from datetime import datetime, timezone
import numpy as np

N_ROWS = 500
RANDOM_SEED = 42


def generate_rows(n_rows: int = N_ROWS, seed: int = RANDOM_SEED) -> list[dict]:
    rng = np.random.default_rng(seed)

    cities = list(range(5))  # 0-4 representing 5 cities
    states = list(range(3))  # 0-2 representing 3 states

    bedrooms = rng.integers(1, 6, n_rows).astype(float)
    bathrooms = rng.integers(1, 4, n_rows).astype(float)
    area_sqft = rng.integers(800, 4000, n_rows).astype(float)
    lot_size = rng.integers(2000, 10000, n_rows).astype(float)
    year_built = rng.integers(1960, 2023, n_rows).astype(float)
    city = rng.choice(cities, n_rows).astype(float)
    state = rng.choice(states, n_rows).astype(float)

    now = datetime.now(timezone.utc)
    return [
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
        for i in range(n_rows)
    ]


def split_into_batches(rows: list, n_batches: int) -> list[list]:
    """Split rows into n_batches near-equal chunks, covering every row exactly once."""
    return [list(batch) for batch in np.array_split(rows, n_batches)]
