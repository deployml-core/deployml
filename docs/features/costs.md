# Cost Estimates

deployml integrates with [Infracost](https://github.com/infracost/infracost){target="_blank"} to provide cost estimates before deploying your infrastructure, helping you manage cloud costs effectively in academic settings.

## Overview

Cost analysis runs automatically during deployment, showing monthly cost estimates for your entire stack, cost breakdowns by component, and warnings if costs exceed your configured threshold. The process analyzes your Terraform configuration before deployment, allowing you to adjust your configuration based on estimates.

## Setup

Install Infracost and register for a free API key using the instructions [here](https://www.infracost.io/docs/#quick-start){target="_blank"}. 

## Configuration

Cost analysis is enabled by default. Configure it in your YAML file to enable or disable cost analysis, set a warning threshold in USD (default $100/month), and choose the currency for cost display.

Here is an example of what this might look like:
```yaml
cost_analysis:
  enabled: true              # Enable/disable cost analysis (default: true)
  warning_threshold: 50.0    # Warn if monthly cost exceeds this amount (default: 100.0)
  currency: "USD"   
  bucket_amount: 200        # GB stored across GCS buckets
  cloudsql_amount: 50       # GB of Cloud SQL storage
```

## Typical Costs

Here are estimated typical costs for several **GCP** services, but please do not simply believe these numbers without keeping track of costs yourself.

- Cloud Run services cost $10-30 per month depending on traffic.  
- Cloud SQL PostgreSQL ranges from $7/month for small instances to $25+ for production.  
- Google Cloud Storage costs approximately $0.020 per GB per month.   
- BigQuery storage costs $0.020 per GB per month with query costs based on data scanned.  
- Cloud VMs cost approximately $25 per month for medium instances.   
- GKE clusters have no management fee, but you pay for VM instances and load balancers. Note that the GKE can get very expensive very quickly.



## Cost Optimization

Here are some tips to keep the costs low while you are learning:  

- Use SQLite instead of Cloud SQL whenever possible, particularly for development purposes and when your data is small.  
- Enable auto-teardown to prevent forgotten deployments. 
- Use Cloud Run for variable workloads to take advantage of scale-to-zero pricing.