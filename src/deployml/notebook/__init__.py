"""
DeployML Notebook Interface

A modular notebook interface for MLOps stack deployment and management.
Provides easy access to deployed services with professional display formatting.

Example usage:
    import deployml.notebook as nb

    # Deploy a new stack
    stack = nb.deploy('config.yaml')

    # Load existing stack
    stack = nb.load('my-stack')

    # Display service URLs
    stack.show_urls()

    # Access MLflow client
    mlflow_client = stack.mlflow
"""

from .deployment import deploy, load
from .stack import DeploymentStack
from .urls import ServiceURLs

__all__ = ["deploy", "load", "DeploymentStack", "ServiceURLs"]
