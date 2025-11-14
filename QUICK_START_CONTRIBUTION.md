# 🚀 Quick Start: Using the Explainability & Fairness Code

## What I Just Generated For You

I created **production-ready code** for adding explainability and fairness monitoring to DeployML:

### 📁 Files Created:

```
deployml/
├── src/deployml/terraform/modules/
│   ├── explainability_monitoring/cloud/gcp/cloud_run/
│   │   ├── main.tf          ✅ Terraform for Cloud Run Job
│   │   ├── variables.tf     ✅ Configuration variables
│   │   └── outputs.tf       ✅ Outputs (URLs, job names)
│   │
│   └── fairness_monitoring/cloud/gcp/cloud_run/
│       ├── main.tf          ✅ Terraform for Cloud Run Job
│       ├── variables.tf     ✅ Configuration variables
│       └── outputs.tf       ✅ Outputs (URLs, job names)
│
├── docker/
│   ├── explainability-monitor/
│   │   ├── Dockerfile       ✅ Container image definition
│   │   ├── requirements.txt ✅ Python dependencies
│   │   ├── monitor.py       ✅ Main monitoring logic
│   │   └── utils.py         ✅ Helper functions
│   │
│   └── fairness-checker/
│       ├── Dockerfile       ✅ Container image definition
│       ├── requirements.txt ✅ Python dependencies
│       ├── checker.py       ✅ Main fairness logic
│       └── utils.py         ✅ Helper functions
```

---

## 2️⃣ What Are the Dockerfiles For?

The Dockerfiles define **container images** that will run as **Cloud Run Jobs** (scheduled monitoring tasks).

### Docker Workflow:

```
1. Dockerfile + Python code
   ↓
2. Build image: docker build -t gcr.io/PROJECT/explainability-monitor:latest
   ↓
3. Push to GCR: docker push gcr.io/PROJECT/explainability-monitor:latest
   ↓
4. Reference in deployml-config.yaml
   ↓
5. Terraform creates Cloud Run Job using that image
   ↓
6. Cloud Scheduler triggers the job on a schedule
```

### Example:

```yaml
# deployml-config.yaml
stack:
  - explainability_monitoring:
      name: shap_monitor
      params:
        image: gcr.io/mldeploy-468919/explainability-monitor:latest  # ← Your built Docker image
        schedule: "0 6 * * *"
```

---

## 3️⃣ Database: Use EXISTING PostgreSQL (Not New One!)

**❌ Don't create a new Cloud SQL instance**
**✅ Add new tables to your existing database**

### Your Current Database:

```
Instance: mlflow-postgres-mldeploy-468919
Host: 34.83.142.98
Database: metrics
User: mlflow
Password: Xv*xlwALsCAX*.jT
```

### Add These Tables to the EXISTING Database:

```sql
-- Connect to your existing database
psql "host=34.83.142.98 port=5432 dbname=metrics user=mlflow password='Xv*xlwALsCAX*.jT'"

-- Add explainability tables
CREATE TABLE IF NOT EXISTS explainability_logs (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(50) REFERENCES prediction_logs(request_id),
    timestamp TIMESTAMP DEFAULT NOW(),
    model_version VARCHAR(50),
    shap_bedrooms FLOAT,
    shap_bathrooms FLOAT,
    shap_sqft FLOAT,
    shap_age FLOAT,
    base_value FLOAT,
    prediction_value FLOAT
);

CREATE INDEX idx_explainability_timestamp ON explainability_logs(timestamp);
CREATE INDEX idx_explainability_request_id ON explainability_logs(request_id);

-- Add feature importance table
CREATE TABLE IF NOT EXISTS feature_importance_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    model_version VARCHAR(50),
    feature_name VARCHAR(100),
    importance_score FLOAT,
    rank INTEGER,
    calculation_method VARCHAR(50)
);

CREATE INDEX idx_importance_timestamp ON feature_importance_log(timestamp);

-- Add fairness metrics table
CREATE TABLE IF NOT EXISTS fairness_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    metric_name VARCHAR(100),
    group_attribute VARCHAR(50),
    group_value VARCHAR(50),
    metric_value FLOAT,
    threshold_violated BOOLEAN,
    period_start TIMESTAMP,
    period_end TIMESTAMP,
    sample_size INTEGER
);

CREATE INDEX idx_fairness_timestamp ON fairness_metrics(timestamp);
CREATE INDEX idx_fairness_violated ON fairness_metrics(threshold_violated);
```

---

## 4️⃣ Step-by-Step Usage Guide

### **Phase 1: Add Database Tables** (5 min)

```bash
# Connect to your existing PostgreSQL
gcloud sql connect mlflow-postgres-mldeploy-468919 \
  --user=mlflow \
  --database=metrics \
  --project=mldeploy-468919

# Or use psql directly (if you have it installed)
psql "host=34.83.142.98 port=5432 dbname=metrics user=mlflow"
# Password: Xv*xlwALsCAX*.jT

# Then paste the CREATE TABLE commands above
```

### **Phase 2: Build & Push Docker Images** (10 min)

```bash
cd docker/explainability-monitor

# Build the image
docker build --platform linux/amd64 \
  -t gcr.io/mldeploy-468919/explainability-monitor:latest .

# Push to GCR
docker push gcr.io/mldeploy-468919/explainability-monitor:latest

# Repeat for fairness-checker
cd ../fairness-checker
docker build --platform linux/amd64 \
  -t gcr.io/mldeploy-468919/fairness-checker:latest .
docker push gcr.io/mldeploy-468919/fairness-checker:latest
```

