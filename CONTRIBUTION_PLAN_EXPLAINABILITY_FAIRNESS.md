# 🎯 DeployML Contribution Plan: Explainability & Fairness Monitoring

## Overview

Add explainability and fairness monitoring as **first-class features** of DeployML, allowing users to enable them with simple YAML configuration.

---

## 🏗️ Current DeployML Architecture

```
User writes YAML config
  ↓
deployml deploy --config-path config.yaml
  ↓
CLI reads config, generates Terraform from Jinja2 templates
  ↓
Terraform provisions: MLflow, Feast, Grafana, FastAPI, Cron jobs
  ↓
Services deployed to GCP Cloud Run/VM
```

**Key Components:**
- `src/deployml/cli/cli.py` - Main CLI logic
- `src/deployml/terraform/modules/` - Terraform modules for each service
- `src/deployml/templates/gcp/` - Jinja2 templates for main.tf generation
- Stack components: `experiment_tracking`, `model_serving`, `model_monitoring`, `workflow_orchestration`

---

## 🎯 Proposed Feature: Explainability & Fairness

### **User Experience (After Contribution)**

Users can enable explainability and fairness in their config:

```yaml
name: ml-monitoring-stack
provider:
  name: gcp
  project_id: my-project
  region: us-west1

deployment:
  type: cloud_run

stack:
  # Existing components
  - experiment_tracking:
      name: mlflow
  
  - model_serving:
      name: fastapi
      params:
        image: gcr.io/my-project/model-api:latest
        service_name: house-price-api
        # NEW: Enable explainability
        enable_explainability: true
        explainer_method: shap  # or lime, integrated_gradients
  
  - model_monitoring:
      name: grafana
      params:
        image: gcr.io/my-project/grafana:latest
        service_name: monitoring-dashboard
  
  # NEW: Explainability monitoring
  - explainability_monitoring:
      name: shap_monitor
      params:
        schedule: "0 6 * * *"  # Daily at 6 AM
        track_feature_importance: true
        alert_on_importance_shift: true
        importance_shift_threshold: 0.3
  
  # NEW: Fairness monitoring
  - fairness_monitoring:
      name: fairness_checker
      params:
        schedule: "0 8 * * *"  # Daily at 8 AM
        sensitive_attributes:
          - location
          - age_group
        fairness_metrics:
          - demographic_parity
          - equal_opportunity
          - disparate_impact
        violation_threshold:
          demographic_parity: 0.1
          disparate_impact: 0.8
        alert_on_violation: true
```

### **What DeployML Will Deploy**

```
┌────────────────────────────────────────────────────────┐
│  FastAPI (Enhanced with SHAP)                         │
│  - Real-time SHAP value calculation                   │
│  - Logs explainability data to PostgreSQL             │
└────────────────────────────────────────────────────────┘
                        ↓
┌────────────────────────────────────────────────────────┐
│  PostgreSQL Database (New Tables)                      │
│  - explainability_logs                                 │
│  - fairness_metrics                                    │
│  - feature_importance_log                              │
└────────────────────────────────────────────────────────┘
                        ↓
┌────────────────────────────────────────────────────────┐
│  Cloud Run Jobs (New)                                  │
│  1. explainability-monitor: Tracks SHAP trends         │
│  2. fairness-checker: Detects bias                     │
└────────────────────────────────────────────────────────┘
                        ↓
┌────────────────────────────────────────────────────────┐
│  Grafana (Pre-configured Dashboards)                   │
│  - Explainability dashboard (auto-provisioned)         │
│  - Fairness dashboard (auto-provisioned)               │
└────────────────────────────────────────────────────────┘
```

---

## 📁 Files to Create/Modify

### **1. New Terraform Modules** (High Priority)

Create new modules for the monitoring jobs:

