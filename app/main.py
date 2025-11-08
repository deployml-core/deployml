from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import mlflow
import os
from typing import List, Optional

app = FastAPI(title="Model Serving API")

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

loaded_model = None

class PredictionRequest(BaseModel):
    features: List[float]

class HealthResponse(BaseModel):
    status: str
    mlflow_connected: bool
    model_loaded: bool

@app.get("/health", response_model=HealthResponse)
async def health_check():
    mlflow_connected = False
    try:
        client = mlflow.tracking.MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
        client.search_experiments(max_results=1)
        mlflow_connected = True
    except:
        pass
    
    return HealthResponse(
        status="healthy",
        mlflow_connected=mlflow_connected,
        model_loaded=loaded_model is not None
    )

@app.post("/model/load")
async def load_model(model_name: str, version: str = "latest"):
    global loaded_model
    try:
        model_uri = f"models:/{model_name}/{version}"
        loaded_model = mlflow.pyfunc.load_model(model_uri)
        return {"status": "success", "model_uri": model_uri}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/predict")
async def predict(request: PredictionRequest):
    if loaded_model is None:
        raise HTTPException(status_code=400, detail="No model loaded")
    
    try:
        import pandas as pd
        input_data = pd.DataFrame([request.features])
        prediction = loaded_model.predict(input_data)
        return {"prediction": prediction.tolist()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

