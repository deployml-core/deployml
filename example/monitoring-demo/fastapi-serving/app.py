"""
FastAPI serving application with prediction logging to metrics database
"""
import os
import uuid
from datetime import datetime
from typing import List
import pandas as pd
import mlflow
import mlflow.sklearn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="House Price Prediction API with Monitoring")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./predictions.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class PredictionLog(Base):
    __tablename__ = "prediction_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(50), unique=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    model_name = Column(String(100))
    model_version = Column(String(50))
    features = Column(JSON)
    prediction = Column(Float)
    processing_time_ms = Column(Float)

Base.metadata.create_all(bind=engine)

class HousePredictionRequest(BaseModel):
    bedrooms: int
    bathrooms: int
    sqft: int
    age: int

class PredictionResponse(BaseModel):
    request_id: str
    prediction: float
    model_version: str
    timestamp: str

model = None
model_version = "1"

@app.on_event("startup")
async def load_model():
    global model, model_version
    
    try:
        mlflow_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000')
        mlflow.set_tracking_uri(mlflow_uri)
        
        model_name = "house-price-model"
        model_uri = f"models:/{model_name}/latest"
        
        logger.info(f"Loading model from {model_uri}...")
        model = mlflow.sklearn.load_model(model_uri)
        model_version = "latest"
        
        logger.info(f"✅ Model loaded: {model_name} version {model_version}")
    except Exception as e:
        logger.error(f"❌ Failed to load model: {e}")
        logger.info("Using fallback model")
        model = None

def log_prediction(request_id: str, features: dict, prediction: float, processing_time: float):
    try:
        db = SessionLocal()
        
        log_entry = PredictionLog(
            request_id=request_id,
            timestamp=datetime.utcnow(),
            model_name="house-price-model",
            model_version=model_version,
            features=features,
            prediction=prediction,
            processing_time_ms=processing_time
        )
        
        db.add(log_entry)
        db.commit()
        db.close()
        
        logger.info(f"✅ Logged prediction {request_id}")
    except Exception as e:
        logger.error(f"❌ Failed to log prediction: {e}")

@app.get("/")
async def root():
    return {
        "status": "healthy",
        "service": "house-price-prediction",
        "model_loaded": model is not None,
        "model_version": model_version
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "database_connected": True,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/predict", response_model=PredictionResponse)
async def predict(request: HousePredictionRequest):
    start_time = datetime.utcnow()
    request_id = str(uuid.uuid4())
    
    try:
        features_dict = {
            'bedrooms': request.bedrooms,
            'bathrooms': request.bathrooms,
            'sqft': request.sqft,
            'age': request.age
        }
        
        features_df = pd.DataFrame([features_dict])
        
        if model is not None:
            prediction = float(model.predict(features_df)[0])
        else:
            prediction = (
                request.bedrooms * 50000 +
                request.bathrooms * 30000 +
                request.sqft * 100 -
                request.age * 2000
            )
        
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds() * 1000
        
        log_prediction(request_id, features_dict, prediction, processing_time)
        
        return PredictionResponse(
            request_id=request_id,
            prediction=round(prediction, 2),
            model_version=model_version,
            timestamp=end_time.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/predict/batch")
async def predict_batch(requests: List[HousePredictionRequest]):
    results = []
    for req in requests:
        try:
            result = await predict(req)
            results.append(result)
        except Exception as e:
            logger.error(f"Batch prediction error: {e}")
            continue
    
    return {"predictions": results, "count": len(results)}

@app.get("/stats")
async def get_stats():
    try:
        db = SessionLocal()
        from sqlalchemy import func
        
        total_predictions = db.query(func.count(PredictionLog.id)).scalar()
        avg_processing_time = db.query(func.avg(PredictionLog.processing_time_ms)).scalar()
        
        recent_predictions = db.query(PredictionLog)\
            .order_by(PredictionLog.timestamp.desc())\
            .limit(10)\
            .all()
        
        db.close()
        
        return {
            "total_predictions": total_predictions,
            "avg_processing_time_ms": round(avg_processing_time, 2) if avg_processing_time else 0,
            "recent_predictions": len(recent_predictions)
        }
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

