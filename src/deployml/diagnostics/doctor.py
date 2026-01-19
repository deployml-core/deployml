import subprocess
import shutil
import os
import sys
import platform
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import importlib
try:
    from importlib.metadata import version as get_package_version_metadata
except ImportError:
    # Fallback for Python < 3.8
    try:
        from importlib_metadata import version as get_package_version_metadata
    except ImportError:
        get_package_version_metadata = None
from dataclasses import dataclass
from enum import Enum
import re

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from IPython.display import display, HTML
    IN_NOTEBOOK = True
except ImportError:
    IN_NOTEBOOK = False


class CheckStatus(Enum):
    """Status of a system check"""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    INFO = "INFO"
    SKIP = "SKIP"


@dataclass
class CheckResult:
    """Result of a system check"""
    name: str
    status: CheckStatus
    message: str
    details: Optional[str] = None
    fix_command: Optional[str] = None
    required: bool = True


class DeployMLDoctor:
    """System verification and dependency checker for DeployML"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: List[CheckResult] = []
        self.system_info = self._gather_system_info()
    
    def _gather_system_info(self) -> Dict[str, str]:
        """Gather basic system information"""
        return {
            'os': platform.system(),
            'os_version': platform.version(),
            'architecture': platform.architecture()[0],
            'python_version': sys.version,
            'python_executable': sys.executable,
            'current_directory': str(Path.cwd())
        }
    
    def run_all_checks(self) -> List[CheckResult]:
        """Run all system checks and return results"""
        self.results.clear()
        
        # Core Python checks
        self._check_python_version()
        self._check_required_packages()
        self._check_optional_packages()
        
        # Infrastructure tools
        self._check_docker()
        self._check_terraform()
        self._check_cloud_cli_tools()
        
        # Development tools
        self._check_git()
        self._check_infracost()
        
        # Permissions and access
        self._check_docker_permissions()
        self._check_cloud_authentication()
        
        # Configuration
        self._check_deployml_config()
        
        return self.results
    
    def _add_result(self, result: CheckResult):
        """Add a check result"""
        self.results.append(result)
        if self.verbose:
            status_symbol = {
                CheckStatus.PASS: "[PASS]",
                CheckStatus.FAIL: "[FAIL]",
                CheckStatus.WARNING: "[WARN]",
                CheckStatus.INFO: "[INFO]",
                CheckStatus.SKIP: "[SKIP]"
            }[result.status]
            print(f"{status_symbol} {result.name}: {result.message}")
    
    def _check_python_version(self):
        """Check Python version compatibility"""
        version = sys.version_info
        
        if version >= (3, 11):
            self._add_result(CheckResult(
                name="Python Version",
                status=CheckStatus.PASS,
                message=f"Python {version.major}.{version.minor}.{version.micro} (>= 3.11)"
            ))
        elif version >= (3, 8):
            self._add_result(CheckResult(
                name="Python Version", 
                status=CheckStatus.WARNING,
                message=f"Python {version.major}.{version.minor}.{version.micro} (Minimum supported, recommend >= 3.11)",
                fix_command="Consider upgrading: pyenv install 3.11 && pyenv global 3.11"
            ))
        else:
            self._add_result(CheckResult(
                name="Python Version",
                status=CheckStatus.FAIL,
                message=f"Python {version.major}.{version.minor}.{version.micro} (Too old, requires >= 3.8)",
                fix_command="Upgrade Python: pyenv install 3.11 && pyenv global 3.11"
            ))
    
    def _check_required_packages(self):
        """Check required Python packages"""
        required_packages = [
            ('typer', 'CLI framework'),
            ('pyyaml', 'YAML configuration parsing'),
            ('jinja2', 'Template rendering'),
            ('pandas', 'Data manipulation'),
            ('requests', 'HTTP client'),
            ('ipython', 'Interactive Python'),
            ('jupyter', 'Notebook support')
        ]
        
        for package, description in required_packages:
            try:
                importlib.import_module(package)
                version = self._get_package_version(package)
                self._add_result(CheckResult(
                    name=f"Package: {package}",
                    status=CheckStatus.PASS,
                    message=f"{description} - v{version}" if version else f"{description} - installed"
                ))
            except ImportError:
                self._add_result(CheckResult(
                    name=f"Package: {package}",
                    status=CheckStatus.FAIL,
                    message=f"Missing required package: {package} ({description})",
                    fix_command=f"pip install {package}",
                    required=True
                ))
    
    def _check_optional_packages(self):
        """Check optional packages that enhance functionality"""
        optional_packages = [
            ('mlflow', 'ML experiment tracking'),
            ('google-cloud-storage', 'GCP storage integration'),
            ('scikit-learn', 'Machine learning'),
            ('matplotlib', 'Plotting'),
            ('seaborn', 'Statistical visualization')
        ]
        
        for package, description in optional_packages:
            try:
                importlib.import_module(package)
                version = self._get_package_version(package)
                self._add_result(CheckResult(
                    name=f"Optional: {package}",
                    status=CheckStatus.PASS,
                    message=f"{description} - v{version}" if version else f"{description} - installed",
                    required=False
                ))
            except ImportError:
                self._add_result(CheckResult(
                    name=f"Optional: {package}",
                    status=CheckStatus.INFO,
                    message=f"Optional package not installed: {package} ({description})",
                    fix_command=f"pip install {package}",
                    required=False
                ))
    
    def _get_package_version(self, package_name: str) -> Optional[str]:
        """Get version of installed package"""
        try:
            if get_package_version_metadata:
                return get_package_version_metadata(package_name)
            else:
                return None
        except Exception:
            return None
    
    def _check_docker(self):
        """Check Docker installation and version"""
        if not shutil.which('docker'):
            self._add_result(CheckResult(
                name="Docker",
                status=CheckStatus.FAIL,
                message="Docker not found in PATH",
                fix_command="Install Docker: https://docs.docker.com/get-docker/"
            ))
            return
        
        try:
            result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.strip()
                self._add_result(CheckResult(
                    name="Docker",
                    status=CheckStatus.PASS,
                    message=version
                ))
            else:
                self._add_result(CheckResult(
                    name="Docker",
                    status=CheckStatus.FAIL,
                    message="Docker command failed",
                    details=result.stderr
                ))
        except Exception as e:
            self._add_result(CheckResult(
                name="Docker",
                status=CheckStatus.FAIL,
                message="Error checking Docker",
                details=str(e)
            ))
    
    def _check_terraform(self):
        """Check Terraform installation"""
        if not shutil.which('terraform'):
            self._add_result(CheckResult(
                name="Terraform",
                status=CheckStatus.FAIL,
                message="Terraform not found in PATH",
                fix_command="Install Terraform: https://developer.hashicorp.com/terraform/install"
            ))
            return
        
        try:
            result = subprocess.run(['terraform', 'version'], capture_output=True, text=True)
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                self._add_result(CheckResult(
                    name="Terraform",
                    status=CheckStatus.PASS,
                    message=version_line
                ))
            else:
                self._add_result(CheckResult(
                    name="Terraform",
                    status=CheckStatus.FAIL,
                    message="Terraform command failed",
                    details=result.stderr
                ))
        except Exception as e:
            self._add_result(CheckResult(
                name="Terraform",
                status=CheckStatus.FAIL,
                message="Error checking Terraform",
                details=str(e)
            ))
    
    def _check_cloud_cli_tools(self):
        """Check cloud CLI tools"""
        cloud_tools = [
            ('gcloud', 'Google Cloud CLI', 'https://cloud.google.com/sdk/docs/install'),
            ('aws', 'AWS CLI', 'https://aws.amazon.com/cli/'),
            ('az', 'Azure CLI', 'https://docs.microsoft.com/en-us/cli/azure/install-azure-cli')
        ]
        
        for tool, description, install_url in cloud_tools:
            if shutil.which(tool):
                try:
                    if tool == 'gcloud':
                        result = subprocess.run(['gcloud', 'version'], capture_output=True, text=True)
                        if result.returncode == 0:
                            version = result.stdout.split('\n')[0]
                            self._add_result(CheckResult(
                                name=description,
                                status=CheckStatus.PASS,
                                message=version,
                                required=False
                            ))
                        else:
                            self._add_result(CheckResult(
                                name=description,
                                status=CheckStatus.WARNING,
                                message="Installed but not properly configured",
                                required=False
                            ))
                    else:
                        # For AWS and Azure CLI
                        result = subprocess.run([tool, '--version'], capture_output=True, text=True)
                        if result.returncode == 0:
                            version = result.stdout.strip()
                            self._add_result(CheckResult(
                                name=description,
                                status=CheckStatus.PASS,
                                message=version,
                                required=False
                            ))
                except Exception:
                    self._add_result(CheckResult(
                        name=description,
                        status=CheckStatus.WARNING,
                        message="Installed but version check failed",
                        required=False
                    ))
            else:
                self._add_result(CheckResult(
                    name=description,
                    status=CheckStatus.INFO,
                    message=f"Not installed (optional for cloud deployments)",
                    fix_command=f"Install from: {install_url}",
                    required=False
                ))
    
    def _check_git(self):
        """Check Git installation"""
        if not shutil.which('git'):
            self._add_result(CheckResult(
                name="Git",
                status=CheckStatus.WARNING,
                message="Git not found (recommended for version control)",
                fix_command="Install Git: https://git-scm.com/downloads",
                required=False
            ))
            return
        
        try:
            result = subprocess.run(['git', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.strip()
                self._add_result(CheckResult(
                    name="Git",
                    status=CheckStatus.PASS,
                    message=version,
                    required=False
                ))
        except Exception:
            self._add_result(CheckResult(
                name="Git",
                status=CheckStatus.WARNING,
                message="Git installed but version check failed",
                required=False
            ))
    
    def _check_infracost(self):
        """Check Infracost installation for cost analysis"""
        if not shutil.which('infracost'):
            self._add_result(CheckResult(
                name="Infracost",
                status=CheckStatus.INFO,
                message="Not installed (optional for cost analysis)",
                fix_command="Install: brew install infracost/tap/infracost",
                required=False
            ))
            return
        
        try:
            result = subprocess.run(['infracost', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.strip()
                self._add_result(CheckResult(
                    name="Infracost",
                    status=CheckStatus.PASS,
                    message=version,
                    required=False
                ))
        except Exception:
            self._add_result(CheckResult(
                name="Infracost",
                status=CheckStatus.WARNING,
                message="Installed but version check failed",
                required=False
            ))
    
    def _check_docker_permissions(self):
        """Check Docker permissions"""
        try:
            result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
            if result.returncode == 0:
                self._add_result(CheckResult(
                    name="Docker Permissions",
                    status=CheckStatus.PASS,
                    message="Can run Docker commands"
                ))
            else:
                if "permission denied" in result.stderr.lower():
                    self._add_result(CheckResult(
                        name="Docker Permissions",
                        status=CheckStatus.FAIL,
                        message="Permission denied - user not in docker group",
                        fix_command="sudo usermod -aG docker $USER && newgrp docker"
                    ))
                else:
                    self._add_result(CheckResult(
                        name="Docker Permissions",
                        status=CheckStatus.FAIL,
                        message="Cannot run Docker commands",
                        details=result.stderr
                    ))
        except Exception as e:
            self._add_result(CheckResult(
                name="Docker Permissions",
                status=CheckStatus.FAIL,
                message="Error testing Docker permissions",
                details=str(e)
            ))
    
    def _check_cloud_authentication(self):
        """Check cloud authentication status"""
        # Check GCP authentication
        if shutil.which('gcloud'):
            try:
                result = subprocess.run(['gcloud', 'auth', 'list'], capture_output=True, text=True)
                if result.returncode == 0 and "ACTIVE" in result.stdout:
                    self._add_result(CheckResult(
                        name="GCP Authentication",
                        status=CheckStatus.PASS,
                        message="Authenticated with Google Cloud",
                        required=False
                    ))
                else:
                    self._add_result(CheckResult(
                        name="GCP Authentication",
                        status=CheckStatus.INFO,
                        message="Not authenticated (required for GCP deployments)",
                        fix_command="gcloud auth login",
                        required=False
                    ))
            except Exception:
                self._add_result(CheckResult(
                    name="GCP Authentication",
                    status=CheckStatus.INFO,
                    message="Cannot check authentication status",
                    required=False
                ))
    
    def _check_deployml_config(self):
        """Check DeployML configuration"""
        config_locations = [
            Path.home() / '.deployml' / 'config.yaml',
            Path.cwd() / '.deployml' / 'config.yaml',
            Path.cwd() / 'deployml.yaml'
        ]
        
        config_found = any(path.exists() for path in config_locations)
        
        if config_found:
            self._add_result(CheckResult(
                name="DeployML Config",
                status=CheckStatus.PASS,
                message="Configuration file found",
                required=False
            ))
        else:
            self._add_result(CheckResult(
                name="DeployML Config",
                status=CheckStatus.INFO,
                message="No configuration file found (will use defaults)",
                details=f"Looked in: {', '.join(str(p) for p in config_locations)}",
                required=False
            ))
    
    def print_results(self, show_all: bool = False):
        """Print results in a formatted way"""
        if IN_NOTEBOOK:
            self._print_notebook_results(show_all)
        else:
            self._print_cli_results(show_all)
    
    def _print_notebook_results(self, show_all: bool):
        """Print results formatted for Jupyter notebooks"""
        # System info
        print("SYSTEM INFORMATION")
        print("=" * 80)
        print(f"OS: {self.system_info['os']} ({self.system_info['architecture']})")
        print(f"Python: {self.system_info['python_version'].split()[0]}")
        print(f"Location: {self.system_info['current_directory']}")
        print()
        
        # Create HTML table for better notebook display
        if pd is not None:
            df = self.to_dataframe()
            if not show_all:
                df = df[(df['status'] != 'INFO') | (df['required'] == True)]
            
            # Style the DataFrame
            def color_status(val):
                if val == 'PASS':
                    return 'color: green; font-weight: bold'
                elif val == 'FAIL':
                    return 'color: red; font-weight: bold'
                elif val == 'WARNING':
                    return 'color: orange; font-weight: bold'
                else:
                    return 'color: blue'
            
            styled_df = df[['name', 'status', 'message', 'fix_command']].style.applymap(
                color_status, subset=['status']
            )
            
            print("DEPLOYML DOCTOR RESULTS")
            print("=" * 80)
            display(styled_df)
        else:
            self._print_simple_table(show_all)
        
        # Summary
        summary = self._get_summary_text()
        print("\n" + "=" * 80)
        print(summary)
    
    def _print_cli_results(self, show_all: bool):
        """Print results for CLI"""
        print("\nSYSTEM INFORMATION")
        print("=" * 80)
        print(f"OS: {self.system_info['os']} ({self.system_info['architecture']})")
        print(f"Python: {self.system_info['python_version'].split()[0]}")
        print(f"Location: {self.system_info['current_directory']}")
        
        print("\nDEPLOYML DOCTOR RESULTS")
        print("=" * 80)
        
        self._print_simple_table(show_all)
        
        print("\n" + "=" * 80)
        summary = self._get_summary_text()
        print(summary)
    
    def _print_simple_table(self, show_all: bool):
        """Print a simple text table"""
        # Calculate column widths
        max_name_width = max(len(r.name) for r in self.results)
        max_status_width = 8
        
        # Header
        print(f"{'STATUS':<{max_status_width}} {'COMPONENT':<{max_name_width}} RESULT")
        print("-" * (max_status_width + max_name_width + 50))
        
        for result in self.results:
            if not show_all and result.status == CheckStatus.INFO and not result.required:
                continue
            
            status_text = f"[{result.status.value}]"
            print(f"{status_text:<{max_status_width}} {result.name:<{max_name_width}} {result.message}")
            
            if result.fix_command:
                print(f"{'':<{max_status_width}} {'':<{max_name_width}} Fix: {result.fix_command}")
    
    def _get_summary_text(self) -> str:
        """Get summary text"""
        summary = self.get_summary()
        failed_count = summary['failed']
        warning_count = summary['warnings']
        
        if failed_count == 0:
            if warning_count == 0:
                return "All checks passed! DeployML is ready to use."
            else:
                return f"Ready with {warning_count} warnings. Consider addressing them for optimal experience."
        else:
            return f"{failed_count} critical issues found. DeployML may not work properly. Run the suggested fix commands above."
    
    def get_summary(self) -> Dict[str, int]:
        """Get a summary of check results"""
        return {
            'total': len(self.results),
            'passed': len([r for r in self.results if r.status == CheckStatus.PASS]),
            'failed': len([r for r in self.results if r.status == CheckStatus.FAIL]),
            'warnings': len([r for r in self.results if r.status == CheckStatus.WARNING]),
            'info': len([r for r in self.results if r.status == CheckStatus.INFO])
        }
    
    def to_dataframe(self) -> 'pd.DataFrame':
        """Convert results to pandas DataFrame"""
        if pd is None:
            raise ImportError("pandas not available")
        
        data = []
        for result in self.results:
            data.append({
                'name': result.name,
                'status': result.status.value,
                'message': result.message,
                'required': result.required,
                'fix_command': result.fix_command or '',
                'details': result.details or ''
            })
        
        return pd.DataFrame(data)


def run_doctor(verbose: bool = False, show_all: bool = False) -> DeployMLDoctor:
    """Run DeployML system verification
    
    Args:
        verbose: Show progress as checks run
        show_all: Show all results including optional info
    
    Returns:
        DeployMLDoctor instance with results
    """
    doctor = DeployMLDoctor(verbose=verbose)
    doctor.run_all_checks()
    doctor.print_results(show_all=show_all)
    return doctor


def check_system() -> DeployMLDoctor:
    """Quick system check function for notebooks"""
    return run_doctor()


# CLI integration - can be called directly
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="DeployML System Doctor")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-a", "--all", action="store_true", help="Show all results")
    
    args = parser.parse_args()
    run_doctor(verbose=args.verbose, show_all=args.all)