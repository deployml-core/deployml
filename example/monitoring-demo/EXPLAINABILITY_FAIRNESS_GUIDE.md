# 🔍 Adding Explainability & Fairness Metrics to ML Monitoring

## 📋 Overview

This guide shows you how to add:
- ✅ **Explainability**: SHAP values, feature importance, prediction explanations
- ✅ **Fairness**: Demographic parity, disparate impact, bias detection

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Incoming Prediction                   │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI Model Serving (Enhanced)                       │
│  - Make prediction                                      │
│  - Calculate SHAP values                                │
│  - Log explainability metrics                           │
│  - Check fairness constraints                           │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│         PostgreSQL Database (New Tables)                │
│  - explainability_logs                                  │
│  - fairness_metrics                                     │
│  - shap_values                                          │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Scheduled Jobs (New)                                   │
│  - Fairness Monitoring (Daily)                          │
│  - Explainability Analysis (Daily)                      │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Grafana Dashboards                         │
│  - SHAP importance trends                               │
│  - Fairness metrics by group                            │
│  - Bias alerts                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 📊 What We'll Add

### **1. Explainability Metrics**

| Metric | Description | Use Case |
|--------|-------------|----------|
| **SHAP Values** | Contribution of each feature to a prediction | "Why did model predict $500k?" |
| **Feature Importance** | Global importance over time | "Is sqft still most important?" |
| **Force Plots** | Visual explanation of individual predictions | Customer transparency |
| **Dependence Plots** | How feature values affect predictions | Model debugging |

### **2. Fairness Metrics**

| Metric | Description | Formula |
|--------|-------------|---------|
| **Demographic Parity** | Equal positive prediction rates across groups | P(Ŷ=1\|A=a) = P(Ŷ=1\|A=b) |
| **Equal Opportunity** | Equal true positive rates across groups | P(Ŷ=1\|Y=1,A=a) = P(Ŷ=1\|Y=1,A=b) |
| **Disparate Impact** | Ratio of positive rates between groups | Should be > 0.8 |
| **Statistical Parity** | Difference in positive rates | Should be < 0.1 |

---

## 🚀 Step-by-Step Implementation

### **Phase 1: Database Schema** (5 min)

Add new tables for explainability and fairness metrics.

### **Phase 2: Enhanced FastAPI** (20 min)

Update prediction endpoint to:
- Calculate SHAP values for each prediction
- Extract sensitive attributes
- Log explainability data

### **Phase 3: Fairness Monitoring Job** (30 min)

Create scheduled job to:
- Calculate fairness metrics across demographic groups
- Detect bias
- Alert on violations

### **Phase 4: Explainability Analysis Job** (30 min)

Create scheduled job to:
- Aggregate SHAP values
- Track feature importance changes
- Generate summary reports

### **Phase 5: Grafana Dashboards** (20 min)

Create visualizations for:
- SHAP importance heatmaps
- Fairness metrics by group
- Bias alerts
- Explainability trends

---

## 📝 Detailed Implementation

### **Step 1: Database Schema**

Create new tables in PostgreSQL:

```sql
CREATE TABLE-- Explainability logs
 explainability_logs (
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

-- Fairness metrics
CREATE TABLE fairness_metrics (
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

-- Feature importance over time
CREATE TABLE feature_importance_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    model_version VARCHAR(50),
    feature_name VARCHAR(100),
    importance_score FLOAT,
    rank INTEGER,
    calculation_method VARCHAR(50)
);
```

### **Step 2: Update FastAPI with SHAP**

Key changes to `app.py`:

```python
import shap
import numpy as np

# Initialize SHAP explainer on startup
@app.on_event("startup")
async def load_model():
    global model, model_version, explainer
    # ... existing model loading ...
    
    # Create SHAP explainer
    # Use a background dataset (sample from training data)
    background_data = generate_background_data(100)
    explainer = shap.TreeExplainer(model, background_data)
    logger.info("✅ SHAP explainer initialized")

def calculate_shap_values(features_df):
    """Calculate SHAP values for a prediction"""
    try:
        shap_values = explainer.shap_values(features_df)
        base_value = explainer.expected_value
        
        return {
            'shap_bedrooms': float(shap_values[0][0]),
            'shap_bathrooms': float(shap_values[0][1]),
            'shap_sqft': float(shap_values[0][2]),
            'shap_age': float(shap_values[0][3]),
            'base_value': float(base_value),
        }
    except Exception as e:
        logger.error(f"SHAP calculation failed: {e}")
        return None

@app.post("/predict")
async def predict(request: HousePredictionRequest):
    # ... existing prediction code ...
    
    # Calculate SHAP values
    shap_data = calculate_shap_values(features_df)
    
    # Log to explainability_logs table
    log_explainability(request_id, shap_data, prediction)
    
    return PredictionResponse(
        request_id=request_id,
        prediction=prediction,
        explanation=shap_data  # NEW: return explanation
    )
```

