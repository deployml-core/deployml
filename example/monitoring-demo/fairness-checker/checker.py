"""
Fairness Monitoring Service
Detects bias and calculates fairness metrics across demographic groups
"""
import os
import json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging
from utils import send_alert, calculate_demographic_parity, calculate_disparate_impact

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
DATABASE_URL = os.getenv("DATABASE_URL")

# Parse SENSITIVE_ATTRIBUTES with error handling
try:
    SENSITIVE_ATTRIBUTES = json.loads(os.getenv("SENSITIVE_ATTRIBUTES", "[]"))
except (json.JSONDecodeError, TypeError) as e:
    logger.warning(f"Invalid SENSITIVE_ATTRIBUTES format: {e}. Defaulting to empty list.")
    SENSITIVE_ATTRIBUTES = []

# Parse FAIRNESS_METRICS with error handling
try:
    FAIRNESS_METRICS = json.loads(os.getenv("FAIRNESS_METRICS", '["demographic_parity", "disparate_impact"]'))
except (json.JSONDecodeError, TypeError) as e:
    logger.warning(f"Invalid FAIRNESS_METRICS format: {e}. Using defaults.")
    FAIRNESS_METRICS = ["demographic_parity", "disparate_impact"]

DEMOGRAPHIC_PARITY_THRESHOLD = float(os.getenv("DEMOGRAPHIC_PARITY_THRESHOLD", "0.1"))
DISPARATE_IMPACT_THRESHOLD = float(os.getenv("DISPARATE_IMPACT_THRESHOLD", "0.8"))
ALERT_ON_VIOLATION = os.getenv("ALERT_ON_VIOLATION", "true").lower() == "true"
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")

# Parse PROTECTED_GROUPS with error handling
try:
    PROTECTED_GROUPS = json.loads(os.getenv("PROTECTED_GROUPS", "null")) if os.getenv("PROTECTED_GROUPS") else None
except (json.JSONDecodeError, TypeError) as e:
    logger.warning(f"Invalid PROTECTED_GROUPS format: {e}. Defaulting to None.")
    PROTECTED_GROUPS = None

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def get_prediction_logs(days=7):
    """
    Fetch prediction logs with features for fairness analysis
    """
    try:
        db = SessionLocal()
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        query = text("""
            SELECT 
                timestamp,
                features,
                prediction,
                model_version
            FROM prediction_logs
            WHERE timestamp >= :start_date
            AND timestamp <= :end_date
            ORDER BY timestamp
        """)
        
        result = db.execute(query, {"start_date": start_date, "end_date": end_date})
        rows = result.fetchall()
        db.close()
        
        if not rows:
            logger.warning("No prediction logs found")
            return None, start_date, end_date
        
        # Convert to DataFrame
        data = []
        for row in rows:
            record = {
                'timestamp': row[0],
                'prediction': row[2],
                'model_version': row[3]
            }
            # Parse JSON features
            features = row[1] if isinstance(row[1], dict) else json.loads(row[1])
            record.update(features)
            data.append(record)
        
        df = pd.DataFrame(data)
        logger.info(f"✅ Loaded {len(df)} prediction logs from {start_date} to {end_date}")
        return df, start_date, end_date
        
    except Exception as e:
        logger.error(f"❌ Failed to fetch prediction logs: {e}")
        return None, None, None


def save_fairness_metric(metric_name, group_attr, group_value, metric_value, 
                         threshold_violated, period_start, period_end, sample_size):
    """
    Save fairness metric to database
    """
    try:
        db = SessionLocal()
        
        query = text("""
            INSERT INTO fairness_metrics 
            (timestamp, metric_name, group_attribute, group_value, metric_value,
             threshold_violated, period_start, period_end, sample_size)
            VALUES (:timestamp, :metric_name, :group_attribute, :group_value, :metric_value,
                    :threshold_violated, :period_start, :period_end, :sample_size)
        """)
        
        db.execute(query, {
            "timestamp": datetime.utcnow(),
            "metric_name": metric_name,
            "group_attribute": group_attr,
            "group_value": group_value,
            "metric_value": float(metric_value),
            "threshold_violated": threshold_violated,
            "period_start": period_start,
            "period_end": period_end,
            "sample_size": sample_size
        })
        
        db.commit()
        db.close()
        
    except Exception as e:
        logger.error(f"❌ Failed to save fairness metric: {e}")


