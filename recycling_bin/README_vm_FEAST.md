# Feast Feature Store Setup and Data Upload Guide

This README documents the complete process of setting up a Feast feature store on a Google Cloud VM and successfully uploading a parquet file (`house_data.parquet`) to it.

## Overview

We successfully deployed a Feast feature store on a GCP VM with:
- **PostgreSQL registry and online store** (Cloud SQL)
- **BigQuery offline store** (dataset + table)
- **House sales records** loaded and materialized
- **Features**: price, city, state, bedrooms, bathrooms, area_sqft, lot_size, year_built, days_on_market, property_type, listing_agent, status, zipcode_encoded

## Prerequisites

- GCP VM instance running (`mlflow-postgres-vm-instance`)
- Docker and Docker Compose installed on the VM
- Feast server running in a Docker container
- PostgreSQL database accessible (Cloud SQL instance)
- Parquet file (`house_data.parquet`) with house sales data

## Step-by-Step Process

### .1 If Using CloudSQL Backend

1. Navigate to Cloud SQL Instances : In the Google Cloud console, go to the Cloud SQL Instances page.
2. Select your instance : Click on the name of the Cloud SQL instance you want to modify. This will take you to its Overview page.
3. Edit the instance : Click the "Edit" button at the top of the instance's Overview page.
4. Find the "Flags and parameters" section : Scroll down the configuration options until you find the "Flags and parameters" section under "Advanced options."
5. Add or modify the max_connections flag :
   - If the max_connections flag is not already listed, click "Add a database flag."
   - From the dropdown menu, select max_connections.
   - Set max_connections to 20.
6. Save changes : Click "Save" at the bottom of the page to apply your changes.

### 1. Initial Setup and Troubleshooting

#### 1.1 Prepare data in BigQuery
```bash
# Load parquet into BigQuery table
bq --project_id=<project_name> --location=us-west2 load \
  --source_format=PARQUET \
  <project_name>:feast_offline_store.house_data /path/to/house_data.parquet
```

#### 1.2 Connect to the VM
```bash
gcloud compute ssh --zone us-west2-a mlflow-postgres-vm-instance
```

#### 1.3 Check Running Containers
```bash
sudo docker ps
# Look for feast-server container
```

### 2. Feast Configuration

#### 2.1 Create Feature Store Configuration
Create `feature_store.yaml` for BigQuery offline store. Choose ONE registry option below.

Option A) SQL registry (PostgreSQL/Cloud SQL):
```yaml
project: house_sales
provider: gcp
registry:
  registry_type: sql
  path: postgresql+psycopg://feast:<PASSWORD>@<POSTGRES_IP>:5432/feast
  cache_ttl_seconds: 60
  sqlalchemy_config_kwargs:
    echo: false
    pool_pre_ping: true
online_store:
  type: postgres
  host: <POSTGRES_IP>
  port: 5432
  database: feast
  user: feast
  password: <PASSWORD>
offline_store:
  type: bigquery
  project_id: <PROJECT_ID>
  dataset: feast_offline_store
entity_key_serialization_version: 3
```

Option B) File registry (no SQL connections):
```yaml
project: house_sales
provider: gcp
registry:
  registry_type: file
  path: data/registry.db
online_store:
  type: postgres
  host: <POSTGRES_IP>
  port: 5432
  database: feast
  user: feast
  password: <PASSWORD>
offline_store:
  type: bigquery
  project_id: <PROJECT_ID>
  dataset: feast_offline_store
entity_key_serialization_version: 3
```

**Key Points:**
- Use the Cloud SQL IP for `<POSTGRES_IP>` (not localhost) when using SQL registry/online store.
- Offline store is BigQuery; set `<PROJECT_ID>` and ensure `feast_offline_store` dataset exists.
- File registry avoids Cloud SQL connection limits during `feast apply`.

#### 2.2 Copy Configuration to Container
```bash
# Copy config to the Feast container
docker cp feature_store.yaml feast-server:/app/feature_repo/feature_store.yaml
docker cp feature_store.yaml feast-server:/app/feature_store.yaml
```

### 3. Feature Definitions

**⚠️ IMPORTANT: Create these files on the HOST VM first, then copy them to the container**

#### 3.1 Create Entity Definition (`entities.py`)
Create this file on the VM (e.g., in your working directory):
```python
from feast import Entity, ValueType

house_entity = Entity(
    name="mls_id",
    value_type=ValueType.INT64,
    description="Unique identifier for a house",
    join_keys=["mls_id"]  # This matches your parquet column
)
```

#### 3.2 Create Data Source (`data_sources.py`)
Create this file on the VM (BigQuery source with only `timestamp_field`):
```python
from feast import BigQuerySource

house_source = BigQuerySource(
    table="<PROJECT_ID>.feast_offline_store.house_data",
    timestamp_field="event_timestamp",  # set to your actual timestamp column
    # created_timestamp_column="created            # optional; if multiple entries are entered for a row-tntity event
)
```