### **Step 3: Fairness Monitoring Job**

Create `fairness-monitoring/monitor.py`:

```python
"""
Fairness monitoring - detects bias across demographic groups
"""
import pandas as pd
from sklearn.metrics import confusion_matrix

def calculate_demographic_parity(predictions_df, sensitive_attr):
    """Calculate demographic parity difference"""
    groups = predictions_df.groupby(sensitive_attr)
    
    positive_rates = {}
    for group_name, group_data in groups:
        positive_rate = (group_data['prediction'] > threshold).mean()
        positive_rates[group_name] = positive_rate
    
    # Calculate max difference
    rates = list(positive_rates.values())
    parity_difference = max(rates) - min(rates)
    
    return positive_rates, parity_difference

def calculate_disparate_impact(predictions_df, sensitive_attr, protected_group, reference_group):
    """Calculate disparate impact ratio"""
    protected_rate = predictions_df[
        predictions_df[sensitive_attr] == protected_group
    ]['prediction'].mean()
    
    reference_rate = predictions_df[
        predictions_df[sensitive_attr] == reference_group
    ]['prediction'].mean()
    
    disparate_impact = protected_rate / reference_rate if reference_rate > 0 else 0
    
    # Should be > 0.8 (80% rule)
    violation = disparate_impact < 0.8
    
    return disparate_impact, violation
```

### **Step 4: Grafana Queries**

#### SHAP Values Heatmap
```sql
SELECT
  timestamp as time,
  ROUND(shap_bedrooms::numeric, 2) as "Bedrooms",
  ROUND(shap_bathrooms::numeric, 2) as "Bathrooms",
  ROUND(shap_sqft::numeric, 2) as "Sqft",
  ROUND(shap_age::numeric, 2) as "Age"
FROM explainability_logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp;
```

#### Fairness Violations
```sql
SELECT
  timestamp as time,
  metric_name as "Metric",
  group_attribute as "Group",
  group_value as "Value",
  ROUND(metric_value::numeric, 3) as "Score",
  threshold_violated as "Violated?"
FROM fairness_metrics
WHERE timestamp > NOW() - INTERVAL '7 days'
  AND threshold_violated = true
ORDER BY timestamp DESC;
```

---

## 🔧 Required Dependencies

Add to requirements.txt:
```
shap==0.42.1
fairlearn==0.9.0
aif360==0.5.0  # For advanced fairness metrics
```

---

## 📦 What You Need to Do

### **Quick Start (1 hour)**
1. ✅ Create database tables (copy SQL above)
2. ✅ Update FastAPI with SHAP (I'll create the full file)
3. ✅ Create fairness monitoring job (I'll create the full file)
4. ✅ Add Grafana queries (copy from above)

### **Full Implementation (3-4 hours)**
1. ✅ All of the above
2. ✅ Create Dockerfiles for new jobs
3. ✅ Update deployml-config.yaml
4. ✅ Build and deploy new images
5. ✅ Test with synthetic sensitive attributes
6. ✅ Create comprehensive dashboards

---

## 🎯 Decision Points

Before we start implementing, decide:

### **1. Which approach?**
- **Option A: Quick Demo** - Add SHAP to existing FastAPI, basic fairness in notebook
- **Option B: Full Production** - Complete implementation with all jobs and monitoring

### **2. Sensitive attributes for fairness?**
For house pricing, we could add:
- **Location/Neighborhood** (proxy for demographics)
- **Age of buyer** (if we have this data)
- **First-time buyer status**

Or use synthetic attributes for demo purposes.

### **3. Deployment method?**
- **Update existing services** (faster, less clean)
- **New microservices** (cleaner, more complex)

---

## 📊 Expected Results

Once implemented, you'll see:

1. **Real-time explainability**
   - Every prediction comes with SHAP explanation
   - "Sqft contributed +$50k, Age contributed -$10k"

2. **Fairness monitoring**
   - Daily fairness reports
   - Automated bias detection
   - Alerts when metrics violate thresholds

3. **Enhanced dashboards**
   - Feature importance trends
   - Fairness metrics by group
   - Bias alert timeline
   - Explainability heatmaps

---

## 🚦 Next Steps

**Tell me which option you prefer:**

1. **🚀 Quick Demo (Recommended)**: I'll create enhanced FastAPI with SHAP + basic fairness analysis in a notebook (1 hour)

2. **🏗️ Full Production**: Complete implementation with all jobs, dashboards, and deployment (3-4 hours)

3. **📚 Guided Tutorial**: Step-by-step walkthrough where I guide you through each piece

Which would you like to do?

