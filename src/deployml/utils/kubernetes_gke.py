import subprocess
import typer
from pathlib import Path
from typing import Optional, Dict
from jinja2 import Environment, FileSystemLoader
from deployml.utils.constants import TEMPLATE_DIR


def check_gke_cluster_connection(cluster_name: str, zone: Optional[str] = None, region: Optional[str] = None) -> bool:
    """Check if kubectl is connected to the GKE cluster."""
    try:
        result = subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            # Check if cluster name is in context
            context_result = subprocess.run(
                ["kubectl", "config", "current-context"],
                capture_output=True,
                text=True
            )
            return cluster_name in context_result.stdout or "gke" in context_result.stdout.lower()
        return False
    except Exception:
        return False


def connect_to_gke_cluster(
    project_id: str,
    cluster_name: str,
    zone: Optional[str] = None,
    region: Optional[str] = None
) -> bool:
    """Connect kubectl to a GKE cluster."""
    typer.echo(f"Connecting to GKE cluster: {cluster_name}...")
    
    try:
        if zone:
            cmd = [
                "gcloud", "container", "clusters", "get-credentials",
                cluster_name,
                "--zone", zone,
                "--project", project_id
            ]
        elif region:
            cmd = [
                "gcloud", "container", "clusters", "get-credentials",
                cluster_name,
                "--region", region,
                "--project", project_id
            ]
        else:
            typer.echo("Either zone or region must be provided")
            return False
        
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )
        typer.echo(f"Connected to cluster: {cluster_name}")
        return True
    except subprocess.CalledProcessError as e:
        typer.echo(f"Failed to connect to cluster: {e.stderr}")
        return False
    except FileNotFoundError:
        typer.echo("gcloud command not found. Please install gcloud CLI first.")
        return False


def push_image_to_gcr(image_name: str, gcr_image: str, project_id: str) -> bool:
    """Tag and push Docker image to Google Container Registry."""
    typer.echo(f"📦 Pushing image to GCR: {gcr_image}...")
    
    try:
        # Tag image
        tag_result = subprocess.run(
            ["docker", "tag", image_name, gcr_image],
            check=True,
            capture_output=True,
            text=True
        )
        
        # Push image
        push_result = subprocess.run(
            ["docker", "push", gcr_image],
            check=True,
            capture_output=True,
            text=True
        )
        
        typer.echo(f"Image pushed successfully: {gcr_image}")
        return True
    except subprocess.CalledProcessError as e:
        typer.echo(f"Failed to push image: {e.stderr}")
        return False
    except FileNotFoundError:
        typer.echo("docker command not found. Please install Docker first.")
        return False


def generate_fastapi_manifests_gke(
    output_dir: Path,
    image: str,
    project_id: str,
    mlflow_tracking_uri: Optional[str] = None,
    service_type: str = "LoadBalancer",
    push_image: bool = True,
) -> None:
    """
    Generate deployment.yaml and service.yaml for FastAPI on GKE.
    
    Args:
        output_dir: Directory where manifests will be created
        image: Docker image for FastAPI (local name)
        project_id: GCP project ID
        mlflow_tracking_uri: Optional MLflow tracking URI
        service_type: Kubernetes service type (LoadBalancer or ClusterIP)
        push_image: Whether to push image to GCR
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Convert local image to GCR format
    if not image.startswith("gcr.io/"):
        gcr_image = f"gcr.io/{project_id}/fastapi/fastapi:latest"
        if push_image:
            push_image_to_gcr(image, gcr_image, project_id)
        image = gcr_image
    else:
        gcr_image = image
    
    # Default values
    port = 8000
    replicas = 1
    cpu_request = "250m"
    memory_request = "512Mi"
    cpu_limit = "500m"
    memory_limit = "1Gi"
    service_name = "fastapi-service"
    
    # Load templates from files (reuse kubernetes_local templates)
    template_dir = TEMPLATE_DIR / "kubernetes_local"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    
    deployment_template = env.get_template("deployment.yaml.j2")
    service_template = env.get_template("service.yaml.j2")
    
    # Render deployment template
    deployment_yaml = deployment_template.render(
        image=gcr_image,
        port=port,
        replicas=replicas,
        cpu_request=cpu_request,
        memory_request=memory_request,
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
        mlflow_tracking_uri=mlflow_tracking_uri
    )
    
    # Update imagePullPolicy for GCR images
    deployment_yaml = deployment_yaml.replace("imagePullPolicy: Never", "imagePullPolicy: IfNotPresent")
    
    # Render service template with LoadBalancer
    service_yaml = f"""apiVersion: v1
kind: Service
metadata:
  name: {service_name}
  labels:
    app: fastapi
spec:
  type: {service_type}
  selector:
    app: fastapi
  ports:
  - port: {port}
    targetPort: {port}
    protocol: TCP
