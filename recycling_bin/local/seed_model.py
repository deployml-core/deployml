"""
Train a dummy housing price model and register it in local MLflow as Production.
Run with: python seed_model.py
"""
import os
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from mlflow.tracking import MlflowClient

MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
MODEL_NAME = "HousingPriceModel"

FEATURE_COLUMNS = [
    'bedrooms', 'bathrooms', 'area_sqft', 'lot_size',
    'year_built', 'city', 'state'
]

def generate_data(n=500):
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        'bedrooms':    rng.integers(1, 7, n),
        'bathrooms':   rng.integers(1, 5, n),
        'area_sqft':   rng.integers(600, 4000, n),
        'lot_size':    rng.integers(1000, 10000, n),
        'year_built':  rng.integers(1950, 2023, n),
        'city':        rng.integers(0, 10, n),
        'state':       rng.integers(0, 5, n),
    })
    # Simple price formula + noise
    df['price'] = (
        df['area_sqft'] * 200
        + df['bedrooms'] * 15000
        + df['bathrooms'] * 10000
        + (2023 - df['year_built']) * -500
        + rng.normal(0, 20000, n)
    )
    return df

def main():
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment("housing-local")

    df = generate_data()
    X = df[FEATURE_COLUMNS]
    y = df['price']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    with mlflow.start_run(run_name="dummy-rf") as run:
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X_train, y_train)

        score = model.score(X_test, y_test)
        mlflow.log_param("n_estimators", 50)
        mlflow.log_metric("r2", score)

        mlflow.sklearn.log_model(model, artifact_path="model")
        run_id = run.info.run_id
        print(f"Logged model with R²={score:.3f}")

    # Register and promote to Production
    client = MlflowClient(MLFLOW_URI)
    mv = mlflow.register_model(f"runs:/{run_id}/model", MODEL_NAME)

    client.transition_model_version_stage(
        name=MODEL_NAME,
        version=mv.version,
        stage="Production",
        archive_existing_versions=True,
    )
    print(f"Promoted {MODEL_NAME} v{mv.version} to Production")
    print(f"\nCheck MLflow UI: {MLFLOW_URI}")
    print(f"FastAPI predict: http://localhost:8000/predict")

if __name__ == "__main__":
    main()
