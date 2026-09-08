# Cost Estimates

deployml integrates with [Infracost](https://www.infracost.io) to show infrastructure costs. Both commands read your Terraform configuration — they price always-on resources like Cloud SQL accurately, but usage-based services (BigQuery, GCS, Cloud Run) show $0 since costs depend on actual usage. Check the GCP Billing Console for real usage charges.

## Setup

```bash
brew install infracost
infracost auth login
```

Run `deployml doctor` to confirm infracost is installed and authenticated.

## Commands

**Before deploying** — estimates cost from your config without touching any infrastructure:
```bash
deployml estimate
```

**While deployed** — scans your actual deployed Terraform workspace:
```bash
deployml costs
```

Both commands show a breakdown of which resources cost money and how much.

## Cost shown during deploy

`deployml deploy` automatically runs a cost estimate after `terraform plan` and shows it before the confirmation prompt:
```
 Deploy stack? Monthly cost: ~$34.55 USD [y/N]:
```

## Configuration

```yaml
cost_analysis:
  enabled: true             # set to false to skip (default: true)
  warning_threshold: 50.0   # warn if monthly cost exceeds this (default: 100.0)
```

## Typical costs (Cloud Run stack)

A standard MLflow + FastAPI + Grafana deployment runs around **$34/month**, almost entirely Cloud SQL. Cloud Run, BigQuery, and GCS scale to zero and cost nothing at idle.

- Cloud Run services cost $10-30 per month depending on traffic.  
- Cloud SQL PostgreSQL ranges from $7/month for small instances to $25+ for production.  
- Google Cloud Storage costs approximately $0.020 per GB per month.   
- BigQuery storage costs $0.020 per GB per month with query costs based on data scanned.  
- Cloud VMs cost approximately $25 per month for medium instances.   
- GKE clusters have no management fee, but you pay for VM instances and load balancers. MLflow on GKE also provisions a small PersistentDisk for its data, a few cents per GB-month. Note that GKE can get expensive quickly.



## Cost Optimization

Here are some tips to keep the costs low while you are learning:  

- Use SQLite instead of Cloud SQL whenever possible, particularly for development purposes and when your data is small. Set `backend_store_uri: sqlite` instead of `postgresql` to eliminate the Cloud SQL instance entirely. The minikube and GKE MLflow paths already do this, sqlite on a PersistentVolumeClaim, so they avoid the always-on Cloud SQL cost.  
- Always run `deployml destroy` when you are done — Cloud SQL bills continuously, whether or not anyone is using it.
- Enable auto-teardown to prevent forgotten deployments. 
- Use Cloud Run for variable workloads to take advantage of scale-to-zero pricing.
