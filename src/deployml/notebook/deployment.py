import sys
import yaml
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any

from .stack import DeploymentStack


def deploy(config_path: str, show_progress: bool = True) -> DeploymentStack:
    """
    Deploy MLOps stack from YAML configuration
    
    Args:
        config_path: Path to YAML configuration file
        show_progress: Show deployment progress
        
    Returns:
        DeploymentStack: Configured stack with service access
    """
    config_file = Path(config_path)
    
    # If relative path doesn't exist, try common locations
    if not config_file.exists():
        # Try in current directory
        if not config_file.is_absolute():
            # Try demo/ subdirectory
            demo_path = Path("demo") / config_file.name
            if demo_path.exists():
                config_file = demo_path
                print(f"ℹ️  Found config file in demo/ directory: {config_file}")
            else:
                # Try example/config/ subdirectory
                example_path = Path("example/config") / config_file.name
                if example_path.exists():
                    config_file = example_path
                    print(f"ℹ️  Found config file in example/config/ directory: {config_file}")
                else:
                    raise FileNotFoundError(
                        f"Configuration file not found: {config_path}\n"
                        f"Tried locations:\n"
                        f"  - {Path(config_path).absolute()}\n"
                        f"  - {Path('demo') / Path(config_path).name}\n"
                        f"  - {Path('example/config') / Path(config_path).name}"
                    )
    
    # Load configuration
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    # Pretty header
    print("\n" + "="*60)
    print("🚀 DEPLOYML STACK DEPLOYMENT")
    print("="*60)
    print(f"📋 Stack Name: {config.get('name', 'unknown')}")
    print(f"☁️  Provider: {config.get('provider', {}).get('name', 'unknown')} ({config.get('provider', {}).get('project_id', 'unknown')})")
    print(f"🌍 Region: {config.get('provider', {}).get('region', 'unknown')}")
    print(f"📄 Configuration: {config_path}")
    
    if show_progress:
        print(f"\n⏳ Initializing deployment...")
    
    # Setup workspace
    workspace_name = config.get('name', 'default')
    workspace_dir = Path.cwd() / ".deployml" / workspace_name
    
    # Run deployment using CLI command with logs (use resolved config_file path)
    _deploy_with_cli(str(config_file), workspace_dir)
    
    # Create and return deployment stack
    stack = DeploymentStack(config, workspace_dir)
    
    print("\n" + "="*60)
    print("🎉 DEPLOYMENT COMPLETED SUCCESSFULLY!")
    print("="*60)
    print("✅ All MLOps services are deployed and ready to use")
    print("📊 Check the URLs below to access your services")
    print("="*60)
    
    return stack


def load(stack_name: str) -> DeploymentStack:
    """
    Load an existing deployed stack
    
    Args:
        stack_name: Name of the deployed stack
        
    Returns:
        DeploymentStack: Loaded stack configuration
    """
    workspace_dir = Path.cwd() / ".deployml" / stack_name
    
    if not workspace_dir.exists():
        raise FileNotFoundError(f"Stack '{stack_name}' not found. Deploy it first with deployml.deploy()")
    
    # Try to find the original config file
    config_files = list(workspace_dir.glob("*.yaml")) + list(workspace_dir.glob("*.yml"))
    
    if not config_files:
        # Fallback: create minimal config from terraform state
        config = {
            'name': stack_name,
            'provider': {'name': 'gcp'},  # Default assumption
            'stack': []
        }
    else:
        with open(config_files[0], 'r') as f:
            config = yaml.safe_load(f)
    
    return DeploymentStack(config, workspace_dir)


def _deploy_with_logs(config_path: str, workspace_dir: Path) -> None:
    """Run deployment using CLI command and show logs in notebook"""
    import subprocess
    import sys
    
    # Run the actual CLI command that works
    cmd = [sys.executable, "-m", "deployml.cli.cli", "deploy", "-c", config_path, "-y"]
    
    print(f"Running: {' '.join(cmd)}")
    print("=" * 60)
    
    # Run with live output
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    
    # Stream output line by line
    for line in iter(process.stdout.readline, ''):
        print(line.rstrip())
        sys.stdout.flush()
    
    process.wait()
    
    if process.returncode != 0:
        raise RuntimeError(f"Deployment failed with exit code {process.returncode}")
        
