"""
Drift monitoring script - runs on a schedule to detect data drift
"""
import os
import json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from scipy import stats
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./predictions.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class DriftMetric(Base):
    __tablename__ = "drift_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    feature_name = Column(String(100))
    drift_score = Column(Float)
    ks_statistic = Column(Float)
    ks_pvalue = Column(Float)
    drift_detected = Column(Boolean)
    model_version = Column(String(50))
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    reference_mean = Column(Float)
    current_mean = Column(Float)
    reference_std = Column(Float)
    current_std = Column(Float)

Base.metadata.create_all(bind=engine)

def calculate_psi(expected, actual, bins=10):
    """Calculate Population Stability Index"""
    def create_bins(data, bins):
        return pd.qcut(data, q=bins, duplicates='drop', retbins=True)[1]
    
    try:
        breakpoints = create_bins(expected, bins)
        expected_percents = pd.cut(expected, bins=breakpoints).value_counts(normalize=True)
        actual_percents = pd.cut(actual, bins=breakpoints).value_counts(normalize=True)
        expected_percents, actual_percents = expected_percents.align(actual_percents, fill_value=0.0001)
        psi_values = (actual_percents - expected_percents) * np.log(actual_percents / expected_percents)
        psi = psi_values.sum()
        return float(psi) if not np.isnan(psi) else 0.0
    except Exception as e:
        logger.warning(f"PSI calculation failed: {e}")
        return 0.0

def get_prediction_logs(days=7):
    try:
        db = SessionLocal()
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        query = f"""
            SELECT timestamp, features, prediction, model_version
            FROM prediction_logs
            WHERE timestamp >= '{start_date.isoformat()}'
            AND timestamp <= '{end_date.isoformat()}'
        """
        
        df = pd.read_sql(query, engine)
        db.close()
        
        if df.empty:
            logger.warning("No prediction logs found")
            return None, start_date, end_date
        
        features_df = pd.json_normalize(df['features'])
        features_df['timestamp'] = df['timestamp']
        features_df['prediction'] = df['prediction']
        
        logger.info(f"✅ Loaded {len(features_df)} predictions from {start_date} to {end_date}")
        return features_df, start_date, end_date
        
    except Exception as e:
        logger.error(f"❌ Failed to fetch prediction logs: {e}")
        return None, None, None

def get_reference_statistics():
    return {
        'bedrooms': {'mean': 3.0, 'std': 1.4, 'min': 1, 'max': 5},
        'bathrooms': {'mean': 2.0, 'std': 0.8, 'min': 1, 'max': 3},
        'sqft': {'mean': 2500, 'std': 1200, 'min': 500, 'max': 5000},
        'age': {'mean': 25, 'std': 14, 'min': 0, 'max': 50},
    }

def calculate_drift_metrics(production_data, reference_stats, start_date, end_date):
    drift_results = []
    features = ['bedrooms', 'bathrooms', 'sqft', 'age']
    
    logger.info("🔍 Calculating drift metrics...")
    
    for feature in features:
        if feature not in production_data.columns:
            continue
        
        try:
            current_values = production_data[feature].dropna()
            if len(current_values) == 0:
                continue
            
            ref_mean = reference_stats[feature]['mean']
            ref_std = reference_stats[feature]['std']
            ref_min = reference_stats[feature]['min']
            ref_max = reference_stats[feature]['max']
            
            np.random.seed(42)
            reference_values = np.random.normal(ref_mean, ref_std, len(current_values))
            reference_values = np.clip(reference_values, ref_min, ref_max)
            
            psi_score = calculate_psi(reference_values, current_values)
            ks_stat, ks_pvalue = stats.ks_2samp(reference_values, current_values)
            drift_detected = psi_score > 0.2 or ks_pvalue < 0.05
            
            current_mean = float(current_values.mean())
            current_std = float(current_values.std())
            
            logger.info(f"  {feature}: PSI={psi_score:.4f}, KS={ks_stat:.4f} (p={ks_pvalue:.4f}), Drift={'YES' if drift_detected else 'NO'}")
            
            drift_results.append({
                'feature_name': feature,
                'drift_score': psi_score,
                'ks_statistic': float(ks_stat),
                'ks_pvalue': float(ks_pvalue),
                'drift_detected': drift_detected,
                'period_start': start_date,
                'period_end': end_date,
                'reference_mean': ref_mean,
                'current_mean': current_mean,
                'reference_std': ref_std,
                'current_std': current_std,
            })
            
        except Exception as e:
            logger.error(f"❌ Error calculating drift for {feature}: {e}")
            continue
    
    return drift_results

def save_drift_metrics(drift_results, model_version="latest"):
    try:
        db = SessionLocal()
        
        for result in drift_results:
            metric = DriftMetric(
                timestamp=datetime.utcnow(),
                model_version=model_version,
                **result
            )
            db.add(metric)
        
        db.commit()
        db.close()
        
        logger.info(f"✅ Saved {len(drift_results)} drift metrics to database")
        
    except Exception as e:
        logger.error(f"❌ Failed to save drift metrics: {e}")

def run_monitoring():
    logger.info("="*50)
    logger.info("🔍 Starting Drift Monitoring")
    logger.info("="*50)
    
    production_data, start_date, end_date = get_prediction_logs(days=7)
    
    if production_data is None or len(production_data) == 0:
        logger.warning("⚠️  No production data available for monitoring")
        return
    
    reference_stats = get_reference_statistics()
    drift_results = calculate_drift_metrics(production_data, reference_stats, start_date, end_date)
    save_drift_metrics(drift_results)
    
    drift_count = sum(1 for r in drift_results if r['drift_detected'])
    logger.info(f"\n{'='*50}")
    logger.info(f"📊 Monitoring Summary:")
    logger.info(f"   Total features monitored: {len(drift_results)}")
    logger.info(f"   Features with drift: {drift_count}")
    logger.info(f"   Period: {start_date.date()} to {end_date.date()}")
    logger.info(f"{'='*50}\n")
    
    if drift_count > 0:
        logger.warning(f"⚠️  DRIFT DETECTED in {drift_count} feature(s)!")
    else:
        logger.info("✅ No significant drift detected")

if __name__ == "__main__":
    run_monitoring()

