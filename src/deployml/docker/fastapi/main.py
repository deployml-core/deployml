from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Optional
import os
import uuid
from datetime import datetime, timezone
import pandas as pd
import mlflow
import mlflow.pyfunc

app = FastAPI(
    title="FastAPI Demo",
    description="Simple FastAPI application for Kubernetes deployment demo",
    version="1.0.0",
)

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow-service:5000")
MODEL_NAME = os.getenv("MODEL_NAME", "HousingPriceModel")
BIGQUERY_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
BIGQUERY_DATASET = os.getenv("BIGQUERY_DATASET", "mlops")

model = None
bq_client = None

FEATURE_ORDER = [
    "bedrooms",
    "bathrooms",
    "area_sqft",
    "lot_size",
    "year_built",
    "city",
    "state",
]


class PredictionRequest(BaseModel):
    entity_id: Optional[str] = None
    features: Dict[str, float]


class PredictionResponse(BaseModel):
    prediction: float
    timestamp: str
    model_used: Optional[str] = None
    entity_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    port: int
    mlflow_connected: bool
    model_loaded: bool


def load_model_from_mlflow():
    global model
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/Production")
        print(f"✓ Loaded model '{MODEL_NAME}' from Production stage")
        return True
    except Exception as e:
        print(f"⚠️  Could not load model from MLflow: {e}")
        model = None
        return False


def init_bigquery():
    global bq_client
    if not BIGQUERY_PROJECT:
        return
    try:
        from google.cloud import bigquery

        bq_client = bigquery.Client(project=BIGQUERY_PROJECT)
        print(f"✓ BigQuery client initialized for project {BIGQUERY_PROJECT}")
    except Exception as e:
        print(f"⚠️  Could not initialize BigQuery client: {e}")
        bq_client = None


def log_prediction_to_bigquery(
    entity_id: str, predicted_value: float, model_version: str
):
    if bq_client is None:
        return
    try:
        table_id = f"{BIGQUERY_PROJECT}.{BIGQUERY_DATASET}.predictions"
        row = {
            "prediction_id": str(uuid.uuid4()),
            "entity_id": entity_id,
            "prediction_timestamp": datetime.now(timezone.utc).isoformat(),
            "predicted_value": predicted_value,
            "model_version": model_version,
            "feature_snapshot_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        bq_client.insert_rows_json(table_id, [row])
    except Exception as e:
        print(f"⚠️  Could not log prediction to BigQuery: {e}")


async def _model_load_retry_loop():
    """Retry loading the model until it succeeds. Earlier code attempted
    the load once at startup; if MLflow was unavailable then, the model
    stayed None forever even after MLflow recovered."""
    import asyncio

    retry_interval = 30
    while model is None:
        ok = await asyncio.to_thread(load_model_from_mlflow)
        if ok:
            return
        await asyncio.sleep(retry_interval)


@app.on_event("startup")
async def startup_event():
    # Init BigQuery synchronously. Cheap, returns immediately if no project.
    init_bigquery()
    # Load the model in a background task with retry so startup completes fast
    # AND we keep trying if MLflow was unreachable at first.
    import asyncio

    asyncio.create_task(_model_load_retry_loop())


@app.get("/")
async def root():
    return {
        "service": "FastAPI Demo",
        "version": "1.0.0",
        "model_loaded": model is not None,
        "model_name": MODEL_NAME,
        "mlflow_uri": MLFLOW_TRACKING_URI,
        "endpoints": {"health": "/health", "predict": "/predict", "docs": "/docs"},
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    port = int(os.getenv("PORT", "8000"))
    # Actually probe MLflow. Earlier code returned mlflow_connected=True
    # hardcoded, which lied to users when MLflow was down.
    mlflow_ok = False
    try:
        import requests as _rq

        resp = _rq.get(f"{MLFLOW_TRACKING_URI.rstrip('/')}/health", timeout=2)
        mlflow_ok = resp.status_code == 200
    except Exception:
        mlflow_ok = False
    return HealthResponse(
        status="healthy" if mlflow_ok else "degraded",
        timestamp=datetime.now(timezone.utc).isoformat(),
        port=port,
        mlflow_connected=mlflow_ok,
        model_loaded=model is not None,
    )


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    global model

    entity_id = request.entity_id or str(uuid.uuid4())

    # Do not lazy-load synchronously here. mlflow.pyfunc.load_model can hang
    # for many seconds when MLflow is unreachable, blocking the request worker.
    # The background loader started in startup_event handles loading. If the
    # model is not yet loaded, return 503 fast.
    if model is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": "Model not available yet. MLflow may be unreachable or no model is registered in Production stage. Retry shortly.",
                "entity_id": entity_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    try:
        feature_values = [request.features.get(f, 0.0) for f in FEATURE_ORDER]
        X = pd.DataFrame([feature_values], columns=FEATURE_ORDER)

        prediction = float(model.predict(X)[0])
        model_version = f"MLflow: {MODEL_NAME}"

        log_prediction_to_bigquery(entity_id, prediction, model_version)

        return PredictionResponse(
            prediction=prediction,
            timestamp=datetime.now(timezone.utc).isoformat(),
            model_used=model_version,
            entity_id=entity_id,
        )
    except Exception as e:
        # Earlier code returned prediction=-1.0 with HTTP 200 and no message,
        # which silently hid model errors. Now we return 500 with the cause.
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Prediction failed: {type(e).__name__}: {e}",
                "entity_id": entity_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
