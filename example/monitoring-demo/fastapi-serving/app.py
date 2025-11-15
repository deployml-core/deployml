"""
Simple FastAPI app for serving house price predictions
"""
import os
import json
from datetime import datetime
from typing import List
import pandas as pd
import mlflow
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="House Price API")

# Global model variable
model = None
model_version = "1"

# Request/Response models
class HouseFeatures(BaseModel):
    bedrooms: int
    bathrooms: int
    sqft: int
    age: int

class PredictionResult(BaseModel):
    price: float
    model_version: str

# Simple prediction log (in-memory for simplicity)
prediction_history = []

@app.on_event("startup")
async def load_model():
    """Load model when app starts"""
    global model, model_version
    
    try:
        # Connect to MLflow
        mlflow_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000')
        mlflow.set_tracking_uri(mlflow_uri)
        
        # Load latest model
        model = mlflow.sklearn.load_model("models:/house-price-model/latest")
        model_version = "latest"
        print(f"✅ Model loaded successfully")
    except Exception as e:
        print(f"⚠️ Could not load model: {e}")
        print("Using fallback formula instead")

@app.get("/")
async def home():
    """Basic info endpoint"""
    return {
        "service": "House Price Prediction",
        "model_loaded": model is not None,
        "predictions_made": len(prediction_history)
    }

@app.post("/predict")
async def predict(house: HouseFeatures) -> PredictionResult:
    """Make a single prediction"""
    
    # Fail if no model is loaded
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded. Train and register a model in MLflow first."
        )
    
    # Convert to DataFrame for model
    features = pd.DataFrame([{
        'bedrooms': house.bedrooms,
        'bathrooms': house.bathrooms,
        'sqft': house.sqft,
        'age': house.age
    }])
    
    # Predict using loaded model
    price = float(model.predict(features)[0])
    
    # Log prediction (simple in-memory storage)
    prediction_history.append({
        "timestamp": datetime.now().isoformat(),
        "features": house.dict(),
        "prediction": price
    })
    
    # Keep only last 100 predictions in memory
    if len(prediction_history) > 100:
        prediction_history.pop(0)
    
    return PredictionResult(
        price=round(price, 2),
        model_version=model_version
    )

@app.post("/predict/batch")
async def predict_batch(houses: List[HouseFeatures]) -> dict:
    """Make multiple predictions"""
    results = []
    for house in houses:
        result = await predict(house)
        results.append(result.price)
    
    return {
        "predictions": results,
        "count": len(results)
    }

@app.get("/stats")
async def get_stats():
    """Get simple statistics"""
    if not prediction_history:
        return {"message": "No predictions yet"}
    
    prices = [p["prediction"] for p in prediction_history]
    return {
        "total_predictions": len(prediction_history),
        "average_price": round(sum(prices) / len(prices), 2),
        "min_price": round(min(prices), 2),
        "max_price": round(max(prices), 2),
        "last_prediction": prediction_history[-1]["timestamp"]
    }

@app.get("/history")
async def get_history(limit: int = 10):
    """Get recent predictions"""
    return prediction_history[-limit:]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)