#!/usr/bin/env python3
"""
MLflow Experiment Tracking on GCP - WORKING VERSION
Train models and track experiments using MLflow deployed via deployml
"""

import mlflow
import pandas as pd
import numpy as np
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

# =============================================================================
# CONFIGURATION - GCP MLflow Server (Deployed via DeployML!)
# =============================================================================
MLFLOW_TRACKING_URI = "https://my-mlops-stack-mlflow-server-c5i2hjbjma-uw.a.run.app"
EXPERIMENT_NAME = "gcp-production-experiments"

print("=" * 80)
print("🚀 MLflow on GCP via DeployML")
print("=" * 80)
print(f"📍 Server: {MLFLOW_TRACKING_URI}")
print(f"🔬 Experiment: {EXPERIMENT_NAME}")
print(f"🏗️  Infrastructure: Managed by deployml")
print("=" * 80)

# Connect to GCP MLflow
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
mlflow.set_experiment(EXPERIMENT_NAME)

print("\n✅ Connected to GCP MLflow server")

# =============================================================================
# CREATE DATASET
# =============================================================================
print("\n📊 Creating dataset...")
X, y = make_classification(n_samples=1000, n_features=20, n_informative=15, random_state=42)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
print(f"✓ Dataset ready: {len(X_train)} training, {len(X_test)} test samples")

# =============================================================================
# TRAIN AND LOG TO GCP
# =============================================================================
models = [
    ("Logistic Regression", LogisticRegression(max_iter=1000, random_state=42), {"max_iter": 1000}),
    ("Random Forest", RandomForestClassifier(n_estimators=100, random_state=42), {"n_estimators": 100}),
    ("Gradient Boosting", GradientBoostingClassifier(n_estimators=100, random_state=42), {"n_estimators": 100}),
]

print(f"\n🤖 Training {len(models)} models on GCP...\n")
results = []

for name, model, params in models:
    print(f"[Training] {name}...")
    
    with mlflow.start_run(run_name=name):
        # Train
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        
        # Calculate metrics
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, average='weighted')
        recall = recall_score(y_test, y_pred, average='weighted')
        f1 = f1_score(y_test, y_pred, average='weighted')
        
        # Log to GCP MLflow
        mlflow.log_params(params)
        mlflow.log_param("model_name", name)
        mlflow.log_param("deployed_via", "deployml")
        mlflow.log_param("cloud", "GCP")
        mlflow.log_param("region", "us-west2")
        
        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_metric("precision", precision)
        mlflow.log_metric("recall", recall)
        mlflow.log_metric("f1_score", f1)
        
        # Get run info
        run = mlflow.active_run()
        print(f"  ✅ {name}")
        print(f"     Accuracy: {accuracy:.4f} | F1: {f1:.4f}")
        print(f"     Run ID: {run.info.run_id}")
        
        results.append({
            "Model": name,
            "Accuracy": f"{accuracy:.4f}",
            "F1 Score": f"{f1:.4f}",
            "Run ID": run.info.run_id[:8]
        })

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("✅ SUCCESS! Experiments Logged to GCP")
print("=" * 80)

results_df = pd.DataFrame(results)
print("\n📊 Results:")
print(results_df.to_string(index=False))

print("\n" + "=" * 80)
print("🌐 View in MLflow UI (deployed via deployml):")
print("=" * 80)
print(f"  {MLFLOW_TRACKING_URI}")
print("\n💡 What DeployML Deployed:")
print("  ✅ Cloud Run Service: mlflow-server-gcp")
print("  ✅ GCS Bucket: mlflow-artifacts-gcp-bucket")
print("  ✅ IAM Permissions: Configured")
print("  ✅ Public Access: Enabled")
print("  ✅ Region: us-west2")
print("\n🎯 You Used DeployML For:")
print("  • Infrastructure as Code (YAML → Terraform)")
print("  • Automatic resource provisioning")
print("  • Cloud Run + GCS deployment")
print("  • No manual gcloud commands needed!")
print("=" * 80)

