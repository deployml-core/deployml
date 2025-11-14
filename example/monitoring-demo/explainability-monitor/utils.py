"""
Utility functions for explainability monitoring
"""
import requests
import logging
import json

logger = logging.getLogger(__name__)


def send_alert(webhook_url, message):
    """
    Send alert to webhook (Slack, PagerDuty, etc.)
    """
    try:
        # Format for Slack
        if "slack.com" in webhook_url:
            payload = {
                "text": f"🚨 Explainability Alert: {message.get('type', 'unknown')}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Explainability Alert*\n{json.dumps(message, indent=2)}"
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