def analyze_fairness(predictions_df, sensitive_attr, period_start, period_end):
    """
    Analyze fairness for a given sensitive attribute
    """
    if sensitive_attr not in predictions_df.columns:
        logger.warning(f"⚠️  Attribute '{sensitive_attr}' not found in data")
        return []
    
    results = []
    groups = predictions_df.groupby(sensitive_attr)
    
    logger.info(f"\n📊 Analyzing fairness for attribute: {sensitive_attr}")
    logger.info(f"   Groups found: {list(groups.groups.keys())}")
    
    # Calculate demographic parity if requested
    if "demographic_parity" in FAIRNESS_METRICS:
        parity_results, max_diff = calculate_demographic_parity(
            predictions_df, 
            sensitive_attr
        )
        
        violation = max_diff > DEMOGRAPHIC_PARITY_THRESHOLD
        
        logger.info(f"\n   Demographic Parity:")
        logger.info(f"      Max difference: {max_diff:.4f} (threshold: {DEMOGRAPHIC_PARITY_THRESHOLD})")
        logger.info(f"      Violation: {'YES ⚠️' if violation else 'NO ✅'}")
        
        for group_value, rate in parity_results.items():
            results.append({
                'metric_name': 'demographic_parity',
                'group_attr': sensitive_attr,
                'group_value': str(group_value),
                'metric_value': rate,
                'threshold_violated': violation,
                'period_start': period_start,
                'period_end': period_end,
                'sample_size': len(predictions_df[predictions_df[sensitive_attr] == group_value])
            })
    
    # Calculate disparate impact if requested
    if "disparate_impact" in FAIRNESS_METRICS and len(groups) == 2:
        # For binary sensitive attributes
        group_names = list(groups.groups.keys())
        
        # Determine which is protected vs reference
        if PROTECTED_GROUPS and sensitive_attr in PROTECTED_GROUPS:
            protected = PROTECTED_GROUPS[sensitive_attr][0] if PROTECTED_GROUPS[sensitive_attr] else group_names[0]
            reference = group_names[1] if group_names[0] == protected else group_names[0]
        else:
            protected, reference = group_names[0], group_names[1]
        
        di_ratio, violation = calculate_disparate_impact(
            predictions_df,
            sensitive_attr,
            protected,
            reference,
            DISPARATE_IMPACT_THRESHOLD
        )
        
        logger.info(f"\n   Disparate Impact:")
        logger.info(f"      Ratio: {di_ratio:.4f} (threshold: {DISPARATE_IMPACT_THRESHOLD})")
        logger.info(f"      Protected group: {protected}")
        logger.info(f"      Reference group: {reference}")
        logger.info(f"      Violation: {'YES ⚠️' if violation else 'NO ✅'}")
        
        results.append({
            'metric_name': 'disparate_impact',
            'group_attr': sensitive_attr,
            'group_value': f"{protected}_vs_{reference}",
            'metric_value': di_ratio,
            'threshold_violated': violation,
            'period_start': period_start,
            'period_end': period_end,
            'sample_size': len(predictions_df)
        })
    
    return results


def run_fairness_check():
    """
    Main fairness checking function
    """
    logger.info("="*60)
    logger.info("⚖️  Starting Fairness Monitoring")
    logger.info("="*60)
    
    if not SENSITIVE_ATTRIBUTES:
        logger.error("❌ No sensitive attributes specified!")
        return
    
    # Fetch prediction data
    predictions_df, period_start, period_end = get_prediction_logs(days=7)
    
    if predictions_df is None or len(predictions_df) == 0:
        logger.warning("⚠️  No prediction data available")
        return
    
    # Analyze fairness for each sensitive attribute
    all_results = []
    violations_found = []
    
    for attr in SENSITIVE_ATTRIBUTES:
        results = analyze_fairness(predictions_df, attr, period_start, period_end)
        all_results.extend(results)
        
        # Check for violations
        for result in results:
            if result['threshold_violated']:
                violations_found.append(result)
    
    # Save all results to database
    logger.info(f"\n💾 Saving {len(all_results)} fairness metrics...")
    for result in all_results:
        save_fairness_metric(**result)
    
    # Send alert if violations found
    if violations_found and ALERT_ON_VIOLATION and ALERT_WEBHOOK_URL:
        logger.warning(f"\n⚠️  FAIRNESS VIOLATIONS DETECTED: {len(violations_found)}")
        alert_message = {
            "type": "fairness_violation",
            "timestamp": datetime.utcnow().isoformat(),
            "violations_count": len(violations_found),
            "violations": violations_found
        }
        send_alert(ALERT_WEBHOOK_URL, alert_message)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"⚖️  Fairness Monitoring Summary:")
    logger.info(f"   Records analyzed: {len(predictions_df)}")
    logger.info(f"   Attributes checked: {len(SENSITIVE_ATTRIBUTES)}")
    logger.info(f"   Metrics calculated: {len(all_results)}")
    logger.info(f"   Violations found: {len(violations_found)}")
    logger.info(f"{'='*60}\n")


if __name__ == "__main__":
    run_fairness_check()

