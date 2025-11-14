"""
Explainability Monitoring Service
Analyzes SHAP values and tracks feature importance over time
"""
import os
import json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging
from utils import send_alert

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
DATABASE_URL = os.getenv("DATABASE_URL")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "")
IMPORTANCE_SHIFT_THRESHOLD = float(os.getenv("IMPORTANCE_SHIFT_THRESHOLD", "0.3"))
TRACK_FEATURE_IMPORTANCE = os.getenv("TRACK_FEATURE_IMPORTANCE", "true").lower() == "true"
ALERT_ON_SHIFT = os.getenv("ALERT_ON_SHIFT", "true").lower() == "true"
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def get_explainability_logs(days=7):
    """
    Fetch SHAP values from explainability_logs table
    """
    try:
        db = SessionLocal()
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        query = text("""
            SELECT 
                timestamp,
                model_version,
                shap_bedrooms,
                shap_bathrooms,
                shap_sqft,
                shap_age,
                base_value,
                prediction_value
            FROM explainability_logs
            WHERE timestamp >= :start_date
            AND timestamp <= :end_date
            ORDER BY timestamp
        """)
        
        result = db.execute(query, {"start_date": start_date, "end_date": end_date})
        rows = result.fetchall()
        db.close()
        
        if not rows:
            logger.warning("No explainability logs found")
            return None
        
        df = pd.DataFrame(rows, columns=result.keys())
        logger.info(f"✅ Loaded {len(df)} explainability logs from {start_date} to {end_date}")
        return df
        
    except Exception as e:
        logger.error(f"❌ Failed to fetch explainability logs: {e}")
        return None


def calculate_feature_importance(shap_df):
    """
    Calculate average absolute SHAP values (feature importance)
    """
    features = ['bedrooms', 'bathrooms', 'sqft', 'age']
    importance = {}
    
    for feature in features:
        col_name = f'shap_{feature}'
        if col_name in shap_df.columns:
            # Mean absolute SHAP value = importance
            importance[feature] = abs(shap_df[col_name]).mean()
    
    # Normalize to sum to 1
    total = sum(importance.values())
    if total > 0:
        importance = {k: v/total for k, v in importance.items()}
    
    return importance


def get_previous_importance():
    """
    Get the most recent feature importance from the database
    """
    try:
        db = SessionLocal()
        
        query = text("""
            SELECT feature_name, importance_score, timestamp
            FROM feature_importance_log
            WHERE timestamp = (SELECT MAX(timestamp) FROM feature_importance_log)
            ORDER BY rank
        """)
        
        result = db.execute(query)
        rows = result.fetchall()
        db.close()
        
        if not rows:
            return None
        
        return {row[0]: row[1] for row in rows}
        
    except Exception as e:
        logger.warning(f"Could not fetch previous importance: {e}")
        return None


def save_feature_importance(importance, model_version="latest"):
    """
    Save feature importance to database
    """
    try:
        db = SessionLocal()
        timestamp = datetime.utcnow()
        
        # Sort by importance descending
        sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        
        for rank, (feature, score) in enumerate(sorted_features, 1):
            query = text("""
                INSERT INTO feature_importance_log 
                (timestamp, model_version, feature_name, importance_score, rank, calculation_method)
                VALUES (:timestamp, :model_version, :feature_name, :importance_score, :rank, :method)
            """)
            
            db.execute(query, {
                "timestamp": timestamp,
                "model_version": model_version,
                "feature_name": feature,
                "importance_score": float(score),
                "rank": rank,
                "method": "mean_abs_shap"
            })
        
        db.commit()
        db.close()
        
        logger.info(f"✅ Saved feature importance to database")
        
    except Exception as e:
        logger.error(f"❌ Failed to save feature importance: {e}")


def detect_importance_shift(current, previous, threshold=0.3):
    """
    Detect if feature importance has shifted significantly
    Returns: (has_shifted, shifts_dict)
    """
    if previous is None:
        return False, {}
    
    shifts = {}
    has_significant_shift = False
    
    for feature in current.keys():
        if feature in previous:
            shift = current[feature] - previous[feature]
            shifts[feature] = shift
            
            if abs(shift) > threshold:
                has_significant_shift = True
                logger.warning(f"⚠️  Significant shift in {feature}: {shift:+.3f}")
    
    return has_significant_shift, shifts


def run_monitoring():
    """
    Main monitoring function
    """
    logger.info("="*60)
    logger.info("🔍 Starting Explainability Monitoring")
    logger.info("="*60)
    
    # Fetch SHAP values
    shap_df = get_explainability_logs(days=7)
    
    if shap_df is None or len(shap_df) == 0:
        logger.warning("⚠️  No explainability data available")
        return
    
    # Calculate current feature importance
    logger.info("📊 Calculating feature importance...")
    current_importance = calculate_feature_importance(shap_df)
    
    logger.info("\n✅ Current Feature Importance:")
    for feature, score in sorted(current_importance.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"   {feature:12s}: {score:.3f}")
    
    if TRACK_FEATURE_IMPORTANCE:
        # Get previous importance
        previous_importance = get_previous_importance()
        
        if previous_importance:
            # Detect shifts
            has_shifted, shifts = detect_importance_shift(
                current_importance, 
                previous_importance, 
                IMPORTANCE_SHIFT_THRESHOLD
            )
            
            if has_shifted:
                logger.warning("\n⚠️  FEATURE IMPORTANCE SHIFT DETECTED!")
                logger.info("   Changes:")
                for feature, shift in sorted(shifts.items(), key=lambda x: abs(x[1]), reverse=True):
                    logger.info(f"   {feature:12s}: {shift:+.3f}")
                
                if ALERT_ON_SHIFT and ALERT_WEBHOOK_URL:
                    alert_message = {
                        "type": "importance_shift",
                        "timestamp": datetime.utcnow().isoformat(),
                        "threshold": IMPORTANCE_SHIFT_THRESHOLD,
                        "shifts": shifts,
                        "current_importance": current_importance
                    }
                    send_alert(ALERT_WEBHOOK_URL, alert_message)
        
        # Save current importance
        save_feature_importance(current_importance)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 Monitoring Summary:")
    logger.info(f"   Records analyzed: {len(shap_df)}")
    logger.info(f"   Most important feature: {max(current_importance, key=current_importance.get)}")
    logger.info(f"{'='*60}\n")


if __name__ == "__main__":
    run_monitoring()

