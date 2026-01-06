import json
import subprocess
from pathlib import Path
from typing import Dict, Any, TYPE_CHECKING
from datetime import datetime, timezone
import pandas as pd

if TYPE_CHECKING:
    from mlflow.tracking import MlflowClient

from .urls import ServiceURLs
from .display import display_services_table


class DeploymentStack:
    """
    Main interface for a deployed MLOps stack
    Provides easy access to services and URLs
    """
    
    def __init__(self, config: Dict[str, Any], workspace_dir: Path):
        self.config = config
        self.workspace_dir = workspace_dir
        self.name = config.get('name', 'unknown')
        self.provider = config.get('provider', {})
        self._urls = None
        self._mlflow_client = None
        
    @property
    def urls(self) -> ServiceURLs:
        """Get all service URLs"""
        if self._urls is None:
            self._urls = self._extract_urls()
        return self._urls
    
    def _extract_urls(self) -> ServiceURLs:
        """Extract URLs from Terraform outputs"""
        try:
            terraform_dir = self.workspace_dir / "terraform"
            result = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=terraform_dir,
                capture_output=True,
                text=True,
                check=True
            )
            
            outputs = json.loads(result.stdout)
            urls = ServiceURLs()
            
            # Extract URLs from Terraform outputs
            for key, value in outputs.items():
                output_val = value.get('value', '')
                if 'mlflow' in key.lower() and output_val.startswith('http'):
                    urls.mlflow = output_val
                elif 'feast' in key.lower() and output_val.startswith('http'):
                    urls.feast = output_val
                elif 'fastapi' in key.lower() or 'serving' in key.lower() and output_val.startswith('http'):
                    urls.serving = output_val
                elif 'grafana' in key.lower() and output_val.startswith('http'):
                    urls.grafana = output_val
                elif 'instance_connection_name' in key.lower():
                    # Format PostgreSQL connection info for display
                    if output_val and ':' in output_val:
                        # Parse the instance connection name: project:region:instance
                        parts = output_val.split(':')
                        if len(parts) == 3:
                            project, region, instance = parts
                            urls.postgresql = f"Instance: {instance} (Project: {project}, Region: {region})"
                        else:
                            urls.postgresql = f"Connection: {output_val}"
                    elif output_val:
                        urls.postgresql = str(output_val)
                elif 'workflow_orchestration_cron_jobs_summary' in key.lower():
                    # Extract cron job URLs from the summary
                    if isinstance(output_val, dict):
                        for job_index, job_info in output_val.items():
                            if isinstance(job_info, dict) and 'job_url' in job_info:
                                job_name = job_info.get('service_name', f'job-{job_index}')
                                urls.cron_jobs[job_name] = job_info['job_url']
                    
            return urls
            
        except Exception as e:
            print(f"Warning: Could not extract URLs: {e}")
            return ServiceURLs()
    
    @property  
    def mlflow(self) -> 'MlflowClient':
        """Get pre-configured MLflow client (lazy import)"""
        if self._mlflow_client is None:
            try:
                import mlflow
                from mlflow.tracking import MlflowClient
            except ImportError:
                raise ImportError(
                    "mlflow is required for MLflow client access. "
                    "Install it with: pip install mlflow"
                )
            if self.urls.mlflow:
                mlflow.set_tracking_uri(self.urls.mlflow)
                self._mlflow_client = MlflowClient(self.urls.mlflow)
            else:
                raise RuntimeError("MLflow URL not available. Check deployment status.")
        return self._mlflow_client
    
    def get_urls_dataframe(self) -> pd.DataFrame:
        """Get service URLs as a pandas DataFrame"""
        return self.urls.to_dataframe()
    
    def show_urls(self) -> pd.DataFrame:
        """Display service URLs as professional DataFrame with clickable links"""
        df = self.get_urls_dataframe()
        
        print("\n" + "="*80)
        print("DEPLOYED MLOPS SERVICES")
        print("="*80)
        
        # Create professional HTML table with clickable links
        display_services_table(df)
        
        print("="*80)
        return df
    
    def get_postgresql_info(self, show_credentials: bool = False) -> Dict[str, str]:
        """Get PostgreSQL connection information for development use
        
        Args:
            show_credentials: If True, attempts to retrieve sensitive credentials
        """
        try:
            terraform_dir = self.workspace_dir / "terraform"
            result = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=terraform_dir,
                capture_output=True,
                text=True,
                check=True
            )
            
            outputs = json.loads(result.stdout)
            
            postgresql_info = {}
            for key, value in outputs.items():
                output_val = value.get('value', '')
                if 'instance_connection_name' in key.lower():
                    postgresql_info['connection_name'] = output_val
                elif 'postgresql_credentials' in key.lower() or 'db_password' in key.lower():
                    if show_credentials:
                        # Try to get the actual sensitive value
                        try:
                            sensitive_result = subprocess.run(
                                ["terraform", "output", "-raw", key],
                                cwd=terraform_dir,
                                capture_output=True,
                                text=True,
                                check=True
                            )
                            postgresql_info['password'] = sensitive_result.stdout.strip()
                        except:
                            postgresql_info['password'] = "[SENSITIVE - Run show_postgresql_credentials()]"
                    else:
                        postgresql_info['credentials'] = "[SENSITIVE - Use show_credentials=True]"
                elif 'db_user' in key.lower() or 'postgresql_user' in key.lower():
                    postgresql_info['username'] = output_val
                elif 'db_name' in key.lower() or 'database_name' in key.lower():
                    postgresql_info['database'] = output_val
                elif 'public_ip' in key.lower() and 'postgresql' in key.lower():
                    postgresql_info['public_ip'] = output_val
                    
            if 'connection_name' in postgresql_info:
                parts = postgresql_info['connection_name'].split(':')
                if len(parts) == 3:
                    postgresql_info['project'] = parts[0]
                    postgresql_info['region'] = parts[1] 
                    postgresql_info['instance'] = parts[2]
                    
                    # Generate connection strings with actual credentials if available
                    username = postgresql_info.get('username', 'postgres')
                    password = postgresql_info.get('password', 'PASSWORD')
                    database = postgresql_info.get('database', 'postgres')
                    
                    postgresql_info['cloud_sql_proxy'] = f"cloud_sql_proxy -instances={postgresql_info['connection_name']}=tcp:5432"
                    postgresql_info['connection_proxy'] = f"postgresql://{username}:{password}@127.0.0.1:5432/{database}"
                    
                    if 'public_ip' in postgresql_info:
                        postgresql_info['connection_direct'] = f"postgresql://{username}:{password}@{postgresql_info['public_ip']}:5432/{database}"
                    
            return postgresql_info
            
        except Exception as e:
            return {"error": f"Could not extract PostgreSQL info: {e}"}
    
    def show_postgresql_connection(self, show_credentials: bool = False):
        """Display detailed PostgreSQL connection information
        
        Args:
            show_credentials: If True, displays actual passwords and connection strings
        """
        info = self.get_postgresql_info(show_credentials=show_credentials)
        
        if 'error' in info:
            print(f"Error: {info['error']}")
            return
            
        print("\\n" + "="*80)
        print("POSTGRESQL CONNECTION INFORMATION")
        print("="*80)
        
        if 'connection_name' in info:
            print(f"Instance Connection Name: {info['connection_name']}")
            print(f"Project: {info.get('project', 'N/A')}")
            print(f"Region: {info.get('region', 'N/A')}")
            print(f"Instance: {info.get('instance', 'N/A')}")
            
            if show_credentials:
                print()
                print("Credentials:")
                print(f"  Username: {info.get('username', 'postgres')}")
                print(f"  Password: {info.get('password', '[NOT FOUND]')}")
                print(f"  Database: {info.get('database', 'postgres')}")
                
                if 'public_ip' in info:
                    print(f"  Public IP: {info['public_ip']}")
            
            print()
            print("Connection Options:")
            print("1. Using Cloud SQL Proxy:")
            print(f"   {info.get('cloud_sql_proxy', 'N/A')}")
            
            if show_credentials and 'connection_proxy' in info:
                print(f"   Connection String: {info['connection_proxy']}")
            else:
                print("   Then connect to: postgresql://username:password@127.0.0.1:5432/database")
            
            print()
            print("2. Direct connection (if public IP enabled):")
            if show_credentials and 'connection_direct' in info:
                print(f"   Connection String: {info['connection_direct']}")
            else:
                print("   postgresql://username:password@PUBLIC_IP:5432/database")
            
            if not show_credentials:
                print()
                print("💡 To see actual credentials, use: stack.show_postgresql_connection(show_credentials=True)")
                print("   Or use: stack.show_postgresql_credentials()")
            
        else:
            print("No PostgreSQL instance found in deployment")
            
        print("="*80)
    
    def show_postgresql_credentials(self):
        """Display PostgreSQL credentials for easy copy-paste into pgAdmin"""
        info = self.get_postgresql_info(show_credentials=True)
        
        if 'error' in info:
            print(f"Error: {info['error']}")
            return
            
        if 'connection_name' not in info:
            print("No PostgreSQL instance found in deployment")
            return
            
        print("\\n" + "="*80)
        print("🔐 POSTGRESQL CREDENTIALS FOR PGADMIN")
        print("="*80)
        
        username = info.get('username', 'postgres')
        password = info.get('password', '[NOT FOUND]')
        database = info.get('database', 'postgres')
        host_proxy = "127.0.0.1"
        port = "5432"
        
        print("For pgAdmin connection setup:")
        print(f"  Host: {host_proxy} (after running Cloud SQL Proxy)")
        print(f"  Port: {port}")
        print(f"  Username: {username}")
        print(f"  Password: {password}")
        print(f"  Database: {database}")
        
        if 'public_ip' in info:
            print()
            print("Direct connection (if public IP enabled):")
            print(f"  Host: {info['public_ip']}")
            print(f"  Port: {port}")
            print(f"  Username: {username}")
            print(f"  Password: {password}")
            print(f"  Database: {database}")
        
        print()
        print("Connection Strings:")
        if 'connection_proxy' in info:
            print(f"  Proxy: {info['connection_proxy']}")
        if 'connection_direct' in info:
            print(f"  Direct: {info['connection_direct']}")
            
        print()
        print("🚀 Steps to connect:")
        print("1. Start Cloud SQL Proxy:")
        print(f"   {info.get('cloud_sql_proxy', 'N/A')}")
        print("2. Open pgAdmin and create new server connection")
        print("3. Use the credentials above")
        
        print("="*80)
    
    def get_postgresql_password(self) -> str:
        """Get just the PostgreSQL password for programmatic use"""
        info = self.get_postgresql_info(show_credentials=True)
        return info.get('password', '[NOT FOUND]')
    
    def get_postgresql_connection_string(self, use_proxy: bool = True) -> str:
        """Get PostgreSQL connection string
        
        Args:
            use_proxy: If True, returns proxy connection (127.0.0.1), else direct IP
        """
        info = self.get_postgresql_info(show_credentials=True)
        
        if use_proxy:
            return info.get('connection_proxy', '[CONNECTION STRING NOT AVAILABLE]')
        else:
            return info.get('connection_direct', '[DIRECT CONNECTION NOT AVAILABLE]')
    
    def get_cron_jobs_info(self) -> Dict[str, Any]:
        """Get detailed cron job information"""
        try:
            terraform_dir = self.workspace_dir / "terraform"
            result = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=terraform_dir,
                capture_output=True,
                text=True,
                check=True
            )
            
            outputs = json.loads(result.stdout)
            
            cron_info = {}
            for key, value in outputs.items():
                if 'workflow_orchestration_cron_jobs_summary' in key.lower():
                    cron_info['jobs_summary'] = value.get('value', {})
                elif 'workflow_orchestration_cron_job_names' in key.lower():
                    cron_info['job_names'] = value.get('value', [])
                elif 'workflow_orchestration_cron_scheduler_jobs' in key.lower():
                    cron_info['scheduler_jobs'] = value.get('value', [])
                    
            return cron_info
            
        except Exception as e:
            return {"error": f"Could not extract cron job info: {e}"}
    
    def show_cron_jobs(self):
        """Display detailed cron job information"""
        info = self.get_cron_jobs_info()
        
        if 'error' in info:
            print(f"Error: {info['error']}")
            return
            
        print("\n" + "="*80)
        print("WORKFLOW ORCHESTRATION - CRON JOBS")
        print("="*80)
        
        jobs_summary = info.get('jobs_summary', {})
        if jobs_summary:
            for job_index, job_info in jobs_summary.items():
                if isinstance(job_info, dict):
                    print(f"\nJob {int(job_index) + 1}: {job_info.get('service_name', 'Unknown')}")
                    print(f"  Schedule: {job_info.get('cron_schedule', 'N/A')}")
                    print(f"  Image: {job_info.get('image', 'N/A')}")
                    if job_info.get('bigquery_dataset'):
                        print(f"  BigQuery Dataset: {job_info.get('bigquery_dataset')}")
                    print(f"  Console URL: {job_info.get('job_url', 'N/A')}")
                    if job_info.get('scheduler_name'):
                        print(f"  Scheduler: {job_info.get('scheduler_name')}")
        else:
            print("No cron jobs found in deployment")
            
        print("="*80)
    
    def show_status(self) -> None:
        """Show deployment status in professional format"""
        print("\n" + "="*80)
        print("DEPLOYMENT STATUS")
        print("="*80)
        
        status_data = [
            ["Stack Name", self.name],
            ["Cloud Provider", f"{self.provider.get('name', 'unknown')} ({self.provider.get('project_id', 'unknown')})"],
            ["Region", self.provider.get('region', 'unknown')],
            ["Workspace", str(self.workspace_dir)]
        ]
        
        for label, value in status_data:
            print(f"{label:20}: {value}")
        
        print("="*80)
    
    def get_teardown_status(self) -> Dict[str, Any]:
        """
        Get teardown status for this deployment stack.
        
        Returns:
            Dictionary with status information including:
            - exists: bool - Whether the scheduler job exists
            - state: str - Job state (ENABLED, PAUSED, etc.)
            - schedule: str - Cron schedule
            - schedule_time: datetime - Next scheduled execution time
            - time_zone: str - Timezone
            - last_attempt_time: Optional[datetime] - Last execution time
            - metadata: Optional[Dict] - Local metadata if available
        """
        from deployml.api import get_teardown_status as _get_teardown_status
        
        project_id = self.provider.get('project_id')
        region = self.provider.get('region')
        workspace_name = self.name
        
        if not project_id or not region:
            return {
                "exists": False,
                "error": "Missing project_id or region in configuration"
            }
        
        return _get_teardown_status(
            project_id=project_id,
            region=region,
            workspace_name=workspace_name,
            deployml_dir=self.workspace_dir
        )
    
    def update_teardown_schedule(
        self,
        duration_hours: int,
        time_zone: str = "UTC"
    ) -> Dict[str, Any]:
        """
        Update teardown schedule for this deployment stack.
        
        Args:
            duration_hours: Hours until teardown
            time_zone: Timezone (default: UTC)
        
        Returns:
            Dictionary with update result:
            - success: bool - Whether update succeeded
            - scheduled_time: datetime - New scheduled time
            - cron_schedule: str - Cron expression
            - error: Optional[str] - Error message if failed
        """
        from deployml.api import update_teardown_schedule as _update_teardown_schedule
        
        project_id = self.provider.get('project_id')
        region = self.provider.get('region')
        workspace_name = self.name
        
        if not project_id or not region:
            return {
                "success": False,
                "error": "Missing project_id or region in configuration"
            }
        
        return _update_teardown_schedule(
            project_id=project_id,
            region=region,
            workspace_name=workspace_name,
            duration_hours=duration_hours,
            deployml_dir=self.workspace_dir,
            time_zone=time_zone
        )
    
    def cancel_teardown(self) -> Dict[str, Any]:
        """
        Cancel scheduled teardown for this deployment stack.
        
        Returns:
            Dictionary with cancellation result:
            - success: bool - Whether cancellation succeeded
            - error: Optional[str] - Error message if failed
        """
        from deployml.api import cancel_teardown as _cancel_teardown
        
        project_id = self.provider.get('project_id')
        region = self.provider.get('region')
        workspace_name = self.name
        
        if not project_id or not region:
            return {
                "success": False,
                "error": "Missing project_id or region in configuration"
            }
        
        return _cancel_teardown(
            project_id=project_id,
            region=region,
            workspace_name=workspace_name,
            deployml_dir=self.workspace_dir
        )
    
    def show_teardown_status(self):
        """Display teardown status in a formatted way"""
        status = self.get_teardown_status()
        
        print("\n" + "="*80)
        print("AUTO-TEARDOWN STATUS")
        print("="*80)
        
        if status.get("error"):
            print(f"❌ Error: {status['error']}")
            print("="*80)
            return
        
        if not status.get("exists"):
            print("ℹ️  Auto-teardown is not scheduled for this workspace")
            print("="*80)
            return
        
        state_emoji = "✅" if status.get("state") == "ENABLED" else "⏸️" if status.get("state") == "PAUSED" else "❌"
        print(f"{state_emoji} Status: {status.get('state', 'UNKNOWN')}")
        print(f"📅 Cron Schedule: {status.get('schedule', 'N/A')}")
        print(f"🌍 Timezone: {status.get('time_zone', 'UTC')}")
        
        schedule_time = status.get("schedule_time")
        if schedule_time:
            print(f"⏰ Next Execution: {schedule_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            now = datetime.now(timezone.utc)
            if now < schedule_time:
                time_remaining = schedule_time - now
                hours = int(time_remaining.total_seconds() // 3600)
                minutes = int((time_remaining.total_seconds() % 3600) // 60)
                print(f"   ⏳ Time Remaining: {hours}h {minutes}m")
            else:
                time_passed = now - schedule_time
                hours_passed = int(time_passed.total_seconds() // 3600)
                minutes_passed = int((time_passed.total_seconds() % 3600) // 60)
                print(f"   ⚠️  Scheduled time passed {hours_passed}h {minutes_passed}m ago")
        
        last_attempt = status.get("last_attempt_time")
        if last_attempt:
            print(f"🕐 Last Execution: {last_attempt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        else:
            print("🕐 Last Execution: Never")
        
        print(f"\n📌 Job Name: {status.get('scheduler_job_name')}")
        print("\n💡 Actions:")
        print(f"   Update: stack.update_teardown_schedule(duration_hours=6)")
        print(f"   Cancel: stack.cancel_teardown()")
        
        print("="*80)