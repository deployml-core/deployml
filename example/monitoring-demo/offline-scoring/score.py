"""
Offline batch scoring script - runs on a schedule for batch predictions
"""
import os
from datetime import datetime
import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./predictions.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class BatchPrediction(Base):
    __tablename__ = "batch_predictions"
    
    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(50), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    model_version = Column(String(50))
    total_records = Column(Integer)
    avg_prediction = Column(Float)
    min_prediction = Column(Float)
    max_prediction = Column(Float)
    processing_time_seconds = Column(Float)

Base.metadata.create_all(bind=engine)

def generate_batch_data(n_samples=100):
    np.random.seed(int(datetime.now().timestamp()))
    
    data = {
        'bedrooms': np.random.randint(1, 7, n_samples),
        'bathrooms': np.random.randint(1, 5, n_samples),
        'sqft': np.random.randint(400, 6000, n_samples),
        'age': np.random.randint(0, 60, n_samples),
    }
    
    df = pd.DataFrame(data)
    logger.info(f"✅ Generated {len(df)} records for batch scoring")
    return df

def load_model():
    try:
        mlflow_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000')
        mlflow.set_tracking_uri(mlflow_uri)
        logger.info(f"📡 Connecting to MLflow at: {mlflow_uri}")
        
        model_name = os.getenv('MODEL_NAME', 'house-price-model')
        model_stage = os.getenv('MODEL_STAGE', 'Production')
        model_uri = f"models:/{model_name}/{model_stage}"
        
        logger.info(f"Loading model from {model_uri}...")
        model = mlflow.sklearn.load_model(model_uri)
        logger.info(f"✅ Model loaded successfully from {model_stage} stage")
        return model, model_stage
        
    except Exception as e:
        logger.error(f"❌ Failed to load model from {model_uri}: {e}")
        logger.error(f"   Make sure model '{model_name}' exists and is in '{model_stage}' stage")
        return None, None

def score_batch(model, data):
    try:
        start_time = datetime.utcnow()
        predictions = model.predict(data)
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds()
        
        results_df = data.copy()
        results_df['prediction'] = predictions
        results_df['timestamp'] = end_time
        
        logger.info(f"✅ Scored {len(predictions)} records in {processing_time:.2f}s")
        return results_df, processing_time
        
    except Exception as e:
        logger.error(f"❌ Batch scoring failed: {e}")
        return None, 0

def save_batch_results(batch_id, predictions_df, processing_time, model_version):
    try:
        db = SessionLocal()
        
        summary = BatchPrediction(
            batch_id=batch_id,
            timestamp=datetime.utcnow(),
            model_version=model_version,
            total_records=len(predictions_df),
            avg_prediction=float(predictions_df['prediction'].mean()),
            min_prediction=float(predictions_df['prediction'].min()),
            max_prediction=float(predictions_df['prediction'].max()),
            processing_time_seconds=processing_time
        )
        
        db.add(summary)
        db.commit()
        db.close()
        
        logger.info(f"✅ Saved batch summary to database")
        
    except Exception as e:
        logger.error(f"❌ Failed to save batch results: {e}")

def run_offline_scoring():
    logger.info("="*50)
    logger.info("📊 Starting Offline Batch Scoring")
    logger.info("="*50)
    
    batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    
    model, model_version = load_model()
    if model is None:
        logger.error("❌ Cannot proceed without model")
        return
    
    batch_data = generate_batch_data(n_samples=100)
    predictions_df, processing_time = score_batch(model, batch_data)
    
    if predictions_df is None:
        logger.error("❌ Batch scoring failed")
        return
    
    save_batch_results(batch_id, predictions_df, processing_time, model_version)
    
    logger.info(f"\n{'='*50}")
    logger.info(f"📊 Batch Scoring Summary:")
    logger.info(f"   Batch ID: {batch_id}")
    logger.info(f"   Records processed: {len(predictions_df)}")
    logger.info(f"   Avg prediction: ${predictions_df['prediction'].mean():,.2f}")
    logger.info(f"   Min prediction: ${predictions_df['prediction'].min():,.2f}")
    logger.info(f"   Max prediction: ${predictions_df['prediction'].max():,.2f}")
    logger.info(f"   Processing time: {processing_time:.2f}s")
    logger.info(f"{'='*50}\n")

if __name__ == "__main__":
    run_offline_scoring()