```
src/deployml/terraform/modules/
├── explainability_monitoring/
│   └── cloud/
│       └── gcp/
│           └── cloud_run/
│               ├── main.tf          # Cloud Run Job for explainability
│               ├── outputs.tf       # Job name, scheduler info
│               └── variables.tf     # Schedule, params
│
└── fairness_monitoring/
    └── cloud/
        └── gcp/
            └── cloud_run/
                ├── main.tf          # Cloud Run Job for fairness
                ├── outputs.tf       # Job name, scheduler info
                └── variables.tf     # Sensitive attrs, thresholds
```

**main.tf example** (explainability_monitoring):

```hcl
# Cloud Run Job for Explainability Monitoring
resource "google_cloud_run_v2_job" "explainability_monitor" {
  name     = "explainability-monitor"
  location = var.region
  project  = var.project_id

  template {
    template {
      containers {
        image = var.explainability_image
        
        env {
          name  = "DATABASE_URL"
          value = var.database_url
        }
        
        env {
          name  = "IMPORTANCE_SHIFT_THRESHOLD"
          value = var.importance_shift_threshold
        }
      }
    }
  }
}

# Cloud Scheduler to trigger the job
resource "google_cloud_scheduler_job" "explainability_schedule" {
  name        = "explainability-monitor-cron"
  description = "Trigger explainability monitoring"
  schedule    = var.schedule  # e.g., "0 6 * * *"
  time_zone   = "UTC"
  region      = var.region
  project     = var.project_id

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/explainability-monitor:run"
    
    oauth_token {
      service_account_email = var.service_account_email
    }
  }
}
```

### **2. Enhanced FastAPI Template** (High Priority)

Create enhanced FastAPI module with explainability support:

```
src/deployml/terraform/modules/
└── fastapi/
    └── cloud/
        └── gcp/
            └── cloud_run/
                ├── main.tf          # Modify to add SHAP env vars
                ├── outputs.tf       
                └── variables.tf     # Add enable_explainability flag
```

**Modified main.tf**:

```hcl
resource "google_cloud_run_service" "fastapi" {
  # ... existing config ...
  
  template {
    spec {
      containers {
        image = var.image
        
        # Existing env vars
        env {
          name  = "MLFLOW_TRACKING_URI"
          value = var.mlflow_url
        }
        
        # NEW: Explainability config
        dynamic "env" {
          for_each = var.enable_explainability ? [1] : []
          content {
            name  = "ENABLE_EXPLAINABILITY"
            value = "true"
          }
        }
        
        dynamic "env" {
          for_each = var.enable_explainability ? [1] : []
          content {
            name  = "EXPLAINER_METHOD"
            value = var.explainer_method
          }
        }
      }
    }
  }
}
```

### **3. Docker Images** (High Priority)

Create reference Docker images users can extend:

```
src/deployml/docker/
├── fastapi-explainability/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py              # FastAPI with SHAP support
│   └── explainability.py   # SHAP utilities
│
├── explainability-monitor/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── monitor.py          # Aggregates SHAP values
│
└── fairness-checker/
    ├── Dockerfile
    ├── requirements.txt
    └── checker.py          # Calculates fairness metrics
```

### **4. Enhanced Grafana with Dashboards** (Medium Priority)

Add pre-configured dashboards:

```
src/deployml/docker/grafana/
├── Dockerfile
├── dashboards/
│   └── dashboard.yaml
└── dashboard-definitions/
    ├── predictions.json
    ├── drift-monitoring.json
    ├── explainability.json       # NEW
    └── fairness.json              # NEW
```

### **5. CLI Updates** (Medium Priority)

Update CLI to recognize new stack components:

**File:** `src/deployml/cli/cli.py`