#### 3.3 Create Feature View (`house_features.py`)
Create this file on the VM (fields must match your BigQuery table columns exactly):
```python
from datetime import timedelta
from feast import FeatureView, Field
from feast.types import Float64, Int64
from feature_repo.entities import house_entity
from feature_repo.data_sources import house_source

house_features = FeatureView(
    name="house_features",
    entities=[house_entity],
    ttl=timedelta(weeks=52),
    schema=[
        Field(name="price", dtype=Float64),
        Field(name="city", dtype=Int64),
        Field(name="state", dtype=Int64),
        Field(name="bedrooms", dtype=Int64),
        Field(name="bathrooms", dtype=Int64),
        Field(name="area_sqft", dtype=Int64),
        Field(name="lot_size", dtype=Int64),
        Field(name="year_built", dtype=Int64),
        Field(name="days_on_market", dtype=Int64),
        Field(name="property_type", dtype=Int64),
        Field(name="listing_agent", dtype=Int64),
        Field(name="status", dtype=Int64),
        Field(name="zipcode_encoded", dtype=Float64),
    ],
    source=house_source,
    tags={"team": "house_sales"},
)
```

**⚠️ IMPORTANT: Repo layout and imports**
- Container path: `/app/feature_repo`
- Place `entities.py` and `data_sources.py` at repo root; place `house_features.py` under `/app/feature_repo/features/`.
- Keep these imports in `features/house_features.py` (absolute from repo root):
  - `from entities import house_entity`
  - `from data_sources import house_source`

#### 3.4 Move Feature Files to the Container
After creating the files on the VM, move them into the Feast container with the expected layout and ensure packages are initialized. The deploy now scaffolds `__init__.py` files automatically, but these commands are provided for manual updates:

```bash
# Create directories and package markers
docker exec -it feast-server mkdir -p /app/feature_repo/features
docker exec -it feast-server sh -lc 'touch /app/feature_repo/__init__.py /app/feature_repo/features/__init__.py'

# Copy files to the correct locations
docker cp entities.py       feast-server:/app/feature_repo/entities.py
docker cp data_sources.py   feast-server:/app/feature_repo/data_sources.py
docker cp house_features.py feast-server:/app/feature_repo/features/house_features.py

# Verify
docker exec -it feast-server ls -la /app/feature_repo/
docker exec -it feast-server ls -la /app/feature_repo/features/

# Optional: Remove the original files from the VM since they're now in the container
rm entities.py data_sources.py house_features.py
```

**Key Points:**
- **Entity join key** must match your data column (`mls_id`)
- **Schema fields** must match your parquet columns exactly
- **Data source path** must be accessible from within the container

### 4. Deploy Features

#### 4.1 Apply Feature Definitions
```bash
docker exec -it feast-server feast apply
```

**Expected Output:**
```
Applying changes for project house_sales
Deploying infrastructure for house_features
```

#### 4.2 Verify Registration
```bash
# List projects
docker exec -it feast-server feast projects list

# List entities
docker exec -it feast-server feast entities list

# List features
docker exec -it feast-server feast features list

# List data sources
docker exec -it feast-server feast data-sources list
```

### 5. Data Materialization
#### 5.1 Materialize Data to Online Store
```bash
docker exec -it feast-server feast materialize \
  --views house_features \
  2017-06-04T00:00:00 2025-08-20T23:59:59
```

**⚠️ CRITICAL: Use the ACTUAL timestamp range from your data!**

**Expected Output:**
```
Materializing 1 feature views from 2017-06-04 00:00:00+00:00 to 2025-08-20 23:59:59+00:00 into the postgres online store.

house_features:
100%|███████████████████████████████████████████████████████████| 3000+/3000+ [00:XX<00:00, XXX.XXit/s]
```

**Why This Matters:**
- **Wrong range** (e.g., 2024-01-01 to 2024-12-31): No data loaded, results in `null` values
- **Correct range** (e.g., 2017-06-04 to 2025-08-20): All data loaded, features return actual values
- **Check your data**: Use `df["event_timestamp"].min()` and `df["event_timestamp"].max()` to find the actual range

### 6. Query Features

#### 6.1 Get Online Features
```bash
docker exec -it feast-server feast get-online-features \
  --features house_features:price \
  --entities mls_id=112914
```

**Expected Output:**
```json
{
    "mls_id": [112914],
    "price": [843750]
}
```

#### 6.2 Get Multiple Features
```bash
docker exec -it feast-server python -c "
from feast import FeatureStore
store = FeatureStore('/app/feature_repo')

# Get multiple features
features = store.get_online_features(
    features=['house_features:price', 'house_features:bedrooms', 'house_features:bathrooms'],
    entity_rows=[{'mls_id': 112914}]
)
print('Features retrieved successfully:')
print(features.to_dict())
"
```

**Expected Output:**
```json
{
    "mls_id": [112914],
    "bedrooms": [1],
    "price": [843750.0],
    "bathrooms": [3.0]
}
```

### 7. Troubleshooting

- BigQuery table not found:
  - Ensure dataset and table exist: `bq ls --project_id=hatchet16 --location=us-west2 feast_offline_store`
  - Load data: `bq load --source_format=PARQUET hatchet16:feast_offline_store.house_data /path/to/house_data.parquet`
- Column errors (e.g., `created` not found):
  - Remove `created_timestamp_column` from `BigQuerySource` or point to a real column.
- Registry tips:
  - If Cloud SQL connections are tight, switch to file registry (`registry_type: file`, `path: data/registry.db`).
  - After a successful `feast apply`, restart the Feast server if changes don’t appear immediately.
- Credentials issue:
  - Do not set `GOOGLE_APPLICATION_CREDENTIALS` inside the container; rely on VM service account.