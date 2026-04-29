"""
Step 2: Pull features from BigQuery and train a RandomForest model, logging to MLflow.
"""
import os
import numpy as np
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import root_mean_squared_error, r2_score
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()

MLFLOW_URL     = os.environ["MLFLOW_URL"]
PROJECT        = os.environ["BIGQUERY_PROJECT"]
DATASET        = os.getenv("BIGQUERY_DATASET", "mlops")
EXPERIMENT     = "housing-price-prediction"
FEATURE_COLS   = ["bedrooms", "bathrooms", "area_sqft", "lot_size", "year_built", "city", "state"]

# Pull features from BigQuery
print(f"Querying BigQuery {PROJECT}.{DATASET}.offline_features ...")
client = bigquery.Client(project=PROJECT)
query  = f"SELECT {', '.join(FEATURE_COLS)} FROM `{PROJECT}.{DATASET}.offline_features`"
df     = client.query(query).to_dataframe()
print(f"✓ Loaded {len(df)} rows from BigQuery")

# Generate target (same formula as seed_model.py)
np.random.seed(42)
df["price"] = (
    df["area_sqft"] * 200
    + df["bedrooms"] * 15000
    + df["bathrooms"] * 10000
    + (2023 - df["year_built"]) * -500
    + np.random.normal(0, 10000, len(df))
)

X = df[FEATURE_COLS]
y = df["price"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

print(f"Connecting to MLflow at {MLFLOW_URL} ...")
mlflow.set_tracking_uri(MLFLOW_URL)
mlflow.set_experiment(EXPERIMENT)

params = {"n_estimators": 100, "max_depth": 10, "random_state": 42}

print("Training RandomForestRegressor ...")
with mlflow.start_run():
    model = RandomForestRegressor(**params)
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    rmse  = root_mean_squared_error(y_test, preds)
    r2    = r2_score(y_test, preds)

    print("Logging to MLflow ...")
    mlflow.log_params(params)
    mlflow.log_metric("rmse", rmse)
    mlflow.log_metric("r2", r2)
    mlflow.sklearn.log_model(model, "model")

    run_id = mlflow.active_run().info.run_id
    print(f"✓ Run logged: {run_id}")
    print(f"  RMSE: {rmse:.2f}  R²: {r2:.3f}")
