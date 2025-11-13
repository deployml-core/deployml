"""
Simple model training script for monitoring demo
Trains a basic regression model and logs it to MLflow
"""
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
import mlflow
import mlflow.sklearn
import os

# Simple synthetic house price data
def create_sample_data(n_samples=1000):
    """Create simple synthetic data"""
    np.random.seed(42)
    
    data = {
        'bedrooms': np.random.randint(1, 6, n_samples),
        'bathrooms': np.random.randint(1, 4, n_samples),
        'sqft': np.random.randint(500, 5000, n_samples),
        'age': np.random.randint(0, 50, n_samples),
    }
    
    # Simple price formula with some noise
    data['price'] = (
        data['bedrooms'] * 50000 +
        data['bathrooms'] * 30000 +
        data['sqft'] * 100 +
        data['age'] * -2000 +
        np.random.normal(0, 50000, n_samples)
    )
    
    return pd.DataFrame(data)

def train_model():
    """Train and register a simple model"""
    
    # Set MLflow tracking URI from environment variable
    # This should point to your DEPLOYED MLflow server, e.g.:
    # export MLFLOW_TRACKING_URI="https://mlflow-server-abc123-uw.a.run.app"
    mlflow_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000')
    
    if mlflow_uri == 'http://localhost:5000':
        print("⚠️  WARNING: Using localhost MLflow. Set MLFLOW_TRACKING_URI to your deployed URL:")
        print("   export MLFLOW_TRACKING_URI='https://your-mlflow-url.run.app'")
    
    mlflow.set_tracking_uri(mlflow_uri)
    print(f"📡 Connecting to MLflow at: {mlflow_uri}")
    mlflow.set_experiment("house-price-prediction")
    
    print(f"📊 Creating training data...")
    df = create_sample_data(n_samples=1000)
    
    X = df[['bedrooms', 'bathrooms', 'sqft', 'age']]
    y = df['price']
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    print(f"🤖 Training model...")
    with mlflow.start_run(run_name="simple-house-model"):
        
        # Train simple random forest
        model = RandomForestRegressor(
            n_estimators=50,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        
        model.fit(X_train, y_train)
        
        # Make predictions
        y_pred_train = model.predict(X_train)
        y_pred_test = model.predict(X_test)
        
        # Calculate metrics
        train_rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
        test_rmse = np.sqrt(mean_squared_error(y_test, y_pred_test))
        train_r2 = r2_score(y_train, y_pred_train)
        test_r2 = r2_score(y_test, y_pred_test)
        
        print(f"\n✅ Model Performance:")
        print(f"   Train RMSE: ${train_rmse:,.2f}")
        print(f"   Test RMSE:  ${test_rmse:,.2f}")
        print(f"   Train R²:   {train_r2:.4f}")
        print(f"   Test R²:    {test_r2:.4f}")
        
        # Log metrics
        mlflow.log_param("n_estimators", 50)
        mlflow.log_param("max_depth", 10)
        mlflow.log_metric("train_rmse", train_rmse)
        mlflow.log_metric("test_rmse", test_rmse)
        mlflow.log_metric("train_r2", train_r2)
        mlflow.log_metric("test_r2", test_r2)
        
        # Log feature importance for monitoring
        feature_importance = dict(zip(X.columns, model.feature_importances_))
        for feature, importance in feature_importance.items():
            mlflow.log_metric(f"feature_importance_{feature}", importance)
        
        # Log model with signature
        from mlflow.models.signature import infer_signature
        signature = infer_signature(X_train, y_pred_train)
        
        mlflow.sklearn.log_model(
            model,
            "model",
            signature=signature,
            registered_model_name="house-price-model"
        )
        
        # Log training statistics for drift detection
        training_stats = {
            'mean': X_train.mean().to_dict(),
            'std': X_train.std().to_dict(),
            'min': X_train.min().to_dict(),
            'max': X_train.max().to_dict(),
        }
        mlflow.log_dict(training_stats, "training_statistics.json")
        
        run_id = mlflow.active_run().info.run_id
        print(f"\n🎯 Model logged to MLflow!")
        print(f"   Run ID: {run_id}")
        print(f"   Model: house-price-model")
        
        return run_id

if __name__ == "__main__":
    train_model()