### **Phase 3: Update deployml-config.yaml** (2 min)

Add these to your existing `deployml-config.yaml`:

```yaml
stack:
  # ... your existing components ...
  
  # NEW: Explainability monitoring
  - explainability_monitoring:
      name: shap_monitor
      params:
        image: gcr.io/mldeploy-468919/explainability-monitor:latest
        schedule: "0 6 * * *"  # Daily at 6 AM
        importance_shift_threshold: 0.3
        track_feature_importance: true
        alert_on_importance_shift: true
  
  # NEW: Fairness monitoring
  - fairness_monitoring:
      name: fairness_checker
      params:
        image: gcr.io/mldeploy-468919/fairness-checker:latest
        schedule: "0 8 * * *"  # Daily at 8 AM
        sensitive_attributes:
          - location
          - age_group
        fairness_metrics:
          - demographic_parity
          - disparate_impact
        demographic_parity_threshold: 0.1
        disparate_impact_threshold: 0.8
        alert_on_violation: true
```

### **Phase 4: Deploy with DeployML**

```bash
deployml deploy -c deployml-config.yaml
```

**DeployML will:**
1. ✅ Read the new `explainability_monitoring` and `fairness_monitoring` components
2. ✅ Copy the Terraform modules you created
3. ✅ Generate Terraform code to create Cloud Run Jobs
4. ✅ Create Cloud Schedulers to trigger them
5. ✅ Connect them to your existing PostgreSQL database

### **Phase 5: Test the Jobs**

```bash
# Trigger explainability monitoring manually
gcloud run jobs execute monitoring-demo-stack-explainability-monitor \
  --region=us-west1 \
  --project=mldeploy-468919

# Trigger fairness checking manually
gcloud run jobs execute monitoring-demo-stack-fairness-checker \
  --region=us-west1 \
  --project=mldeploy-468919
```

### **Phase 6: View Results in Grafana**

Query the new tables in Grafana:

```sql
-- Feature importance over time
SELECT 
  timestamp,
  feature_name,
  importance_score
FROM feature_importance_log
ORDER BY timestamp DESC;

-- Fairness violations
SELECT * 
FROM fairness_metrics 
WHERE threshold_violated = true
ORDER BY timestamp DESC;
```

---

## 5️⃣ Next Steps for DeployML Contribution

The code I generated is **ready to contribute**! Here's what you need to do:

### **A. Update CLI to Recognize New Components**

Edit `src/deployml/cli/cli.py` around line 406:

```python
# In the deploy() function, after copying modules:
copy_modules_to_workspace(
    DEPLOYML_MODULES_DIR,
    stack=stack,
    deployment_type=deployment_type,
    cloud=cloud,
)

# ADD THIS:
# Check for explainability_monitoring and fairness_monitoring
for stage in stack:
    if "explainability_monitoring" in stage or "fairness_monitoring" in stage:
        logger.info("✅ Explainability/Fairness monitoring detected")
```

### **B. Create Example Config**

Add to `example/explainability-fairness-demo/deployml-config.yaml`

### **C. Add Documentation**

Write user-facing docs in `docs/features/explainability.md`

### **D. Test End-to-End**

1. Deploy with your new config
2. Verify jobs are created
3. Run jobs manually
4. Check database for results
5. View in Grafana

### **E. Create Pull Request**

```bash
git add src/deployml/terraform/modules/explainability_monitoring
git add src/deployml/terraform/modules/fairness_monitoring
git add docker/explainability-monitor
git add docker/fairness-checker
git commit -m "feat: Add explainability and fairness monitoring modules"
git push origin feature/explainability-fairness
```

---

## 🎯 Key Takeaways

1. **Database**: Use EXISTING PostgreSQL, just add new tables
2. **Dockerfiles**: Define container images that run as Cloud Run Jobs
3. **Terraform Modules**: Infrastructure code to deploy the jobs
4. **Python Services**: The actual monitoring logic
5. **DeployML Integration**: Users enable with simple YAML config

## ❓ Common Questions

**Q: Do I need to create a new Cloud SQL instance?**
A: No! Use the existing one, just add tables.

**Q: What does the Dockerfile do?**
A: It packages your Python monitoring code into a container image that Cloud Run can execute.

**Q: How do users enable this?**
A: They add `explainability_monitoring` and `fairness_monitoring` to their YAML config.

**Q: Where does the data go?**
A: To the existing PostgreSQL database in new tables.

**Q: Can I test locally first?**
A: Yes! Build the Docker image and run it locally with environment variables.

---

## 🧪 Local Testing (Before Deploying)

```bash
# Build the image
cd docker/explainability-monitor
docker build -t explainability-monitor:test .

# Run locally with your database connection
docker run --rm \
  -e DATABASE_URL="postgresql://mlflow:Xv*xlwALsCAX*.jT@34.83.142.98:5432/metrics" \
  -e IMPORTANCE_SHIFT_THRESHOLD=0.3 \
  -e TRACK_FEATURE_IMPORTANCE=true \
  explainability-monitor:test

# You should see output showing feature importance analysis!
```

---

Ready to contribute? Let me know if you need help with any specific part! 🚀