"""
    
    # Write files
    deployment_file = output_dir / "deployment.yaml"
    service_file = output_dir / "service.yaml"
    
    deployment_file.write_text(deployment_yaml)
    service_file.write_text(service_yaml)
    
    typer.echo(f"Generated GKE manifests in {output_dir}")
    typer.echo(f"   - {deployment_file}")
    typer.echo(f"   - {service_file}")


def generate_mlflow_manifests_gke(
    output_dir: Path,
    image: str,
    project_id: str,
    backend_store_uri: Optional[str] = None,
    artifact_root: Optional[str] = None,
    service_type: str = "LoadBalancer",
    push_image: bool = True,
) -> None:
    """
    Generate deployment.yaml and service.yaml for MLflow on GKE.
    
    Args:
        output_dir: Directory where manifests will be created
        image: Docker image for MLflow (local name)
        project_id: GCP project ID
        backend_store_uri: Optional backend store URI
        artifact_root: Optional artifact root path (GCS bucket)
        service_type: Kubernetes service type (LoadBalancer or ClusterIP)
        push_image: Whether to push image to GCR
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Convert local image to GCR format
    if not image.startswith("gcr.io/"):
        gcr_image = f"gcr.io/{project_id}/mlflow/mlflow:latest"
        if push_image:
            push_image_to_gcr(image, gcr_image, project_id)
        image = gcr_image
    else:
        gcr_image = image
    
    # Default values
    port = 5000
    replicas = 1
    cpu_request = "250m"
    memory_request = "512Mi"
    cpu_limit = "500m"
    memory_limit = "2Gi"  # Increased for GKE
    service_name = "mlflow-service"
    
    # Defaults if not provided
    if not backend_store_uri:
        backend_store_uri = "sqlite:///mlflow.db"
    if not artifact_root:
        artifact_root = "/mlflow-artifacts"
    
    # Load templates from files
    template_dir = TEMPLATE_DIR / "kubernetes_local"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    
    deployment_template = env.get_template("mlflow-deployment.yaml.j2")
    
    # Render deployment template
    deployment_yaml = deployment_template.render(
        image=gcr_image,
        port=port,
        replicas=replicas,
        cpu_request=cpu_request,
        memory_request=memory_request,
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
        backend_store_uri=backend_store_uri,
        artifact_root=artifact_root
    )
    
    # Update imagePullPolicy for GCR images
    deployment_yaml = deployment_yaml.replace("imagePullPolicy: Never", "imagePullPolicy: IfNotPresent")
    
    # Render service template with LoadBalancer
    service_yaml = f"""apiVersion: v1
kind: Service
metadata:
  name: {service_name}
  labels:
    app: mlflow
spec:
  type: {service_type}
  selector:
    app: mlflow
  ports:
  - port: {port}
    targetPort: {port}
    protocol: TCP
"""
    
    # Write files
    deployment_file = output_dir / "deployment.yaml"
    service_file = output_dir / "service.yaml"
    
    deployment_file.write_text(deployment_yaml)
    service_file.write_text(service_yaml)
    
    typer.echo(f"Generated MLflow GKE manifests in {output_dir}")
    typer.echo(f"   - {deployment_file}")
    typer.echo(f"   - {service_file}")


def deploy_to_gke(
    manifest_dir: Path,
    cluster_name: str,
    project_id: str,
    zone: Optional[str] = None,
    region: Optional[str] = None,
) -> bool:
    """
    Deploy manifests to GKE cluster using kubectl apply.
    
    Args:
        manifest_dir: Directory containing deployment.yaml and service.yaml
        cluster_name: GKE cluster name
        project_id: GCP project ID
        zone: GKE cluster zone (for zonal clusters)
        region: GKE cluster region (for regional clusters)
    """
    if not manifest_dir.exists():
        typer.echo(f"Directory not found: {manifest_dir}")
        return False
    
    deployment_file = manifest_dir / "deployment.yaml"
    service_file = manifest_dir / "service.yaml"
    
    if not deployment_file.exists() or not service_file.exists():
        typer.echo(f"Required manifest files not found in {manifest_dir}")
        return False
    
    # Connect to cluster if not already connected
    if not check_gke_cluster_connection(cluster_name, zone, region):
        if not connect_to_gke_cluster(project_id, cluster_name, zone, region):
            return False
    
    typer.echo("🚀 Applying Kubernetes manifests to GKE...")
    
    try:
        typer.echo(f"   Applying {deployment_file.name}...")
        result = subprocess.run(
            ["kubectl", "apply", "-f", str(deployment_file)],
            check=True,
            capture_output=True,
            text=True
        )
        typer.echo(f"   {result.stdout.strip()}")
        
        typer.echo(f"   Applying {service_file.name}...")
        result = subprocess.run(
            ["kubectl", "apply", "-f", str(service_file)],
            check=True,
            capture_output=True,
            text=True
        )
        typer.echo(f"   {result.stdout.strip()}")
        
        # Get service URL (LoadBalancer)
        typer.echo("\n⏳ Waiting for LoadBalancer IP...")
        typer.echo("   (This may take a few minutes)")
        
        # Wait for external IP
        import time
        max_wait = 300  # 5 minutes
        waited = 0
        service_name = service_file.stem.replace("service", "service")
        
        while waited < max_wait:
            result = subprocess.run(
                ["kubectl", "get", "svc", "-o", "jsonpath='{.items[?(@.spec.type==\"LoadBalancer\")].status.loadBalancer.ingress[0].ip}'"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0 and result.stdout.strip().strip("'"):
                external_ip = result.stdout.strip().strip("'")
                if external_ip and external_ip != "<none>":
                    # Get port
                    port_result = subprocess.run(
                        ["kubectl", "get", "svc", service_name, "-o", "jsonpath='{.spec.ports[0].port}'"],
                        capture_output=True,
                        text=True
                    )
                    port = port_result.stdout.strip().strip("'") or "5000"
                    typer.echo(f"\n✅ Service is available at: http://{external_ip}:{port}")
                    break
            
            time.sleep(5)
            waited += 5
            if waited % 30 == 0:
                typer.echo(f"   Still waiting... ({waited}s)")
        
        typer.echo("\n Deployment status:")
        subprocess.run(["kubectl", "get", "pods"])
        subprocess.run(["kubectl", "get", "svc"])
        
        return True
        
    except subprocess.CalledProcessError as e:
        typer.echo(f"Deployment failed: {e.stderr}")
        return False
    except FileNotFoundError:
        typer.echo("kubectl command not found. Please install kubectl first.")
        return False
