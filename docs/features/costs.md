# Cost Estimates

deployml integrates with Infracost to provide cost estimates before deploying your infrastructure, helping you manage cloud costs effectively in academic settings.

## Overview

Cost analysis runs automatically during deployment, showing monthly cost estimates for your entire stack, cost breakdowns by component, and warnings if costs exceed your configured threshold. The process analyzes your Terraform configuration before deployment, allowing you to adjust your configuration based on estimates.

## Setup

Install Infracost using Homebrew (macOS), shell script (Linux), or Chocolatey (Windows). Create a free Infracost account and authenticate using the command line to save your API key locally.

## Configuration

Cost analysis is enabled by default. Configure it in your YAML file to enable or disable cost analysis, set a warning threshold in USD (default $100/month), and choose the currency for cost display.

## Typical Costs

Cloud Run services cost $10-30 per month depending on traffic. Cloud SQL PostgreSQL ranges from $7/month for small instances to $25+ for production. Google Cloud Storage costs approximately $0.020 per GB per month. BigQuery storage costs $0.020 per GB per month with query costs based on data scanned. Cloud VMs cost approximately $25 per month for medium instances. GKE clusters have no management fee, but you pay for VM instances and load balancers.

A minimal development stack typically costs around $24 per month, while a standard production stack costs approximately $125 per month.

## Cost Optimization

Use SQLite instead of Cloud SQL for development, choose appropriate machine types, enable auto-teardown to prevent forgotten deployments, use Cloud Run for variable workloads to take advantage of scale-to-zero pricing, and optimize storage through lifecycle policies.

## Next Steps

- Review [Features Overview](overview.md) for component details
- Explore [MLOps Components](pipeline.md) for stack configuration
- Check [Tutorials](../tutorials/overview.md) for deployment examples
