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

## Keeping costs low

- Always `deployml destroy` when done — Cloud SQL bills continuously.
- Use `backend_store_uri: sqlite` instead of `postgresql` during development to eliminate Cloud SQL entirely.
