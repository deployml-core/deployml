import subprocess
import typer
from pathlib import Path
from typing import Optional, Dict
from jinja2 import Environment, FileSystemLoader
from deployml.utils.constants import TEMPLATE_DIR


def check_minikube_running() -> bool:
    """Check if minikube is currently running."""
    try:
        result = subprocess.run(
            ["minikube", "status"],
            capture_output=True,
            text=True
        )
        return "Running" in result.stdout
    except Exception:
        return False


def start_minikube() -> bool:
    """Start minikube cluster."""
    typer.echo("Starting minikube...")
    try:
        result = subprocess.run(
            ["minikube", "start"],
            check=True,
            capture_output=True,
            text=True
        )
        typer.echo("Minikube started successfully!")
        return True
    except subprocess.CalledProcessError as e:
        typer.echo(f"Failed to start minikube: {e.stderr}")
        return False
    except FileNotFoundError:
        typer.echo("minikube command not found. Please install minikube first.")
        return False


def generate_fastapi_manifests(
    output_dir: Path,
    image: str,
) -> None:
    """
    Generate deployment.yaml and service.yaml for FastAPI in the specified directory.
    
    Args:
        output_dir: Directory where manifests will be created
        image: Docker image for FastAPI
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Default values
    port = 8000
    node_port = 30080
    replicas = 1
    cpu_request = "250m"
    memory_request = "512Mi"
    cpu_limit = "500m"
    memory_limit = "1Gi"
    service_name = "fastapi-service"
    
    # Load templates from files
    template_dir = TEMPLATE_DIR / "kubernetes_local"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    
    deployment_template = env.get_template("deployment.yaml.j2")
    service_template = env.get_template("service.yaml.j2")
    
    # Render templates
    deployment_yaml = deployment_template.render(
        image=image,
        port=port,
        replicas=replicas,
        cpu_request=cpu_request,
        memory_request=memory_request,
        cpu_limit=cpu_limit,
        memory_limit=memory_limit
    )
    
    service_yaml = service_template.render(
        service_name=service_name,
        port=port,
        node_port=node_port
    )
    
    # Write files
    deployment_file = output_dir / "deployment.yaml"
    service_file = output_dir / "service.yaml"
    
    deployment_file.write_text(deployment_yaml)
    service_file.write_text(service_yaml)
    
    typer.echo(f"Generated manifests in {output_dir}")
    typer.echo(f"   - {deployment_file}")
    typer.echo(f"   - {service_file}")


def deploy_fastapi_to_minikube(manifest_dir: Path) -> bool:
    """
    Deploy FastAPI to minikube using kubectl apply.
    
    Args:
        manifest_dir: Directory containing deployment.yaml and service.yaml
    """
    if not manifest_dir.exists():
        typer.echo(f"Directory not found: {manifest_dir}")
        return False
    
    deployment_file = manifest_dir / "deployment.yaml"
    service_file = manifest_dir / "service.yaml"
    
    if not deployment_file.exists() or not service_file.exists():
        typer.echo(f"Required manifest files not found in {manifest_dir}")
        return False
    
    typer.echo("Applying Kubernetes manifests...")
    
    try:
        typer.echo(f"   Applying {deployment_file.name}...")
        result = subprocess.run(
            ["kubectl", "apply", "-f", str(deployment_file)],
            check=True,
            capture_output=True,
            text=True
        )
        typer.echo(f"{result.stdout.strip()}")
        
        # Apply service
        typer.echo(f"   Applying {service_file.name}...")
        result = subprocess.run(
            ["kubectl", "apply", "-f", str(service_file)],
            check=True,
            capture_output=True,
            text=True
        )
        typer.echo(f"{result.stdout.strip()}")
        
        # Get service URL
        typer.echo("\n Getting service URL...")
        result = subprocess.run(
            ["minikube", "service", service_file.stem.replace("service", "service"), "--url"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            service_url = result.stdout.strip()
            typer.echo(f"FastAPI service is available at: {service_url}")
        else:
            # Fallback: get NodePort manually
            typer.echo("   Getting NodePort...")
            result = subprocess.run(
                ["kubectl", "get", "svc", "-o", "jsonpath='{.items[?(@.spec.type==\"NodePort\")].spec.ports[0].nodePort}'"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                node_port = result.stdout.strip().strip("'")
                minikube_ip = subprocess.run(
                    ["minikube", "ip"],
                    capture_output=True,
                    text=True
                ).stdout.strip()
                typer.echo(f"FastAPI service: http://{minikube_ip}:{node_port}")
        
        typer.echo("\n Deployment status:")
        subprocess.run(["kubectl", "get", "pods", "-l", "app=fastapi"])
        subprocess.run(["kubectl", "get", "svc", "-l", "app=fastapi"])
        
        return True
        
    except subprocess.CalledProcessError as e:
        typer.echo(f"Deployment failed: {e.stderr}")
        return False
    except FileNotFoundError:
        typer.echo("kubectl command not found. Please install kubectl first.")
        return False