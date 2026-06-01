import os
import shutil
import subprocess
import typer
from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader

try:
    from importlib.metadata import version as _pkg_version
    _DEPLOYML_VERSION = _pkg_version("deployml-core")
except Exception:
    _DEPLOYML_VERSION = "0.0.42"

from deployml.utils.constants import TEMPLATE_DIR
from deployml.utils.kubernetes_local import ensure_namespace, ns_args
from deployml.utils.platform_compat import run_tool


def check_gke_cluster_connection(cluster_name: str, zone: Optional[str] = None, region: Optional[str] = None) -> bool:
    """Check if kubectl is connected to THIS specific GKE cluster.

    Earlier the function returned True if kubectl was connected to any GKE
    cluster, which silently applied manifests to the wrong cluster. Now we
    only return True if the current context contains the exact cluster name.
    """
    try:
        result = run_tool(
            "kubectl", ["cluster-info"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            context_result = run_tool(
                "kubectl", ["config", "current-context"],
                capture_output=True,
                text=True
            )
            return cluster_name in context_result.stdout
        return False
    except Exception:
        return False


def warn_if_gke_auth_plugin_missing() -> None:
    """kubectl needs gke-gcloud-auth-plugin to authenticate to GKE. The gcloud SDK
    installs it into the SDK bin directory, which is not always on the PATH that a
    subprocess inherits, especially on Windows. Warn with an actionable hint up
    front instead of letting kubectl fail later with a cryptic
    "executable gke-gcloud-auth-plugin not found"."""
    if shutil.which("gke-gcloud-auth-plugin"):
        return
    typer.echo(
        "WARNING: gke-gcloud-auth-plugin was not found on PATH. kubectl cannot "
        "authenticate to GKE without it."
    )
    typer.echo("   Install it: gcloud components install gke-gcloud-auth-plugin")
    if os.name == "nt":
        typer.echo(
            "   Then add the gcloud SDK bin directory to PATH, typically "
            "%LOCALAPPDATA%\\Google\\Cloud SDK\\google-cloud-sdk\\bin or "
            "C:\\Program Files (x86)\\Google\\Cloud SDK\\google-cloud-sdk\\bin."
        )


def disk_ref_from_volume_handle(volume_handle):
    """Parse a GCE PD CSI volume handle into (disk_name, location_flag, location).

    Handles zonal "projects/P/zones/Z/disks/NAME" and regional
    "projects/P/regions/R/disks/NAME" forms. Returns None when the string is not a
    GCE PD handle, so callers can skip cleanup safely.
    """
    if not volume_handle:
        return None
    parts = volume_handle.strip().strip("/").split("/")
    if "disks" not in parts:
        return None
    di = parts.index("disks")
    if di + 1 >= len(parts):
        return None
    disk_name = parts[di + 1]
    if "zones" in parts:
        return (disk_name, "--zone", parts[parts.index("zones") + 1])
    if "regions" in parts:
        return (disk_name, "--region", parts[parts.index("regions") + 1])
    return None


def get_pvc_volume_handle(pvc_name, namespace=None):
    """Return the CSI volume handle of the PV bound to pvc_name, or None.

    Must be called while the PVC still exists, since it follows the PVC to its
    bound PV and reads the PV's CSI volume handle. Used by gke-destroy to capture
    the backing PersistentDisk before teardown.
    """
    ns = ["-n", namespace] if namespace and namespace != "default" else []
    pv = run_tool(
        "kubectl",
        ["get", "pvc", pvc_name, "-o", "jsonpath={.spec.volumeName}"] + ns,
        capture_output=True, text=True,
    )
    pv_name = (pv.stdout or "").strip()
    if pv.returncode != 0 or not pv_name:
        return None
    handle = run_tool(
        "kubectl",
        ["get", "pv", pv_name, "-o", "jsonpath={.spec.csi.volumeHandle}"],
        capture_output=True, text=True,
    )
    vh = (handle.stdout or "").strip()
    return vh or None


def delete_gce_disk_if_exists(project, disk_ref) -> bool:
    """Best-effort delete of a specific GCE PersistentDisk.

    disk_ref is (disk_name, location_flag, location) as returned by
    disk_ref_from_volume_handle. If the disk is already gone, for example the CSI
    driver reclaimed it before the cluster was deleted, describe fails and no
    delete is issued. Only ever touches the one disk passed in, so it cannot
    affect unrelated disks. Returns True if the disk is absent afterward.
    """
    disk_name, loc_flag, loc = disk_ref
    describe = run_tool(
        "gcloud",
        ["compute", "disks", "describe", disk_name, loc_flag, loc,
         "--project", project, "--format=value(name)"],
        capture_output=True, text=True,
    )
    if describe.returncode != 0:
        return True
    typer.echo(f" Removing orphaned persistent disk {disk_name}...")
    run_tool(
        "gcloud",
        ["compute", "disks", "delete", disk_name, loc_flag, loc,
         "--project", project, "--quiet"],
        capture_output=True, text=True,
    )
    verify = run_tool(
        "gcloud",
        ["compute", "disks", "describe", disk_name, loc_flag, loc,
         "--project", project, "--format=value(name)"],
        capture_output=True, text=True,
    )
    return verify.returncode != 0


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
        
        result = run_tool(
            cmd[0], cmd[1:],
            check=True,
            capture_output=True,
            text=True
        )
        typer.echo(f"Connected to cluster: {cluster_name}")
        # kubectl will now need the GKE auth plugin; warn early if it is missing.
        warn_if_gke_auth_plugin_missing()
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
        tag_result = run_tool(
            "docker", ["tag", image_name, gcr_image],
            check=True,
            capture_output=True,
            text=True
        )

        # Push image
        push_result = run_tool(
            "docker", ["push", gcr_image],
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
    
    # Convert local image to GCR format. Pin tag to the deployml version to
    # avoid the :latest drift bug that bites the Cloud Run path the same way.
    if not image.startswith("gcr.io/"):
        gcr_image = f"gcr.io/{project_id}/fastapi/fastapi:v{_DEPLOYML_VERSION}"
        if push_image:
            push_image_to_gcr(image, gcr_image, project_id)
        image = gcr_image
    else:
        gcr_image = image

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
    use_pvc: bool = True,
    pvc_size: str = "5Gi",
) -> None:
    """
    Generate deployment.yaml, service.yaml, and optionally pvc.yaml for MLflow on GKE.

    Args:
        output_dir: Directory where manifests will be created
        image: Docker image for MLflow (local name)
        project_id: GCP project ID
        backend_store_uri: Optional backend store URI
        artifact_root: Optional artifact root path (GCS bucket)
        service_type: Kubernetes service type (LoadBalancer or ClusterIP)
        push_image: Whether to push image to GCR
        use_pvc: When True, provision a PersistentVolumeClaim so experiment data
          survives pod restarts. Without it MLflow stores sqlite in the container
          filesystem and loses everything when the pod is rescheduled.
        pvc_size: PVC size when use_pvc=True.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Convert local image to GCR format. Pin tag to the deployml version.
    if not image.startswith("gcr.io/"):
        gcr_image = f"gcr.io/{project_id}/mlflow/mlflow:v{_DEPLOYML_VERSION}"
        if push_image:
            push_image_to_gcr(image, gcr_image, project_id)
        image = gcr_image
    else:
        gcr_image = image

    port = 5000
    replicas = 1
    cpu_request = "250m"
    memory_request = "512Mi"
    cpu_limit = "500m"
    memory_limit = "2Gi"  # Increased for GKE
    service_name = "mlflow-service"
    
    # Defaults if not provided. Put sqlite on the mounted volume (4 slashes =
    # absolute /mlflow-artifacts/mlflow.db) so the backend store persists with
    # use_pvc. A relative sqlite:///mlflow.db would sit in the ephemeral
    # container filesystem and be lost on restart.
    if not backend_store_uri:
        backend_store_uri = (
            "sqlite:////mlflow-artifacts/mlflow.db" if use_pvc else "sqlite:///mlflow.db"
        )
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
        artifact_root=artifact_root,
        use_pvc=use_pvc,
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

    if use_pvc:
        pvc_template = env.get_template("mlflow-pvc.yaml.j2")
        pvc_yaml = pvc_template.render(pvc_size=pvc_size)
        pvc_file = output_dir / "pvc.yaml"
        pvc_file.write_text(pvc_yaml)
        typer.echo(f"   - {pvc_file}  (PersistentVolumeClaim, {pvc_size})")


def deploy_to_gke(
    manifest_dir: Path,
    cluster_name: str,
    project_id: str,
    zone: Optional[str] = None,
    region: Optional[str] = None,
    namespace: Optional[str] = None,
) -> bool:
    """
    Deploy manifests to GKE cluster using kubectl apply.

    Args:
        manifest_dir: Directory containing deployment.yaml and service.yaml
        cluster_name: GKE cluster name
        project_id: GCP project ID
        zone: GKE cluster zone (for zonal clusters)
        region: GKE cluster region (for regional clusters)
        namespace: Target namespace. Default keeps the default namespace; pass a
          value to isolate this stack. MLflow and FastAPI must share a namespace
          for in-cluster service DNS to resolve.
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
    ensure_namespace(namespace)
    ns = ns_args(namespace)

    try:
        # Apply the PVC first so the deployment can bind it on first schedule.
        pvc_file = manifest_dir / "pvc.yaml"
        if pvc_file.exists():
            typer.echo(f"   Applying {pvc_file.name}...")
            result = run_tool(
                "kubectl", ["apply", "-f", str(pvc_file)] + ns,
                check=True,
                capture_output=True,
                text=True
            )
            typer.echo(f"   {result.stdout.strip()}")

        typer.echo(f"   Applying {deployment_file.name}...")
        result = run_tool(
            "kubectl", ["apply", "-f", str(deployment_file)] + ns,
            check=True,
            capture_output=True,
            text=True
        )
        typer.echo(f"   {result.stdout.strip()}")

        typer.echo(f"   Applying {service_file.name}...")
        result = run_tool(
            "kubectl", ["apply", "-f", str(service_file)] + ns,
            check=True,
            capture_output=True,
            text=True
        )
        typer.echo(f"   {result.stdout.strip()}")
        
        # Get service URL (LoadBalancer)
        typer.echo("\n⏳ Waiting for LoadBalancer IP...")
        typer.echo("   (This may take a few minutes)")
        
        # Wait for external IP. Earlier code did service_file.stem.replace("service", "service")
        # which is a no-op and then queried kubectl for service "service" which is wrong.
        # Read the actual service name from the rendered manifest instead.
        import time, yaml as _yaml
        max_wait = 300
        waited = 0
        try:
            svc_doc = _yaml.safe_load(service_file.read_text())
            service_name = svc_doc.get("metadata", {}).get("name", "")
        except Exception:
            service_name = ""

        # Without a concrete service name we cannot safely target one service.
        # Querying every service and guessing an IP risks reporting the wrong
        # endpoint, so bail out and let the user inspect manually instead.
        if not service_name:
            typer.echo("   Could not read the service name from service.yaml; "
                       "skipping IP wait. Run: kubectl get svc")
            waited = max_wait

        while waited < max_wait:
            ip_query = "{.status.loadBalancer.ingress[0].ip}"
            cmd = ["kubectl", "get", "svc", service_name,
                   "-o", f"jsonpath={ip_query}"] + ns
            result = run_tool(cmd[0], cmd[1:], capture_output=True, text=True)

            external_ip = result.stdout.strip().strip("'")
            if result.returncode == 0 and external_ip and external_ip != "<none>":
                port_query = "{.spec.ports[0].port}"
                port_cmd = ["kubectl", "get", "svc", service_name,
                            "-o", f"jsonpath={port_query}"] + ns
                port_result = run_tool(port_cmd[0], port_cmd[1:], capture_output=True, text=True)
                port = port_result.stdout.strip().strip("'") or "5000"
                typer.echo(f"\n Service is available at: http://{external_ip}:{port}")
                break

            time.sleep(5)
            waited += 5
            if waited % 30 == 0:
                typer.echo(f"   Still waiting... ({waited}s)")
        
        typer.echo("\n Deployment status:")
        run_tool("kubectl", ["get", "pods"] + ns)
        run_tool("kubectl", ["get", "svc"] + ns)

        return True
        
    except subprocess.CalledProcessError as e:
        typer.echo(f"Deployment failed: {e.stderr}")
        return False
    except FileNotFoundError:
        typer.echo("kubectl command not found. Please install kubectl first.")
        return False
