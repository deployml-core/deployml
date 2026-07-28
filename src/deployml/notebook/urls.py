from typing import Dict, Optional
import pandas as pd


class ServiceURLs:
    """Container for all service URLs"""

    def __init__(self):
        self.mlflow: Optional[str] = None
        self.feast: Optional[str] = None
        self.serving: Optional[str] = None
        self.grafana: Optional[str] = None
        self.postgresql: Optional[str] = None
        self.cron_jobs: Dict[str, str] = {}  # job_name -> job_url

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for easy iteration"""
        base_services = {
            "mlflow": self.mlflow,
            "feast": self.feast,
            "serving": self.serving,
            "grafana": self.grafana,
            "postgresql": self.postgresql,
        }
        # Add cron jobs with prefixed keys
        for job_name, job_url in self.cron_jobs.items():
            base_services[f"cron_{job_name}"] = job_url
        return base_services

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to pandas DataFrame for notebook display"""
        data = []
        service_names = {
            "mlflow": "MLflow Experiment Tracking",
            "feast": "Feast Feature Store",
            "serving": "Model Serving API",
            "grafana": "Grafana Monitoring Dashboard",
            "postgresql": "PostgreSQL Database",
        }

        # Add cron job service names
        for job_name in self.cron_jobs.keys():
            service_names[f"cron_{job_name}"] = (
                f"Cron Job: {job_name.replace('-', ' ').title()}"
            )

        for key, url in self.to_dict().items():
            if url:
                data.append(
                    {
                        "Service": service_names.get(key, key),
                        "URL": url,
                        "Status": "Ready",
                    }
                )
            else:
                data.append(
                    {
                        "Service": service_names.get(key, key),
                        "URL": "Not deployed",
                        "Status": "Missing",
                    }
                )

        return pd.DataFrame(data)
