"""
Simplified FastAPI app - loads model on every request
Features:
- Model serving from MLflow (loads fresh each request)
- PostgreSQL prediction logging
- SHAP explainability
- Always uses latest model version
"""
import os
import json
import uuid
import time
from datetime import datetime
from typing import List, Optional
import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
import shap
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="House Price API - Simple Mode")

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")
engine = None
SessionLocal = None

if DATABASE_URL:
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info("✅ Database connection established")
    except Exception as e:
        logger.error(f"❌ Failed to connect to database: {e}")
        logger.warning("⚠️  Running without database logging")
else:
    logger.warning("⚠️  DATABASE_URL not set. Running without database logging")

# Request/Response models
class HouseFeatures(BaseModel):
    bedrooms: int
    bathrooms: int
    sqft: int
    age: int

class PredictionResult(BaseModel):
    request_id: str
    price: float
    model_version: str
    explanation: Optional[dict] = None

# Helper functions
def load_model_from_mlflow():
    """Load model from MLflow - called on every request"""
    try:
        mlflow_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000')
        mlflow.set_tracking_uri(mlflow_uri)
        
        model_name = os.getenv('MODEL_NAME', 'house-price-model')
        model_stage = os.getenv('MODEL_STAGE', 'Production')
        model_uri = f"models:/{model_name}/{model_stage}"
        
        logger.info(f"📡 Loading model from {model_uri}...")
        model = mlflow.sklearn.load_model(model_uri)
        
        return model, f"{model_stage}-latest"
    except Exception as e:
        logger.error(f"❌ Failed to load model: {e}")
        return None, None

def generate_background_data(n_samples=50):
    """Generate background data for SHAP"""
    np.random.seed(42)
    return pd.DataFrame({
        'bedrooms': np.random.randint(1, 6, n_samples),
        'bathrooms': np.random.randint(1, 4, n_samples),
        'sqft': np.random.randint(500, 5000, n_samples),
        'age': np.random.randint(0, 50, n_samples),
    })

def calculate_shap_values(model, features_df):
    """Calculate SHAP values for a prediction"""
    try:
        # Create explainer for this request
        background_data = generate_background_data(50)
        explainer = shap.TreeExplainer(model, background_data)
        
        shap_values = explainer.shap_values(features_df)
        base_value = explainer.expected_value
        
        # Handle different SHAP output formats
        if isinstance(shap_values, list):
            shap_values = shap_values[0]
        
        shap_dict = {
            'shap_bedrooms': float(shap_values[0][0]),
            'shap_bathrooms': float(shap_values[0][1]),
            'shap_sqft': float(shap_values[0][2]),
            'shap_age': float(shap_values[0][3]),
            'base_value': float(base_value),
        }
        
        # Calculate human-readable contributions
        contributions = {
            'bedrooms': f"${shap_values[0][0]:+,.0f}",
            'bathrooms': f"${shap_values[0][1]:+,.0f}",
            'sqft': f"${shap_values[0][2]:+,.0f}",
            'age': f"${shap_values[0][3]:+,.0f}",
        }
        
        return shap_dict, contributions
        
    except Exception as e:
        logger.error(f"❌ SHAP calculation failed: {e}")
        return None, None

def log_prediction_to_db(request_id, features_dict, prediction, model_version, latency_ms):
    """Log prediction to PostgreSQL database"""
    if not SessionLocal:
        return False
    
    try:
        db = SessionLocal()
        query = text("""
            INSERT INTO prediction_logs 
            (request_id, timestamp, model_version, features, prediction, latency_ms)
            VALUES (:request_id, :timestamp, :model_version, :features, :prediction, :latency_ms)
        """)
        
        db.execute(query, {
            "request_id": request_id,
            "timestamp": datetime.utcnow(),
            "model_version": model_version,
            "features": json.dumps(features_dict),
            "prediction": float(prediction),
            "latency_ms": latency_ms
        })
        
        db.commit()
        db.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to log prediction: {e}")
        return False

def log_explainability_to_db(request_id, shap_dict, prediction, model_version):
    """Log SHAP values to PostgreSQL database"""
    if not SessionLocal or not shap_dict:
        return False
    
    try:
        db = SessionLocal()
        query = text("""
            INSERT INTO explainability_logs 
            (request_id, timestamp, model_version, shap_bedrooms, shap_bathrooms, 
             shap_sqft, shap_age, base_value, prediction_value)
            VALUES (:request_id, :timestamp, :model_version, :shap_bedrooms, :shap_bathrooms,
                    :shap_sqft, :shap_age, :base_value, :prediction_value)
        """)
        
        db.execute(query, {
            "request_id": request_id,
            "timestamp": datetime.utcnow(),
            "model_version": model_version,
            "shap_bedrooms": shap_dict['shap_bedrooms'],
            "shap_bathrooms": shap_dict['shap_bathrooms'],
            "shap_sqft": shap_dict['shap_sqft'],
            "shap_age": shap_dict['shap_age'],
            "base_value": shap_dict['base_value'],
            "prediction_value": float(prediction)
        })
        
        db.commit()
        db.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to log explainability: {e}")
        return False

# Endpoints
@app.get("/")
async def home():
    """Basic info endpoint"""
    return {
        "service": "House Price Prediction API - Simple Mode",
        "version": "2.0.0-simple",
        "mode": "load_on_request",
        "features": [
            "Always loads latest model",
            "SHAP explainability",
            "PostgreSQL logging",
            "No restart needed for new models"
        ],
        "database_connected": SessionLocal is not None
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "mode": "load_on_request",
        "database": "connected" if SessionLocal else "disconnected"
    }

