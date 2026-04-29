## VM Deployment Guide (GCP VM)

This guide is designed to help setup and run the deployment of Deployml after the initial Deployml prerequisite have been met. 

### Configuration

To start create a configuration YAML describing your VM stack. You can start from the example:

```bash
cp example/config/gcp-cloud-vm-sample.yaml ./vm-stack.yaml
```

Key fields in `vm-stack.yaml`:

- provider: `name`, `project_id`, `region`, `zone`
- deployment: `type: cloud_vm`
- stack stages and params (MLflow, artifact bucket, Feast, Grafana, etc.)

Minimal VM example (edit values to match your project):

```yaml
name: gcp-mlops-stack-mlflow-vm
provider:
  name: gcp
  project_id: YOUR_PROJECT_ID
  region: YOUR_CHOSEN_REGION
  zone: YOUR_CHOSEN_ZONE
cost_analysis:
  enabled: true
  warning_threshold: 50.0
  currency: "USD"
deployment:
  type: cloud_vm
stack:
  - experiment_tracking:
      name: mlflow
      params:
        service_name: mlflow-server-postgres-vm
        vm_name: mlflow-postgres-vm-instance
        machine_type: e2-medium
        disk_size_gb: 20
        mlflow_port: 5000
        allow_public_access: true
        fastapi_port: 8000
        fastapi_app_source: "template"
  - artifact_tracking:
      name: mlflow
      params:
        artifact_bucket: mlflow-artifact-bucket-postgres-2
        create_artifact_bucket: true
  - model_registry:
      name: mlflow
      params:
  
```

Notes:

- If `artifact_bucket` is omitted, the CLI will generate a unique bucket name and set it up.
- If `model_registry.params.backend_store_uri` starts with `postgresql`, the CLI will automatically include Cloud SQL Postgres in the deployment plan and wire dependencies.

### Deploy

Run the deploy command. It will generate Terraform files under `.deployml/`, run a Terraform plan, perform optional cost analysis, and then apply:

```bash
deployml deploy --config-path vm-stack.yaml
```
- `--config-path` can be replaced with `-c` to simplify the deploymenet command.
Flags:

- `-y` or `--yes` to skip confirmation prompts.

What this does:

- Generates Terraform from templates for `cloud_vm` into `.deployml/<name>/terraform`
- Initializes and plans Terraform
- Optionally runs cost analysis (if enabled)
- Applies the plan and prints friendly outputs (URLs, service endpoints, credentials when applicable)

This process should take an estimated 18 - 20 minutes to complete. 
Once the all Google Cloud tools are setup the Virtual Machine will begin downloading and configuring itself which will take another 15 - 18 minutes.

### Virtual Machine Setup 
Get the VM external IP from the outputs or via gcloud:

```bash
gcloud compute instances list --filter="name~'mlflow'" --format="get(networkInterfaces[0].accessConfigs[0].natIP)"
```

SSH to the VM:

```bash
gcloud compute ssh --zone YOUR_ZONE YOUR_VM_NAME
```

Once in the VM you can run:

```bash
journalctl -f
```
To see live updates as the VM continues its deployment. 
To see if Deployment has been successful run the following Docker Command to see the status of all your Docker Containers.

```bash
sudo docker ps
```
If all containers show healthy all tools have been successfully deployed and are ready for use. 

### Outputs and Access

After a successful deploy, the CLI prints an "DeployML Outputs" section with key values. Typical endpoints and how to access them:

- MLflow UI: exposed on the VM at port 5000 (use the VM external IP). Example: `http://<VM_EXTERNAL_IP>:5000`
- FastAPI app (template): port 8000 → `http://<VM_EXTERNAL_IP>:8000`
- Feast server (inside VM Docker): port 6566 (access over SSH tunnel or within the VM)
- Grafana (if enabled): port 3000 → `http://<VM_EXTERNAL_IP>:3000`


### MLFlow

Use the link found in the DeployML output to access MLFlow. 
To be able to connect to MLFlow all you need to change in your logging files is:
```
mlflow.set_tracking_uri(EXTERNAL_VM_IP:5000)
```
### Feast on the VM

Once the VM is up, you can configure Feast and materialize data. See the detailed guide:

- `README_vm_FEAST.md` in the repo root (end-to-end walkthrough for setting up registry/online store and loading parquet).

### Grafana on the VM

Use the link found in the DeployML output to access Grafana. 
To Login the following is the default login and can be changed:
```
username: Admin  | password: Admin
```
Once logged in you can connect to the postgressql database by going to:
```
connections -> PostgresSQL -> Add New Datasource
```
and filling in the following:
```
Host URL: Found in .tfstate file

Database name: default is mlflow

Username: default is mlflow

Password: found in .tfstate file

TLS/SSL Mode: Disable
```

The .tfstate file will be generated in the .deployml directory upon deployment. 
To find the needed information look for:
```
    "db_connection_string": {
      "value": "postgresql+psycopg2://mlflow:RANDOMLY_GENERATED_PASSWORD@POSTGRES_IP/mlflow",
      "type": "string",
      "sensitive": true
    },
```

### Airflow

Use the link found in the DeployML output to access Airflow. 
To login to airflow you will need to find the username and password from the deployment logs using while in the VM:
```bash
sudo docker logs airflow-webserver
```
and look for 
```
Simple auth manager | Password for user 'admin': RANDOM_GENERATED_PASSWORD
```


### Destroy and Cleanup

To destroy the deployed resources and optionally remove the local workspace:

```bash
deployml destroy --config-path vm-stack.yaml
```

You will be prompted to confirm. To also remove `.deployml/<name>` after destroying, re-run with `--clean-workspace` or confirm when prompted to clean Terraform state files.

Due to how GCP tears down systems you may need to run the destroy command twice to get a fully tear down. 

### Troubleshooting

- Authentication: If prompted, the CLI will run `gcloud auth application-default login` during deploy.
- Ports blocked: Ensure your VM firewall rules allow ingress on the ports you need (5000, 8000, 3000, 6566, etc.). The Terraform for `cloud_vm` opens required ports defined by your stack params.
- Artifact bucket missing: If you provide a bucket name, ensure it exists or set `create_artifact_bucket: true`.
- Postgres backend: When using `postgresql` backend for MLflow (and Feast SQL registry), Cloud SQL Postgres resources are created; teardown uses the CLI `destroy` command which also handles Cloud SQL dependencies.

### Known Bugs
- MLFlow does not successfully deploy due to not finding the right password. 
- `deployml destroy --config-path vm-stack.yaml` does not fully tear down the project.
