from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
TERRAFORM_DIR = Path(__file__).parent.parent / "terraform"

TOOL_VARIABLES = {
    "mlflow": [
        {"name": "project_id", "type": "string", "description": "GCP project ID"},
        {"name": "region", "type": "string", "description": "Deployment region"},
        {"name": "artifact_bucket", "type": "string", "description": "Bucket for MLflow artifacts"},
        {"name": "backend_store_uri", "type": "string", "description": "URI for MLflow backend store"},
        {"name": "image", "type": "string", "description": "MLflow Docker image"},
    ],
    "wandb": [
        {"name": "project_id", "type": "string", "description": "GCP project ID"},
        {"name": "region", "type": "string", "description": "Deployment region"},
        {"name": "artifact_bucket", "type": "string", "description": "Bucket for wandb artifacts"},
        {"name": "wandb_port", "type": "number", "description": "Port for wandb server (default 8080)"},
        {"name": "image", "type": "string", "description": "wandb Docker image (optional)"},
    ],
    "fastapi": [
        {"name": "project_id", "type": "string", "description": "GCP project ID"},
        {"name": "region", "type": "string", "description": "Deployment region"},
        {"name": "image", "type": "string", "description": "FastAPI Docker image"},
    ]
}

ANIMAL_NAMES = [
    "antelope", "badger", "beaver", "bison", "buffalo", "camel", "cheetah", "cougar", "coyote", "deer", "dingo", "elephant", "elk", "ferret", "fox", "gazelle", "giraffe", "gnu", "goat", "hippo", "hyena", "ibex", "jaguar", "kangaroo", "koala", "leopard", "lion", "llama", "lynx", "mink", "moose", "otter", "panda", "panther", "pig", "platypus", "porcupine", "puma", "rabbit", "raccoon", "ram", "rat", "reindeer", "rhinoceros", "sheep", "skunk", "sloth", "squirrel", "tiger", "walrus", "weasel", "wolf", "wombat", "yak", "zebra"
]

FALLBACK_WORDS = [
    "mlflow", "model", "artifact", "experiment", "data", "pipeline", "deploy", "track", "ai", "ml", "cloud"
]

REQUIRED_GCP_APIS = [
    "run.googleapis.com",
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "compute.googleapis.com",
    "storage-api.googleapis.com",
    "storage-component.googleapis.com",
    "sqladmin.googleapis.com",
    "sql-component.googleapis.com",
    "servicenetworking.googleapis.com",
    "cloudkms.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
]