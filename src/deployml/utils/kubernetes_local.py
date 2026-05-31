import subprocess
import typer
from pathlib import Path
from typing import Optional, Dict
from jinja2 import Environment, FileSystemLoader
from deployml.utils.constants import TEMPLATE_DIR


def ns_args(namespace: Optional[str]) -> list:
    """kubectl/minikube namespace flag. Empty for the default namespace so the
    existing single-stack flow is unchanged."""
    return ["-n", namespace] if namespace and namespace != "default" else []


def ensure_namespace(namespace: Optional[str]) -> None:
    """Create the namespace if it does not exist. No-op for the default
    namespace. Idempotent via apply of a client-side dry-run manifest."""
    if not namespace or namespace == "default":
        return
    rendered = subprocess.run(
        ["kubectl", "create", "namespace", namespace, "--dry-run=client", "-o", "yaml"],
        capture_output=True, text=True,
    )
    if rendered.returncode == 0:
        subprocess.run(["kubectl", "apply", "-f", "-"], input=rendered.stdout,
                       capture_output=True, text=True)
        typer.echo(f"   Using namespace: {namespace}")


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
    mlflow_tracking_uri: Optional[str] = None,
    load_image: bool = True,
) -> None:
    """
    Generate deployment.yaml and service.yaml for FastAPI in the specified directory.
    
    Args:
        output_dir: Directory where manifests will be created
        image: Docker image for FastAPI
        mlflow_tracking_uri: Optional MLflow tracking URI
        load_image: Whether to automatically load image into minikube (default: True)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load image into minikube if requested
    if load_image:
        load_image_to_minikube(image)
    
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
        memory_limit=memory_limit,
        mlflow_tracking_uri=mlflow_tracking_uri
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


def generate_mlflow_manifests(
    output_dir: Path,
    image: str,
    backend_store_uri: Optional[str] = None,
    artifact_root: Optional[str] = None,
    load_image: bool = True,
    use_pvc: bool = True,
    pvc_size: str = "5Gi",
) -> None:
    """
    Generate deployment.yaml, service.yaml, and optionally pvc.yaml for MLflow.

    Args:
        output_dir: Directory where manifests will be created
        image: Docker image for MLflow
        backend_store_uri: Optional backend store URI. Default puts sqlite on
          the mounted volume so data survives pod restarts.
        artifact_root: Optional artifact root path
        load_image: Whether to automatically load image into minikube
        use_pvc: When True, generate a PersistentVolumeClaim and mount it.
          When False, use ephemeral emptyDir (legacy behavior).
        pvc_size: PVC size when use_pvc=True. Default 5Gi.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if load_image:
        load_image_to_minikube(image)

    port = 5000
    node_port = 30050
    replicas = 1
    # MLflow 3.x ships with huey consumers and other workers that push memory
    # well past 1Gi on cold start. Earlier defaults caused OOMKilled (exit 137)
    # within seconds of uvicorn starting. Bumped to 2Gi limit / 1Gi request.
    cpu_request = "500m"
    memory_request = "1Gi"
    cpu_limit = "1000m"
    memory_limit = "2Gi"
    service_name = "mlflow-service"

    if not backend_store_uri:
        # Put sqlite on the mounted volume so data survives pod restarts
        # when use_pvc=True. With emptyDir the file is still pod-local.
        backend_store_uri = "sqlite:////mlflow-artifacts/mlflow.db"
    if not artifact_root:
        artifact_root = "/mlflow-artifacts"

    template_dir = TEMPLATE_DIR / "kubernetes_local"
    env = Environment(loader=FileSystemLoader(str(template_dir)))

    deployment_template = env.get_template("mlflow-deployment.yaml.j2")
    service_template = env.get_template("mlflow-service.yaml.j2")

    deployment_yaml = deployment_template.render(
        image=image,
        port=port,
        replicas=replicas,
        cpu_request=cpu_request,
        memory_request=memory_request,
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
        backend_store_uri=backend_store_uri,
        artifact_root=artifact_root,
        use_pvc=use_pvc,
    )

    service_yaml = service_template.render(
        service_name=service_name,
        port=port,
        node_port=node_port
    )

    deployment_file = output_dir / "deployment.yaml"
    service_file = output_dir / "service.yaml"

    deployment_file.write_text(deployment_yaml)
    service_file.write_text(service_yaml)

    typer.echo(f"Generated MLflow manifests in {output_dir}")
    typer.echo(f"   - {deployment_file}")
    typer.echo(f"   - {service_file}")

    if use_pvc:
        pvc_template = env.get_template("mlflow-pvc.yaml.j2")
        pvc_yaml = pvc_template.render(pvc_size=pvc_size)
        pvc_file = output_dir / "pvc.yaml"
        pvc_file.write_text(pvc_yaml)
        typer.echo(f"   - {pvc_file}  (PersistentVolumeClaim, {pvc_size})")


