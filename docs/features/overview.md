# Features Overview

deployml is a Python library designed to simplify the deployment of end-to-end MLOps infrastructure in the cloud. Built specifically for academia, deployml enables instructors and students to focus on learning MLOps concepts rather than struggling with infrastructure setup.

## Core Capabilities

### Infrastructure as Code

deployml uses Terraform to provision cloud infrastructure declaratively. Instead of manually configuring services through cloud consoles, you define your entire MLOps stack in a simple YAML configuration file. This approach provides several key benefits: reproducible deployments that work consistently across environments, version-controlled infrastructure that can be tracked in Git, easy teardown and cleanup when projects are complete, and elimination of manual configuration errors.

### Cost Analysis

Understanding cloud costs before deployment is crucial, especially in academic settings with limited budgets. deployml integrates with Infracost to provide cost estimates before any infrastructure is provisioned. You'll see monthly cost projections for your entire stack, receive warnings if costs exceed your configured threshold, and get cost breakdowns by component. This helps prevent unexpected bills and allows for better budget planning.

### Multi-Cloud Support

Currently focused on Google Cloud Platform, deployml supports multiple deployment types to match different use cases. Cloud Run provides serverless, auto-scaling container deployments ideal for APIs and services with variable traffic. GKE (Google Kubernetes Engine) offers production-ready Kubernetes deployments with full control over cluster configuration. Cloud VM enables persistent virtual machine deployments for long-running services that need stable storage. Minikube support allows for local development and testing without any cloud costs.

### ML-Focused Components

deployml comes pre-configured with essential MLOps tools that work together seamlessly. The platform supports experiment tracking through MLflow or WandB, allowing you to log parameters, metrics, and artifacts from your ML experiments. Model registry capabilities enable centralized model versioning and stage management. Feature store integration with Feast provides consistent features across training and serving. FastAPI endpoints make it easy to deploy models as production-ready APIs. Grafana dashboards offer monitoring and visualization capabilities. Workflow orchestration through cron jobs enables scheduled training, scoring, and monitoring tasks.

### Production Ready

While designed for learning, deployml incorporates production best practices. Service account management ensures secure access to cloud resources. Secure artifact storage in Google Cloud Storage buckets protects your models and data. Database backend options include both PostgreSQL for production deployments and SQLite for development. Auto-teardown functionality helps manage costs by automatically destroying infrastructure after a specified duration. Health checks and monitoring capabilities ensure your services are running correctly.

## What deployml Provides

deployml provisions infrastructure for a complete MLOps pipeline covering all major stages of the machine learning lifecycle. Experiment tracking allows you to track ML experiments and compare results across different runs. Artifact tracking stores and versions model artifacts, datasets, and other ML assets. Model registry provides centralized model versioning and management with stage transitions. Feature store manages features for both training and serving with consistency guarantees. Model serving deploys models as API endpoints that can be integrated into applications. Model monitoring tracks model performance, drift, and system health. Workflow orchestration schedules and runs training and scoring jobs automatically.

## What's Not Included

deployml focuses on traditional ML workflows and does not include tooling for LLMs and generative AI, scalable model development frameworks, or data versioning and data pipelines. These areas may be added in future releases based on community needs.

## Use Cases

### For Instructors

Instructors teaching MLOps courses can use deployml to quickly set up lab environments for students, demonstrate MLOps concepts with real infrastructure, manage costs effectively with auto-teardown features, and provide reproducible deployment examples that students can follow.

### For Students

Students learning MLOps can use deployml to gain hands-on experience without getting bogged down in infrastructure complexity, practice with production-like environments, understand cloud deployment patterns, and focus their time on ML workflows rather than infrastructure setup.