# 🔍 Explainability & Fairness Monitoring: Complete Workflow

## 📋 Overview

This document explains how explainability and fairness monitoring work from config to deployment.

---

## 1️⃣ What Gets Deployed?

When a user enables explainability and fairness monitoring, DeployML deploys:

```
┌─────────────────────────────────────────────────────────────┐
│                    User's Existing Stack                     │
├─────────────────────────────────────────────────────────────┤
│ ✅ FastAPI (Model Serving)                                  │
│ ✅ MLflow (Experiment Tracking)                             │
│ ✅ PostgreSQL (Metrics Database)                            │
│ ✅ Grafana (Monitoring Dashboards)                          │
└─────────────────────────────────────────────────────────────┘
                           +
┌─────────────────────────────────────────────────────────────┐
│                    NEW: Monitoring Jobs                      │
├─────────────────────────────────────────────────────────────┤
│ 🆕 Explainability Monitor (Cloud Run Job)                   │
│    - Runs daily (or custom schedule)                        │
│    - Analyzes SHAP values                                   │
│    - Tracks feature importance                              │
│    - Detects importance shifts                              │
│                                                              │
│ 🆕 Fairness Checker (Cloud Run Job)                         │
│    - Runs daily (or custom schedule)                        │
│    - Calculates fairness metrics                            │
│    - Detects bias across groups                             │
│    - Alerts on violations                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2️⃣ User Configuration (deployml-config.yaml)

### **Minimal Configuration**

```yaml
name: ml-monitoring-stack
provider:
  name: gcp
  project_id: mldeploy-468919
  region: us-west1

deployment:
  type: cloud_run

stack:
  # Existing components
  - experiment_tracking:
      name: mlflow
      params:
        image: gcr.io/mldeploy-468919/mlflow-server:latest
  
  - model_serving:
      name: fastapi
      params:
        image: gcr.io/mldeploy-468919/model-api:latest
  
  - model_monitoring:
      name: grafana
      params:
        image: gcr.io/mldeploy-468919/grafana:latest
  
  # NEW: Explainability monitoring (minimal config)
  - explainability_monitoring:
      name: shap_monitor
      params:
        image: gcr.io/mldeploy-468919/explainability-monitor:latest
  
  # NEW: Fairness monitoring (minimal config)
  - fairness_monitoring:
      name: fairness_checker
      params:
        image: gcr.io/mldeploy-468919/fairness-checker:latest
        sensitive_attributes:
          - location
          - age_group
```

### **Full Configuration (All Options)**

```yaml
stack:
  # Explainability monitoring with all options
  - explainability_monitoring:
      name: shap_monitor
      params:
        # Required
        image: gcr.io/mldeploy-468919/explainability-monitor:latest
        
        # Optional (with defaults)
        schedule: "0 6 * * *"                    # Daily at 6 AM (default)
        importance_shift_threshold: 0.3          # Detect shifts > 30% (default)
        track_feature_importance: true           # Track over time (default)
        alert_on_importance_shift: true          # Send alerts (default)
        alert_webhook_url: "https://hooks.slack.com/services/..."  # Optional
  
  # Fairness monitoring with all options
  - fairness_monitoring:
      name: fairness_checker
      params:
        # Required
        image: gcr.io/mldeploy-468919/fairness-checker:latest
        sensitive_attributes:                    # REQUIRED
          - location
          - age_group
        
        # Optional (with defaults)
        schedule: "0 8 * * *"                    # Daily at 8 AM (default)
        fairness_metrics:                        # Metrics to calculate (default)
          - demographic_parity
          - disparate_impact
        demographic_parity_threshold: 0.1        # Max allowed difference (default)
        disparate_impact_threshold: 0.8          # Min ratio (80% rule, default)
        alert_on_violation: true                 # Send alerts (default)
        alert_webhook_url: "https://hooks.slack.com/services/..."  # Optional
        protected_groups:                        # Optional: specify protected groups
          location:
            - rural
            - suburban
          age_group:
            - young
```

---

## 3️⃣ What Happens When User Runs `deployml deploy`?

### **Step-by-Step Process**

```bash
$ deployml deploy -c config.yaml
```

#### **Phase 1: Configuration Parsing**
```
DeployML reads config.yaml
    ↓