def deploy_mlflow_to_minikube(manifest_dir: Path, image_name: Optional[str] = None,
                              namespace: Optional[str] = None) -> bool:
    """
    Deploy MLflow to minikube using kubectl apply.

    Args:
        manifest_dir: Directory containing deployment.yaml and service.yaml
        image_name: Optional image name to load if not already in minikube
        namespace: Target Kubernetes namespace. Default (None/"default") keeps
          everything in the default namespace; pass a value to isolate this stack.
    """
    if not manifest_dir.exists():
        typer.echo(f"Directory not found: {manifest_dir}")
        return False
    
    deployment_file = manifest_dir / "deployment.yaml"
    service_file = manifest_dir / "service.yaml"
    
    if not deployment_file.exists() or not service_file.exists():
        typer.echo(f"Required manifest files not found in {manifest_dir}")
        return False
    
    # Extract image name from deployment if not provided
    if not image_name:
        try:
            content = deployment_file.read_text()
            import re
            match = re.search(r'image:\s*([^\s]+)', content)
            if match:
                image_name = match.group(1)
        except Exception:
            pass
    
    # Load image if provided
    if image_name:
        load_image_to_minikube(image_name)
    
    typer.echo("Applying Kubernetes manifests...")
    ensure_namespace(namespace)
    ns = ns_args(namespace)

    try:
        # Apply PVC first so the deployment can reference it.
        pvc_file = manifest_dir / "pvc.yaml"
        if pvc_file.exists():
            typer.echo(f"   Applying {pvc_file.name}...")
            result = subprocess.run(
                ["kubectl", "apply", "-f", str(pvc_file)] + ns,
                check=True, capture_output=True, text=True,
            )
            typer.echo(f"{result.stdout.strip()}")

        typer.echo(f"   Applying {deployment_file.name}...")
        result = subprocess.run(
            ["kubectl", "apply", "-f", str(deployment_file)] + ns,
            check=True,
            capture_output=True,
            text=True
        )
        typer.echo(f"{result.stdout.strip()}")

        # Apply service
        typer.echo(f"   Applying {service_file.name}...")
        result = subprocess.run(
            ["kubectl", "apply", "-f", str(service_file)] + ns,
            check=True,
            capture_output=True,
            text=True
        )
        typer.echo(f"{result.stdout.strip()}")

        # Get service URL
        typer.echo("\n Getting service URL...")

        # Try minikube service --url with timeout (can hang)
        try:
            result = subprocess.run(
                ["minikube", "service", "mlflow-service", "--url"] + ns,
                capture_output=True,
                text=True,
                timeout=5  # 5 second timeout to prevent hanging
            )

            if result.returncode == 0 and result.stdout.strip():
                service_url = result.stdout.strip()
                typer.echo(f"MLflow service is available at: {service_url}")
            else:
                raise subprocess.TimeoutExpired("", 5)  # Fall through to fallback
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            # Fallback: get NodePort manually (more reliable)
            typer.echo("   Getting NodePort...")
            result = subprocess.run(
                ["kubectl", "get", "svc", "mlflow-service", "-o", "jsonpath='{.spec.ports[0].nodePort}'"] + ns,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                node_port = result.stdout.strip().strip("'")
                minikube_ip_result = subprocess.run(
                    ["minikube", "ip"],
                    capture_output=True,
                    text=True
                )
                if minikube_ip_result.returncode == 0:
                    minikube_ip = minikube_ip_result.stdout.strip()
                    typer.echo(f"MLflow service: http://{minikube_ip}:{node_port}")
                else:
                    typer.echo("   Could not determine minikube IP")
            else:
                typer.echo("   Could not determine service URL. Check with: kubectl get svc mlflow-service")

        typer.echo("\n Deployment status:")
        subprocess.run(["kubectl", "get", "pods", "-l", "app=mlflow"] + ns)
        subprocess.run(["kubectl", "get", "svc", "-l", "app=mlflow"] + ns)
        
        return True
        
    except subprocess.CalledProcessError as e:
        typer.echo(f"Deployment failed: {e.stderr}")
        return False
    except FileNotFoundError:
        typer.echo("kubectl command not found. Please install kubectl first.")
        return False


def deploy_fastapi_to_minikube(manifest_dir: Path, image_name: Optional[str] = None,
                               namespace: Optional[str] = None) -> bool:
    """
    Deploy FastAPI to minikube using kubectl apply.

    Args:
        manifest_dir: Directory containing deployment.yaml and service.yaml
        image_name: Optional image name to load if not already in minikube
        namespace: Target Kubernetes namespace. Default keeps the default
          namespace; pass a value to isolate this stack. Must match the MLflow
          namespace for in-cluster service DNS to resolve.
    """
    if not manifest_dir.exists():
        typer.echo(f"Directory not found: {manifest_dir}")
        return False
    
    deployment_file = manifest_dir / "deployment.yaml"
    service_file = manifest_dir / "service.yaml"
    
    if not deployment_file.exists() or not service_file.exists():
        typer.echo(f"Required manifest files not found in {manifest_dir}")
        return False
    
    # Extract image name from deployment if not provided
    if not image_name:
        try:
            content = deployment_file.read_text()
            import re
            match = re.search(r'image:\s*([^\s]+)', content)
            if match:
                image_name = match.group(1)
        except Exception:
            pass
    
    # Load image if provided
    if image_name:
        load_image_to_minikube(image_name)
    
    typer.echo("Applying Kubernetes manifests...")
    ensure_namespace(namespace)
    ns = ns_args(namespace)

    try:
        typer.echo(f"   Applying {deployment_file.name}...")
        result = subprocess.run(
            ["kubectl", "apply", "-f", str(deployment_file)] + ns,
            check=True,
            capture_output=True,
            text=True
        )
        typer.echo(f"{result.stdout.strip()}")

        # Apply service
        typer.echo(f"   Applying {service_file.name}...")
        result = subprocess.run(
            ["kubectl", "apply", "-f", str(service_file)] + ns,
            check=True,
            capture_output=True,
            text=True
        )
        typer.echo(f"{result.stdout.strip()}")

        # Get service URL
        typer.echo("\n Getting service URL...")

        # Try minikube service --url with timeout (can hang)
        try:
            result = subprocess.run(
                ["minikube", "service", "fastapi-service", "--url"] + ns,
                capture_output=True,
                text=True,
                timeout=5  # 5 second timeout to prevent hanging
            )

            if result.returncode == 0 and result.stdout.strip():
                service_url = result.stdout.strip()
                typer.echo(f"FastAPI service is available at: {service_url}")
            else:
                raise subprocess.TimeoutExpired("", 5)  # Fall through to fallback
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            # Fallback: get NodePort manually (more reliable)
            typer.echo("   Getting NodePort...")
            result = subprocess.run(
                ["kubectl", "get", "svc", "fastapi-service", "-o", "jsonpath='{.spec.ports[0].nodePort}'"] + ns,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                node_port = result.stdout.strip().strip("'")
                minikube_ip_result = subprocess.run(
                    ["minikube", "ip"],
                    capture_output=True,
                    text=True
                )
                if minikube_ip_result.returncode == 0:
                    minikube_ip = minikube_ip_result.stdout.strip()
                    typer.echo(f"FastAPI service: http://{minikube_ip}:{node_port}")
                else:
                    typer.echo("   Could not determine minikube IP")
            else:
                typer.echo("   Could not determine service URL. Check with: kubectl get svc fastapi-service")

        typer.echo("\n Deployment status:")
        subprocess.run(["kubectl", "get", "pods", "-l", "app=fastapi"] + ns)
        subprocess.run(["kubectl", "get", "svc", "-l", "app=fastapi"] + ns)
        
        return True
        
    except subprocess.CalledProcessError as e:
        typer.echo(f"Deployment failed: {e.stderr}")
        return False
    except FileNotFoundError:
        typer.echo("kubectl command not found. Please install kubectl first.")
        return False


def load_image_to_minikube(image_name: str) -> bool:
    """
    Load a Docker image into minikube if it exists locally.
    
    Args:
        image_name: Name of the Docker image to load
        
    Returns:
        True if image was loaded or already exists, False otherwise
    """
    # Check if image exists locally
    result = subprocess.run(
        ["docker", "images", "-q", image_name],
        capture_output=True,
        text=True
    )
    
    if not result.stdout.strip():
        typer.echo(f"⚠️  Image '{image_name}' not found locally")
        typer.echo(f"   Build it first: docker build -t {image_name} .")
        return False
    
    # Check if image is already in minikube
    result = subprocess.run(
        ["minikube", "image", "ls"],
        capture_output=True,
        text=True
    )
    
    if image_name in result.stdout:
        typer.echo(f"✅ Image '{image_name}' already in minikube")
        return True
    
    # Load image into minikube
    typer.echo(f"📦 Loading image '{image_name}' into minikube...")
    result = subprocess.run(
        ["minikube", "image", "load", image_name],
        check=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        typer.echo(f"✅ Image '{image_name}' loaded into minikube")
        return True
    else:
        typer.echo(f"❌ Failed to load image: {result.stderr}")
        return False