"""Utilities for managing auto-teardown functionality."""
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any


METADATA_FILE = "deployment_metadata.json"


def save_deployment_metadata(workspace_dir: Path, metadata: Dict[str, Any]):
    """Save deployment metadata including teardown schedule."""
    metadata_path = workspace_dir / METADATA_FILE
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)


def load_deployment_metadata(workspace_dir: Path) -> Optional[Dict[str, Any]]:
    """Load deployment metadata."""
    metadata_path = workspace_dir / METADATA_FILE
    if not metadata_path.exists():
        return None
    
    with open(metadata_path, 'r') as f:
        return json.load(f)


def calculate_teardown_schedule(deployed_at: datetime, duration_hours: int) -> str:
    """
    Calculate cron expression for teardown time.
    Returns cron string like "0 2 15 1 *" for Jan 15 at 2:00 AM UTC
    """
    teardown_time = deployed_at + timedelta(hours=duration_hours)
    
    # Format: minute hour day month day-of-week
    minute = teardown_time.minute
    hour = teardown_time.hour
    day = teardown_time.day
    month = teardown_time.month
    
    return f"{minute} {hour} {day} {month} *"


def calculate_cron_from_timestamp(timestamp: int) -> str:
    """Convert Unix timestamp to cron expression."""
    # Use UTC timezone-aware datetime to ensure correct conversion
    from datetime import timezone
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return f"{dt.minute} {dt.hour} {dt.day} {dt.month} *"

