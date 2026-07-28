"""
Step 7: Provision a Grafana model monitoring dashboard via the Grafana HTTP API.

The dashboard shows:
- Prediction volume over time
- Mean predicted value over time
- Feature mean shift per feature
- MAE over time

Prerequisites: Grafana must be running and accessible at GRAFANA_URL.
Auth: the admin password lives in Secret Manager. This script fetches it via
gcloud using GRAFANA_ADMIN_PASSWORD_SECRET_ID from .env (run `deployml get-urls`).
Override by exporting GRAFANA_PASSWORD if you prefer.
"""

import os
import subprocess
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path.cwd() / ".env")

GRAFANA_URL = os.environ.get("GRAFANA_URL")
PROJECT = os.environ.get("BIGQUERY_PROJECT")
if not GRAFANA_URL or not PROJECT:
    raise SystemExit(
        "GRAFANA_URL or BIGQUERY_PROJECT missing. Run `deployml get-urls` to write .env."
    )
GRAFANA_URL = GRAFANA_URL.rstrip("/")
DATASET = os.getenv("BIGQUERY_DATASET", "mlops")
GRAFANA_USER = os.getenv("GRAFANA_USER", "admin")

GRAFANA_PASS = os.getenv("GRAFANA_PASSWORD")
if not GRAFANA_PASS:
    secret_id = os.environ.get("GRAFANA_ADMIN_PASSWORD_SECRET_ID")
    if not secret_id:
        raise SystemExit(
            "Grafana password not available. Either export GRAFANA_PASSWORD, "
            "or run `deployml get-urls` so .env has GRAFANA_ADMIN_PASSWORD_SECRET_ID."
        )
    proc = subprocess.run(
        [
            "gcloud",
            "secrets",
            "versions",
            "access",
            "latest",
            "--secret",
            secret_id,
            "--project",
            PROJECT,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"Failed to fetch Grafana password: {proc.stderr.strip()}")
    GRAFANA_PASS = proc.stdout.strip()

session = requests.Session()
session.auth = (GRAFANA_USER, GRAFANA_PASS)


def get_or_create_bigquery_datasource():
    """Return the UID of the BigQuery datasource, creating it if needed."""
    resp = session.get(f"{GRAFANA_URL}/api/datasources/name/BigQuery")
    if resp.status_code == 200:
        uid = resp.json()["uid"]
        print(f"✓ Using existing BigQuery datasource (uid={uid})")
        return uid

    payload = {
        "name": "BigQuery",
        "type": "grafana-bigquery-datasource",
        "access": "proxy",
        "jsonData": {
            "authenticationType": "gce",
            "defaultProject": PROJECT,
        },
    }
    resp = session.post(f"{GRAFANA_URL}/api/datasources", json=payload)
    resp.raise_for_status()
    uid = resp.json()["datasource"]["uid"]
    print(f"✓ Created BigQuery datasource (uid={uid})")
    return uid


def build_dashboard(ds_uid: str) -> dict:
    def bq_target(sql: str, ref: str) -> dict:
        return {
            "datasource": {"type": "grafana-bigquery-datasource", "uid": ds_uid},
            "rawQuery": True,
            "rawSql": sql,
            "refId": ref,
            "format": "time_series",
        }

    predictions_sql = f"""
SELECT prediction_timestamp AS time, COUNT(*) AS prediction_count
FROM `{PROJECT}.{DATASET}.predictions`
GROUP BY time ORDER BY time
""".strip()

    mean_pred_sql = f"""
SELECT prediction_timestamp AS time, AVG(predicted_value) AS mean_prediction
FROM `{PROJECT}.{DATASET}.predictions`
GROUP BY time ORDER BY time
""".strip()

    drift_sql = f"""
SELECT metric_timestamp AS time, feature_name, value AS mean_shift
FROM `{PROJECT}.{DATASET}.drift_metrics`
WHERE metric_type = 'feature_mean_shift'
ORDER BY time
""".strip()

    mae_sql = f"""
SELECT metric_timestamp AS time, value AS mae
FROM `{PROJECT}.{DATASET}.drift_metrics`
WHERE metric_type = 'mae'
ORDER BY time
""".strip()

    panels = [
        {
            "id": 1,
            "title": "Prediction Volume",
            "type": "timeseries",
            "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
            "targets": [bq_target(predictions_sql, "A")],
        },
        {
            "id": 2,
            "title": "Mean Predicted Price",
            "type": "timeseries",
            "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8},
            "targets": [bq_target(mean_pred_sql, "A")],
        },
        {
            "id": 3,
            "title": "Feature Mean Shift",
            "type": "timeseries",
            "gridPos": {"x": 0, "y": 8, "w": 12, "h": 8},
            "targets": [bq_target(drift_sql, "A")],
        },
        {
            "id": 4,
            "title": "MAE (Predictions vs Ground Truth)",
            "type": "timeseries",
            "gridPos": {"x": 12, "y": 8, "w": 12, "h": 8},
            "targets": [bq_target(mae_sql, "A")],
        },
    ]

    return {
        "dashboard": {
            "title": "Housing Price Model Monitoring",
            "tags": ["mlops", "deployml"],
            "timezone": "browser",
            "panels": panels,
            "schemaVersion": 36,
            "version": 1,
        },
        "overwrite": True,
        "folderId": 0,
    }


ds_uid = get_or_create_bigquery_datasource()
dashboard = build_dashboard(ds_uid)

resp = session.post(f"{GRAFANA_URL}/api/dashboards/db", json=dashboard)
resp.raise_for_status()
slug = resp.json().get("slug", "")
print(f"✓ Dashboard created: {GRAFANA_URL}/d/{resp.json().get('uid')}")