```python
# In deploy() function, add recognition for new components:

for stage in config.get("stack", []):
    for stage_name, tool in stage.items():
        # Existing handling...
        
        # NEW: Handle explainability_monitoring
        if stage_name == "explainability_monitoring":
            if tool.get("name") == "shap_monitor":
                # Ensure database connection is configured
                # Copy explainability_monitoring module
                pass
        
        # NEW: Handle fairness_monitoring  
        if stage_name == "fairness_monitoring":
            if tool.get("name") == "fairness_checker":
                # Validate sensitive_attributes are specified
                # Copy fairness_monitoring module
                pass
```

### **6. Database Schema** (High Priority)

Add SQL migrations/initialization:

```
src/deployml/sql/
├── init/
│   ├── 001_prediction_logs.sql      # Existing
│   ├── 002_explainability_logs.sql  # NEW
│   └── 003_fairness_metrics.sql     # NEW
```

**002_explainability_logs.sql**:

```sql
CREATE TABLE IF NOT EXISTS explainability_logs (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(50) REFERENCES prediction_logs(request_id),
    timestamp TIMESTAMP DEFAULT NOW(),
    model_version VARCHAR(50),
    shap_values JSONB,  -- Store as JSON for flexibility
    base_value FLOAT,
    prediction_value FLOAT,
    INDEX idx_timestamp (timestamp),
    INDEX idx_request_id (request_id)
);

CREATE TABLE IF NOT EXISTS feature_importance_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    model_version VARCHAR(50),
    feature_name VARCHAR(100),
    importance_score FLOAT,
    rank INTEGER,
    calculation_method VARCHAR(50),
    INDEX idx_timestamp (timestamp)
);
```

### **7. Documentation** (Medium Priority)

Add documentation:

```
docs/
├── features/
│   ├── explainability.md       # NEW
│   └── fairness.md             # NEW
└── tutorials/
    ├── explainability-setup.md # NEW
    └── fairness-setup.md       # NEW
```

### **8. Example Configs** (Low Priority)

Add example configurations:

```
example/
├── explainability-demo/
│   ├── deployml-config.yaml
│   ├── train.py
│   └── README.md
│
└── fairness-demo/
    ├── deployml-config.yaml
    ├── train.py
    └── README.md
```

---

## 🚀 Implementation Phases

### **Phase 1: Core Infrastructure** (Week 1)
- [x] Create Terraform modules for explainability_monitoring
- [x] Create Terraform modules for fairness_monitoring
- [x] Update CLI to recognize new stack components
- [x] Create database schemas

### **Phase 2: Docker Images** (Week 2)
- [x] Create fastapi-explainability Docker image
- [x] Create explainability-monitor Docker image
- [x] Create fairness-checker Docker image
- [x] Test images locally

### **Phase 3: Integration** (Week 3)
- [x] Update FastAPI terraform module with explainability flags
- [x] Create Jinja2 templates for new modules
- [x] Add Grafana dashboards
- [x] Integration testing

### **Phase 4: Documentation & Examples** (Week 4)
- [x] Write documentation
- [x] Create example projects
- [x] Add tests
- [x] Create PR

---

## 🔧 Technical Details

### **Dependencies to Add**

`pyproject.toml`:
```toml
[project.optional-dependencies]
explainability = [
    "shap>=0.42.1",
    "lime>=0.2.0.1",
]
fairness = [
    "fairlearn>=0.9.0",
    "aif360>=0.5.0",
]
```

### **Environment Variables**

New env vars for FastAPI:
- `ENABLE_EXPLAINABILITY` (bool)
- `EXPLAINER_METHOD` (shap|lime|integrated_gradients)
- `EXPLAINABILITY_LOG_TABLE` (default: explainability_logs)

New env vars for monitoring jobs:
- `IMPORTANCE_SHIFT_THRESHOLD` (float, default: 0.3)
- `FAIRNESS_VIOLATION_THRESHOLD` (float, default: 0.1)
- `ALERT_WEBHOOK_URL` (optional)

---

## 📝 Contribution Steps

### **1. Fork & Setup**
```bash
git clone https://github.com/YOUR_USERNAME/deployml.git
cd deployml
git checkout -b feature/explainability-fairness
```