@app.post("/predict", response_model=PredictionResult)
async def predict(house: HouseFeatures) -> PredictionResult:
    """
    Make a single prediction
    Loads fresh model from MLflow on every request
    """
    
    start_time = time.time()
    request_id = str(uuid.uuid4())
    
    # Load model (fresh every request)
    logger.info("🔄 Loading model from MLflow...")
    model, model_version = load_model_from_mlflow()
    
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="Failed to load model from MLflow. Check MLFLOW_TRACKING_URI and model registry."
        )
    
    logger.info(f"✅ Model loaded: {model_version}")
    
    # Convert to DataFrame for model
    features_dict = house.dict()
    features_df = pd.DataFrame([features_dict])
    
    # Make prediction
    prediction = float(model.predict(features_df)[0])
    
    # Calculate latency
    latency_ms = int((time.time() - start_time) * 1000)
    
    # Log prediction to database
    log_success = log_prediction_to_db(
        request_id, 
        features_dict, 
        prediction, 
        model_version, 
        latency_ms
    )
    
    if log_success:
        logger.info(f"✅ Logged prediction {request_id} to database")
    
    # Calculate SHAP values
    explanation = None
    shap_dict, contributions = calculate_shap_values(model, features_df)
    
    if shap_dict:
        # Log explainability to database
        log_explainability_to_db(request_id, shap_dict, prediction, model_version)
        
        # Add to response
        explanation = {
            "method": "SHAP",
            "contributions": contributions,
            "base_value": shap_dict['base_value']
        }
        logger.info(f"✅ Calculated SHAP values")
    
    logger.info(f"⏱️  Total request time: {latency_ms}ms")
    
    return PredictionResult(
        request_id=request_id,
        price=round(prediction, 2),
        model_version=model_version,
        explanation=explanation
    )

@app.post("/predict/batch")
async def predict_batch(houses: List[HouseFeatures]) -> dict:
    """Make multiple predictions"""
    results = []
    for house in houses:
        result = await predict(house)
        results.append({
            "request_id": result.request_id,
            "price": result.price
        })
    
    return {
        "predictions": results,
        "count": len(results)
    }

@app.get("/stats")
async def get_stats():
    """Get prediction statistics from database"""
    if not SessionLocal:
        return {"error": "Database not connected"}
    
    try:
        db = SessionLocal()
        
        query = text("""
            SELECT 
                COUNT(*) as total_predictions,
                AVG(prediction) as avg_price,
                MIN(prediction) as min_price,
                MAX(prediction) as max_price,
                AVG(latency_ms) as avg_latency_ms
            FROM prediction_logs
            WHERE timestamp > NOW() - INTERVAL '24 hours'
        """)
        
        result = db.execute(query).fetchone()
        db.close()
        
        return {
            "period": "last_24_hours",
            "total_predictions": result[0],
            "average_price": round(result[1], 2) if result[1] else 0,
            "min_price": round(result[2], 2) if result[2] else 0,
            "max_price": round(result[3], 2) if result[3] else 0,
            "avg_latency_ms": round(result[4], 2) if result[4] else 0
        }
        
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return {"error": str(e)}

@app.get("/stats/explainability")
async def get_explainability_stats():
    """Get feature importance from recent predictions"""
    if not SessionLocal:
        return {"error": "Database not connected"}
    
    try:
        db = SessionLocal()
        
        query = text("""
            SELECT 
                AVG(ABS(shap_bedrooms)) as avg_bedrooms,
                AVG(ABS(shap_bathrooms)) as avg_bathrooms,
                AVG(ABS(shap_sqft)) as avg_sqft,
                AVG(ABS(shap_age)) as avg_age
            FROM explainability_logs
            WHERE timestamp > NOW() - INTERVAL '24 hours'
        """)
        
        result = db.execute(query).fetchone()
        db.close()
        
        if result[0] is None:
            return {"message": "No explainability data yet"}
        
        total = sum([result[0], result[1], result[2], result[3]])
        
        return {
            "period": "last_24_hours",
            "feature_importance": {
                "bedrooms": round(result[0] / total, 3) if total > 0 else 0,
                "bathrooms": round(result[1] / total, 3) if total > 0 else 0,
                "sqft": round(result[2] / total, 3) if total > 0 else 0,
                "age": round(result[3] / total, 3) if total > 0 else 0
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get explainability stats: {e}")
        return {"error": str(e)}

@app.get("/history")
async def get_history(limit: int = 10):
    """Get recent predictions from database"""
    if not SessionLocal:
        return {"error": "Database not connected"}
    
    try:
        db = SessionLocal()
        
        query = text("""
            SELECT 
                request_id,
                timestamp,
                features,
                prediction,
                latency_ms
            FROM prediction_logs
            ORDER BY timestamp DESC
            LIMIT :limit
        """)
        
        result = db.execute(query, {"limit": limit}).fetchall()
        db.close()
        
        history = []
        for row in result:
            history.append({
                "request_id": row[0],
                "timestamp": row[1].isoformat(),
                "features": row[2],
                "prediction": round(row[3], 2),
                "latency_ms": row[4]
            })
        
        return {"predictions": history, "count": len(history)}
        
    except Exception as e:
        logger.error(f"Failed to get history: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
