"""
Utility functions for fairness monitoring
"""
import requests
import logging
import json
import numpy as np

logger = logging.getLogger(__name__)


def calculate_demographic_parity(predictions_df, sensitive_attr, threshold=0.5):
    """
    Calculate demographic parity: equal positive prediction rates across groups
    
    Returns: (rates_dict, max_difference)
    """
    groups = predictions_df.groupby(sensitive_attr)
    positive_rates = {}
    
    for group_name, group_data in groups:
        # Assuming binary classification or threshold on continuous predictions
        positive_rate = (group_data['prediction'] > threshold).mean()
        positive_rates[group_name] = float(positive_rate)
    
    # Calculate maximum difference
    rates = list(positive_rates.values())
    max_diff = max(rates) - min(rates) if rates else 0.0
    
    return positive_rates, max_diff


def calculate_disparate_impact(predictions_df, sensitive_attr, 
                                protected_group, reference_group, 
                                threshold_ratio=0.8):
    """
    Calculate disparate impact ratio between protected and reference groups
    
    Returns: (disparate_impact_ratio, violation)
    """
    protected_data = predictions_df[predictions_df[sensitive_attr] == protected_group]
    reference_data = predictions_df[predictions_df[sensitive_attr] == reference_group]
    
    if len(protected_data) == 0 or len(reference_data) == 0:
        logger.warning(f"Empty group data for disparate impact calculation")
        return 0.0, False
    
    # Mean predictions as proxy for positive rate
    protected_rate = protected_data['prediction'].mean()
    reference_rate = reference_data['prediction'].mean()
    
    if reference_rate == 0:
        logger.warning(f"Reference rate is zero, cannot calculate disparate impact")
        return 0.0, False
    
    disparate_impact = protected_rate / reference_rate
    violation = disparate_impact < threshold_ratio
    
    return float(disparate_impact), violation


def send_alert(webhook_url, message):
    """
    Send alert to webhook (Slack, PagerDuty, etc.)
    """
    try:
        # Format for Slack
        if "slack.com" in webhook_url:
            violations_text = "\n".join([
                f"• {v['metric_name']} on {v['group_attr']}: {v['metric_value']:.3f}"
                for v in message.get('violations', [])[:5]  # Show first 5
            ])
            
            payload = {
                "text": f"⚖️ Fairness Alert: {message.get('violations_count', 0)} violations detected",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Fairness Violations Detected*\n\n{violations_text}"
                        }
                    }
                ]
            }
        else:
            # Generic webhook format
            payload = message
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        
        logger.info("✅ Alert sent successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send alert: {e}")
        return False