Detects explainability_monitoring component
    ↓
Detects fairness_monitoring component
    ↓
Validates required fields (image, sensitive_attributes)
```

#### **Phase 2: Terraform Generation**
```
DeployML copies Terraform modules:
    ├── explainability_monitoring/cloud/gcp/cloud_run/
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    │
    └── fairness_monitoring/cloud/gcp/cloud_run/
        ├── main.tf
        ├── variables.tf
        └── outputs.tf

DeployML generates main.tf with:
    - Cloud Run Job for explainability
    - Cloud Run Job for fairness
    - Cloud Schedulers for both
    - IAM permissions
    - Database connection strings
```

#### **Phase 3: Terraform Deployment**
```
Terraform creates in Google Cloud:

1. Cloud Run Job: explainability-monitor
   - Container: gcr.io/project/explainability-monitor:latest
   - Environment variables:
     * DATABASE_URL: postgresql://...
     * IMPORTANCE_SHIFT_THRESHOLD: 0.3
     * TRACK_FEATURE_IMPORTANCE: true
   
2. Cloud Scheduler: explainability-monitor-cron
   - Schedule: 0 6 * * * (daily at 6 AM)
   - Target: explainability-monitor job
   
3. Cloud Run Job: fairness-checker
   - Container: gcr.io/project/fairness-checker:latest
   - Environment variables:
     * DATABASE_URL: postgresql://...
     * SENSITIVE_ATTRIBUTES: ["location", "age_group"]
     * FAIRNESS_METRICS: ["demographic_parity", "disparate_impact"]
   
4. Cloud Scheduler: fairness-checker-cron
   - Schedule: 0 8 * * * (daily at 8 AM)
   - Target: fairness-checker job
   
5. IAM Permissions
   - Allow schedulers to invoke jobs
   - Allow jobs to access PostgreSQL
```

#### **Phase 4: Output**
```
✅ Deployment complete!

📦 DeployML Outputs:
  explainability_monitoring_job_name: explainability-monitor
  explainability_monitoring_job_url: https://console.cloud.google.com/run/jobs/details/us-west1/explainability-monitor
  explainability_monitoring_schedule: 0 6 * * *
  
  fairness_monitoring_job_name: fairness-checker
  fairness_monitoring_job_url: https://console.cloud.google.com/run/jobs/details/us-west1/fairness-checker
  fairness_monitoring_schedule: 0 8 * * *
  fairness_monitoring_sensitive_attributes: ['location', 'age_group']
```

---

## 4️⃣ How Explainability Monitoring Works

### **Runtime Flow**

```
Cloud Scheduler triggers at 6 AM daily
    ↓
Cloud Run starts explainability-monitor container
    ↓
Python script (monitor.py) executes:
    
    1. Connect to PostgreSQL database
       ↓
    2. Fetch SHAP values from last 7 days
       SELECT * FROM explainability_logs WHERE timestamp > NOW() - INTERVAL '7 days'
       ↓
    3. Calculate feature importance
       - Average absolute SHAP values per feature
       - Normalize to sum to 1.0
       ↓
    4. Compare with previous run
       SELECT * FROM feature_importance_log ORDER BY timestamp DESC LIMIT 1
       ↓
    5. Detect shifts
       - If |current - previous| > 0.3 → SHIFT DETECTED
       ↓
    6. Save results
       INSERT INTO feature_importance_log (feature_name, importance_score, ...)
       ↓
    7. Send alerts (if configured)
       POST to alert_webhook_url with shift details
    ↓
Container stops, job completes
```

### **Database Tables Used**

```sql
-- Input: SHAP values logged by FastAPI
explainability_logs (
    id, request_id, timestamp,
    shap_bedrooms, shap_bathrooms, shap_sqft, shap_age,
    base_value, prediction_value
)

-- Output: Feature importance over time
feature_importance_log (
    id, timestamp, feature_name,
    importance_score, rank, calculation_method
)
```

### **Example Output**

```
🔍 Starting Explainability Monitoring
📊 Calculating feature importance...

