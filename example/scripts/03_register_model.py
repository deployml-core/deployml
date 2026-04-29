"""
Step 3: Register the best MLflow run as HousingPriceModel and promote to Production.
"""
import os
import mlflow
from mlflow.tracking import MlflowClient
from dotenv import load_dotenv

load_dotenv()

MLFLOW_URL  = os.environ["MLFLOW_URL"]
MODEL_NAME  = "HousingPriceModel"
EXPERIMENT  = "housing-price-prediction"

mlflow.set_tracking_uri(MLFLOW_URL)
client = MlflowClient()

experiment = client.get_experiment_by_name(EXPERIMENT)
if experiment is None:
    raise ValueError(f"Experiment '{EXPERIMENT}' not found. Run 02_train_model.py first.")

runs = client.search_runs(
    experiment_ids=[experiment.experiment_id],
    order_by=["metrics.rmse ASC"],
    max_results=1,
)
if not runs:
    raise ValueError("No runs found. Run 02_train_model.py first.")

best_run = runs[0]
run_id   = best_run.info.run_id
rmse     = best_run.data.metrics.get("rmse")
print(f"✓ Best run: {run_id}  RMSE: {rmse:.2f}")

model_uri = f"runs:/{run_id}/model"
result    = mlflow.register_model(model_uri, MODEL_NAME)
version   = result.version
print(f"✓ Registered as '{MODEL_NAME}' version {version}")

client.transition_model_version_stage(
    name=MODEL_NAME,
    version=version,
    stage="Production",
    archive_existing_versions=True,
)
print(f"✓ Promoted version {version} to Production")
