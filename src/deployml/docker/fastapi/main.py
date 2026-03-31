from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os
from datetime import datetime
import pandas as pd
import mlflow
import mlflow.pyfunc

app = FastAPI(
    title="FastAPI Demo",
    description="Simple FastAPI application for Kubernetes deployment demo",
    version="1.0.0"
)

# Hardcoded MLflow configuration
MLFLOW_TRACKING_URI = "http://mlflow-service:5000"
MODEL_NAME = "HousingPriceModel"

# Global model variable
model = None

# Pydantic models
class PredictionRequest(BaseModel):
    features: Dict[str, float]

class PredictionResponse(BaseModel):
    prediction: float
    timestamp: str
    model_used: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    port: int
    mlflow_connected: bool
    model_loaded: bool

def load_model_from_mlflow():
    """Load model from MLflow Model Registry"""
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

# Load model at startup
@app.on_event("startup")
async def startup_event():
    """Load MLflow model on startup"""
    load_model_from_mlflow()

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "FastAPI Demo",
        "version": "1.0.0",
        "model_loaded": model is not None,
        "model_name": MODEL_NAME,
        "mlflow_uri": MLFLOW_TRACKING_URI,
        "endpoints": {
            "health": "/health",
            "predict": "/predict",
            "docs": "/docs"
        }
    }

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    port = int(os.getenv("FASTAPI_PORT", "8000"))
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        port=port,
        mlflow_connected=True,
        model_loaded=model is not None
    )

@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    """Prediction endpoint using MLflow model"""
    global model
    
    # If model is not loaded, return -1
    if model is None:
        return PredictionResponse(
            prediction=-1.0,
            timestamp=datetime.now().isoformat(),
            model_used=None
        )
    
    try:
        # Convert features dict to DataFrame in correct order
        # Features: bedrooms, bathrooms, area_sqft, lot_size, year_built, city, state
        feature_order = ['bedrooms', 'bathrooms', 'area_sqft', 'lot_size', 'year_built', 'city', 'state']
        feature_values = [request.features.get(f, 0.0) for f in feature_order]
        X = pd.DataFrame([feature_values], columns=feature_order)
        
        prediction = float(model.predict(X)[0])
        model_used = f"MLflow: {MODEL_NAME}"
        
        return PredictionResponse(
            prediction=prediction,
            timestamp=datetime.now().isoformat(),
            model_used=model_used
        )
    except Exception as e:
        # On any error, return -1
        return PredictionResponse(
            prediction=-1.0,
            timestamp=datetime.now().isoformat(),
            model_used=None
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("FASTAPI_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)