✅ Current Feature Importance:
   sqft        : 0.452
   bedrooms    : 0.285
   bathrooms   : 0.178
   age         : 0.085

⚠️  FEATURE IMPORTANCE SHIFT DETECTED!
   Changes:
   sqft        : +0.120  (was 0.332, now 0.452)
   bedrooms    : -0.095  (was 0.380, now 0.285)

📊 Monitoring Summary:
   Records analyzed: 1,247
   Most important feature: sqft
```

---

## 5️⃣ How Fairness Monitoring Works

### **Runtime Flow**

```
Cloud Scheduler triggers at 8 AM daily
    ↓
Cloud Run starts fairness-checker container
    ↓
Python script (checker.py) executes:
    
    1. Connect to PostgreSQL database
       ↓
    2. Fetch predictions from last 7 days
       SELECT features, prediction FROM prediction_logs 
       WHERE timestamp > NOW() - INTERVAL '7 days'
       ↓
    3. For each sensitive attribute (e.g., "location"):
       
       a) Calculate demographic parity
          - Group by location
          - Calculate positive rate per group
          - Max difference between groups
          
       b) Calculate disparate impact (if 2 groups)
          - Protected group rate / Reference group rate
          - Should be > 0.8
       ↓
    4. Detect violations
       - Demographic parity diff > 0.1 → VIOLATION
       - Disparate impact < 0.8 → VIOLATION
       ↓
    5. Save results
       INSERT INTO fairness_metrics (metric_name, group_attribute, ...)
       ↓
    6. Send alerts (if violations found)
       POST to alert_webhook_url with violation details
    ↓
Container stops, job completes
```

### **Database Tables Used**

```sql
-- Input: Predictions with features
prediction_logs (
    id, timestamp, features,  -- features contains sensitive attributes
    prediction, model_version
)

-- Output: Fairness metrics
fairness_metrics (
    id, timestamp, metric_name,
    group_attribute, group_value, metric_value,
    threshold_violated, period_start, period_end, sample_size
)
```

### **Example Output**

```
⚖️  Starting Fairness Monitoring

📊 Analyzing fairness for attribute: location
   Groups found: ['urban', 'rural', 'suburban']

   Demographic Parity:
      Max difference: 0.145 (threshold: 0.1)
      Violation: YES ⚠️
      
   Group positive rates:
      urban    : 0.621
      rural    : 0.476  ← 14.5% lower!
      suburban : 0.598

⚖️  Fairness Monitoring Summary:
   Records analyzed: 1,247
   Attributes checked: 2
   Metrics calculated: 4
   Violations found: 1

⚠️  FAIRNESS VIOLATIONS DETECTED!
   Alert sent to Slack webhook
```

---

## 6️⃣ What the User Sees in Grafana

After deployment, users can query the new tables in Grafana:

### **Explainability Dashboard**

```sql
-- Feature importance over time
SELECT 
  timestamp,
  feature_name,
  importance_score
FROM feature_importance_log
WHERE timestamp > NOW() - INTERVAL '30 days'
ORDER BY timestamp;
```

**Visualization**: Line chart showing how feature importance changes over time

### **Fairness Dashboard**

```sql
-- Fairness violations
SELECT 
  timestamp,
  metric_name,
  group_attribute,
  group_value,
  metric_value,
  threshold_violated
FROM fairness_metrics
WHERE timestamp > NOW() - INTERVAL '30 days'
  AND threshold_violated = true