def _format_deployment_line(line: str) -> str:
    """Format deployment log lines for better readability"""
    line = line.rstrip()
    
    # Skip empty lines and some control characters but preserve progress indicators
    if not line or (line.startswith('\\x1b') and '[2K' not in line):
        return None
    
    # Clean up terminal control sequences but keep progress content
    if '[2K' in line:
        line = line.replace('\x1b[2K', '').strip()
        if not line:
            return None
    
    # Fix literal \n strings that should be actual newlines
    if '\\n' in line:
        line = line.replace('\\n', '\n')
    
    # Format different types of lines
    if line.startswith('📦 DeployML Outputs:'):
        return f"\n{'='*60}\n🎯 DEPLOYMENT OUTPUTS\n{'='*60}"
    elif line.startswith('💰 COST ANALYSIS'):
        return f"\n{'='*60}\n💰 COST ANALYSIS\n{'='*60}"
    elif line.startswith('✅ Deployment complete!'):
        return f"\n✅ INFRASTRUCTURE DEPLOYMENT COMPLETE!"
    elif 'DeployML: Creating resources' in line:
        # Show progress lines for better user feedback
        if any(char in line for char in ['⠏', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠋']):
            # This is a progress line with spinner
            return f"\r{line}"  # Use carriage return to update same line
        elif '%' in line:
            # This is a progress line with percentage
            return f"\r{line}"  # Use carriage return to update same line
        elif '100%' in line:
            return "\n✅ Infrastructure deployment completed!"
        else:
            return line
    elif line.startswith('🚀 Deploying'):
        return f"\n🚀 STARTING DEPLOYMENT\n{'-'*40}\n{line}"
    elif line.startswith('📋 Initializing Terraform'):
        return f"\n🔧 INFRASTRUCTURE SETUP\n{'-'*40}\n{line}"
    elif line.startswith('Monthly Cost:') or line.startswith('Hourly Cost:'):
        return f"💵 {line}"
    elif line.startswith('• module.') or line.startswith('  Type:') or line.startswith('  Monthly Cost:'):
        return f"  {line}"
    elif '_url:' in line and 'https://' in line:
        # Format service URLs nicely
        parts = line.split(': ')
        if len(parts) == 2:
            service = parts[0].replace('_', ' ').title().replace('Mlflow', 'MLflow').replace('Fastapi', 'FastAPI')
            url = parts[1]
            if '[No value]' not in url:
                return f"🌐 {service}: {url}"
        return None  # Skip [No value] entries
    elif line.startswith('  ') and not line.startswith('    '):
        # Indent sub-items
        return f"    {line.strip()}"
    elif '🏗️ Applying changes...' in line:
        return f"\n🏗️ DEPLOYING INFRASTRUCTURE\n{'-'*40}\n{line}"
    elif 'Estimated time:' in line:
        return f"⏱️  {line}"
    elif any(char in line for char in ['⠏', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠋']) and ('terraform' in line.lower() or 'applying' in line.lower() or 'creating' in line.lower()):
        # Progress indicators for terraform operations
        return f"\r{line}"
    elif line.startswith('⠏') or line.startswith('⠙') or line.startswith('⠹') or line.startswith('⠸'):
        # Direct progress spinner lines
        return f"\r{line}"
    
    return line

def _deploy_with_cli(config_path: str, workspace_dir: Path) -> None:
    """Run deployment using deployml CLI command with formatted logs"""
    
    # Try direct deployml command first (pip installed)
    if shutil.which("deployml"):
        cmd = ["deployml", "deploy", "-c", config_path, "-y"]
        print(f"🔧 Command: {' '.join(cmd)}")
    # Fallback to poetry for development
    elif shutil.which("poetry"):
        cmd = ["poetry", "run", "deployml", "deploy", "-c", config_path, "-y"]
        print(f"🔧 Command: {' '.join(cmd)} (development mode)")
    # Last resort: direct python module
    else:
        cmd = [sys.executable, "-m", "deployml.cli.cli", "deploy", "-c", config_path, "-y"]
        print(f"🔧 Command: {' '.join(cmd)} (fallback)")
    
    print("\n" + "="*60)
    print("📝 DEPLOYMENT LOG")
    print("="*60)
    
    # Store output lines for error reporting
    output_lines = []
    
    # Run with live output
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    
    # Stream and format output line by line
    for line in iter(process.stdout.readline, ''):
        output_lines.append(line)
        formatted_line = _format_deployment_line(line)
        if formatted_line is not None:
            print(formatted_line)
            sys.stdout.flush()
    
    process.wait()
    
    if process.returncode != 0:
        # Force flush any pending output
        sys.stdout.flush()
        sys.stderr.flush()
        
        print(f"\n" + "="*60, flush=True)
        print(f"❌ DEPLOYMENT FAILED (Exit Code: {process.returncode})", flush=True)
        print("="*60, flush=True)
        
        # Show last 50 lines of output to help debug
        print("\n📋 Last 50 lines of output:", flush=True)
        print("-" * 60, flush=True)
        for line in output_lines[-50:]:
            # Show unformatted lines for error context
            clean_line = line.rstrip()
            if clean_line:
                print(clean_line, flush=True)
        
        # Try to extract error message
        error_lines = [line for line in output_lines if any(keyword in line.lower() for keyword in ['error', 'failed', 'fatal', 'exception', 'traceback'])]
        if error_lines:
            print("\n🔍 Error Summary:", flush=True)
            print("-" * 60, flush=True)
            for line in error_lines[-10:]:  # Last 10 error-related lines
                clean_line = line.rstrip()
                if clean_line:
                    print(clean_line, flush=True)
        else:
            print("\n⚠️  No obvious error keywords found in output.", flush=True)
            print("   Showing all output lines for debugging:", flush=True)
            print("-" * 60, flush=True)
            for line in output_lines:
                clean_line = line.rstrip()
                if clean_line:
                    print(clean_line, flush=True)
        
        print("="*60, flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
        
        raise RuntimeError(
            f"Deployment failed with exit code {process.returncode}. "
            f"Check the output above for details. "
            f"Total output lines: {len(output_lines)}, "
            f"Error-related lines: {len([l for l in output_lines if any(k in l.lower() for k in ['error', 'failed', 'fatal'])])}"
        )