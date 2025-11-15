"""
Simple script to train a model and save it to MLflow
"""
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
import mlflow
import mlflow.sklearn
import os

def create_data():
    """Create simple fake house data"""
    np.random.seed(42)
    n = 1000
    
    data = pd.DataFrame({
        'bedrooms': np.random.randint(1, 6, n),
        'bathrooms': np.random.randint(1, 4, n),
        'sqft': np.random.randint(500, 5000, n),
        'age': np.random.randint(0, 50, n),
    })
    
    # Simple price formula
    data['price'] = (
        data['bedrooms'] * 50000 +
        data['bathrooms'] * 30000 +
        data['sqft'] * 100 -
        data['age'] * 2000 +
        np.random.normal(0, 50000, n)  # Add some noise
    )
    
    return data

def train():
    """Train and save model to MLflow"""
    
    # Setup MLflow
    mlflow_uri = os.getenv('MLFLOW_TRACKING_URI', 'http://localhost:5000')
    mlflow.set_tracking_uri(mlflow_uri)
    print(f"📡 Using MLflow at: {mlflow_uri}")
    
    # Create experiment
    mlflow.set_experiment("house-prices")
    
    # Get data
    print("📊 Creating data...")
    df = create_data()
    
    # Split features and target
    X = df[['bedrooms', 'bathrooms', 'sqft', 'age']]
    y = df['price']
    
    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    # Start MLflow run
    with mlflow.start_run():
        
        # Train model
        print("🤖 Training model...")
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X_train, y_train)
        
        # Test model
        predictions = model.predict(X_test)
        rmse = np.sqrt(mean_squared_error(y_test, predictions))
        
        print(f"✅ Model trained! RMSE: ${rmse:,.0f}")
        
        # Log to MLflow
        mlflow.log_param("n_estimators", 50)
        mlflow.log_metric("rmse", rmse)
        mlflow.sklearn.log_model(model, "model", registered_model_name="house-price-model")
        
        # Register model
        try:
            mlflow.register_model(
                f"runs:/{mlflow.active_run().info.run_id}/model",
                "house-price-model"
            )
            print("✅ Model registered as 'house-price-model'")
        except:
            print("⚠️  Model logged but not registered (might already exist)")
        
        print(f"🎯 Done! Check MLflow UI at {mlflow_uri}")

if __name__ == "__main__":
    train()