ORDER BY timestamp DESC;
```

**Visualization**: Table showing all fairness violations with alerts

---

## 7️⃣ Required User Inputs

### **For Explainability Monitoring**

| Field | Required? | Default | Description |
|-------|-----------|---------|-------------|
| `image` | ✅ Yes | - | Docker image URL |
| `schedule` | ❌ No | `"0 6 * * *"` | Cron schedule |
| `importance_shift_threshold` | ❌ No | `0.3` | Shift detection threshold |
| `track_feature_importance` | ❌ No | `true` | Track over time |
| `alert_on_importance_shift` | ❌ No | `true` | Send alerts |
| `alert_webhook_url` | ❌ No | `""` | Slack/webhook URL |

### **For Fairness Monitoring**

| Field | Required? | Default | Description |
|-------|-----------|---------|-------------|
| `image` | ✅ Yes | - | Docker image URL |
| `sensitive_attributes` | ✅ Yes | - | List of attributes to monitor |
| `schedule` | ❌ No | `"0 8 * * *"` | Cron schedule |
| `fairness_metrics` | ❌ No | `["demographic_parity", "disparate_impact"]` | Metrics to calculate |
| `demographic_parity_threshold` | ❌ No | `0.1` | Max allowed difference |
| `disparate_impact_threshold` | ❌ No | `0.8` | Min required ratio |
| `alert_on_violation` | ❌ No | `true` | Send alerts |
| `alert_webhook_url` | ❌ No | `""` | Slack/webhook URL |
| `protected_groups` | ❌ No | `null` | Specify protected groups |

---

## 8️⃣ Infrastructure Created

When user deploys, Terraform creates:

### **Google Cloud Resources**

```
1. Cloud Run Jobs (2 total)
   ├── explainability-monitor
   │   - Memory: 512 MB
   │   - CPU: 1
   │   - Timeout: 600s (10 min)
   │   - Execution mode: Job
   │
   └── fairness-checker
       - Memory: 512 MB
       - CPU: 1
       - Timeout: 900s (15 min)
       - Execution mode: Job

2. Cloud Schedulers (2 total)
   ├── explainability-monitor-cron
   │   - Schedule: 0 6 * * *
   │   - Target: explainability-monitor job
   │   - HTTP trigger with OAuth
   │
   └── fairness-checker-cron
       - Schedule: 0 8 * * *
       - Target: fairness-checker job
       - HTTP trigger with OAuth

3. IAM Permissions
   - Service account with roles:
     * Cloud Run Invoker
     * Cloud SQL Client

4. Database Tables (added to existing PostgreSQL)
   - explainability_logs (if not exists)
   - feature_importance_log (if not exists)
   - fairness_metrics (if not exists)
```

### **Cost Estimation**

```
Explainability Monitor:
- Runs daily for ~30 seconds
- $0.00002/second * 30s * 30 days = $0.018/month

Fairness Checker:
- Runs daily for ~45 seconds
- $0.00002/second * 45s * 30 days = $0.027/month

Total: ~$0.05/month (essentially free!)
```

---

## 9️⃣ Testing & Verification

### **Manual Trigger (for testing)**

```bash
# Trigger explainability monitoring immediately
gcloud run jobs execute explainability-monitor \
  --region=us-west1 \
  --project=mldeploy-468919

# Trigger fairness checking immediately
gcloud run jobs execute fairness-checker \
  --region=us-west1 \
  --project=mldeploy-468919
```

### **Check Logs**

```bash
# View explainability logs
gcloud run jobs executions describe <execution-id> \
  --region=us-west1 --format=yaml

# View fairness logs
gcloud logging read "resource.type=cloud_run_job AND \
  resource.labels.job_name=fairness-checker" \
  --limit=50 --format=json
```

### **Verify Data**

```sql
-- In Grafana or psql
SELECT COUNT(*) FROM feature_importance_log;
SELECT COUNT(*) FROM fairness_metrics;
```

---

## 🎯 Complete Example

**User's config.yaml:**
```yaml
stack:
  - explainability_monitoring:
      name: shap_monitor
      params:
        image: gcr.io/mldeploy-468919/explainability-monitor:latest
        schedule: "0 6 * * *"
  
  - fairness_monitoring:
      name: fairness_checker
      params:
        image: gcr.io/mldeploy-468919/fairness-checker:latest
        sensitive_attributes: [location, age_group]
        schedule: "0 8 * * *"
```

**User runs:**
```bash
deployml deploy -c config.yaml
```

**Result:**
- ✅ 2 Cloud Run Jobs created
- ✅ 2 Cloud Schedulers configured
- ✅ Runs automatically every day
- ✅ Data visible in Grafana
- ✅ Alerts sent to Slack (if configured)

**That's it!** User gets production-grade explainability and fairness monitoring with ~10 lines of YAML! 🚀