### **2. Create Terraform Modules**

Start with explainability_monitoring:

```bash
mkdir -p src/deployml/terraform/modules/explainability_monitoring/cloud/gcp/cloud_run
cd src/deployml/terraform/modules/explainability_monitoring/cloud/gcp/cloud_run

# Create main.tf, variables.tf, outputs.tf
```

### **3. Create Docker Images**

```bash
mkdir -p src/deployml/docker/explainability-monitor
cd src/deployml/docker/explainability-monitor

# Create Dockerfile, requirements.txt, monitor.py
```

### **4. Update CLI**

Edit `src/deployml/cli/cli.py` to recognize new stack components.

### **5. Test Locally**

Create test config:
```yaml
name: test-explainability
stack:
  - explainability_monitoring:
      name: shap_monitor
```

Run:
```bash
deployml deploy --config-path test-config.yaml
```

### **6. Add Tests**

```bash
# Add pytest tests
tests/
├── test_explainability_module.py
└── test_fairness_module.py
```

### **7. Documentation**

Write docs and examples.

### **8. Create Pull Request**

```bash
git add .
git commit -m "feat: Add explainability and fairness monitoring"
git push origin feature/explainability-fairness
```

Create PR on GitHub with:
- Description of changes
- Example usage
- Screenshots of dashboards
- Testing results

---

## 🎯 Success Criteria

A user should be able to:

1. **Enable explainability** with one line in their config:
   ```yaml
   enable_explainability: true
   ```

2. **Deploy complete stack** with:
   ```bash
   deployml deploy --config-path config.yaml
   ```

3. **View dashboards** immediately with:
   - SHAP value trends
   - Feature importance changes
   - Fairness metrics by group
   - Bias alerts

4. **Get alerts** when:
   - Feature importance shifts significantly
   - Fairness violations detected
   - Model behavior changes

---

## 📊 Example Usage (After Implementation)

```yaml
# config.yaml
name: production-ml-monitoring
provider:
  name: gcp
  project_id: my-company-ml
  region: us-central1

deployment:
  type: cloud_run

stack:
  - experiment_tracking:
      name: mlflow
      params:
        image: gcr.io/my-company-ml/mlflow:latest

  - model_serving:
      name: fastapi
      params:
        image: gcr.io/my-company-ml/model-api:latest
        enable_explainability: true
        explainer_method: shap

  - model_monitoring:
      name: grafana
      params:
        image: gcr.io/my-company-ml/grafana:latest

  - explainability_monitoring:
      name: shap_monitor
      params:
        schedule: "0 6 * * *"
        alert_on_importance_shift: true

  - fairness_monitoring:
      name: fairness_checker
      params:
        schedule: "0 8 * * *"
        sensitive_attributes: [location, age_group]
        fairness_metrics: [demographic_parity, disparate_impact]
```

```bash
# Deploy everything
deployml deploy --config-path config.yaml

# Output:
✅ Deployed model-api with explainability enabled
✅ Deployed explainability monitoring (scheduled daily at 6 AM)
✅ Deployed fairness monitoring (scheduled daily at 8 AM)
✅ Grafana dashboards configured

🔗 Dashboards:
  - Predictions: https://grafana-xxx.run.app/d/predictions
  - Explainability: https://grafana-xxx.run.app/d/explainability
  - Fairness: https://grafana-xxx.run.app/d/fairness
```

---

## 🤝 Getting Started with Contribution

**Ready to start?** Let me know which part you'd like to work on first:

1. **🏗️ Terraform Modules** - Infrastructure code (good starting point)
2. **🐳 Docker Images** - Python services (if you prefer app development)
3. **⚙️ CLI Integration** - Python CLI code (if you like tooling)
4. **📊 Grafana Dashboards** - Visualization (if you like UI/dashboards)

I can generate the complete code for any of these to get you started!

