# MLOps Components

deployml provisions a complete end-to-end MLOps pipeline with pre-configured components. Each component can be enabled or disabled based on your specific needs, allowing you to build a stack that matches your learning objectives or project requirements.

## Component Overview

The deployml stack consists of six main stages that work together to provide a complete MLOps solution. Experiment tracking enables you to track and compare ML experiments with detailed logging of parameters, metrics, and results. Artifact tracking stores model artifacts, datasets, and other ML assets in versioned cloud storage. Model registry provides centralized model versioning and management with stage transitions from development to production. Model serving deploys models as production-ready API endpoints that can be integrated into applications. Model monitoring tracks model performance, detects drift, and monitors system health. Workflow orchestration schedules and runs training, scoring, and monitoring jobs automatically.

## Experiment Tracking

Experiment tracking is fundamental to MLOps, allowing you to log, compare, and reproduce ML experiments. deployml supports MLflow as the experiment tracking solution.

MLflow provides comprehensive experiment tracking capabilities. You can track experiments with automatic logging of parameters, metrics, and artifacts. The MLflow UI offers visual comparison of runs, making it easy to identify the best performing models. Integration with artifact storage ensures all experiment data is preserved. MLflow supports multiple backend stores including PostgreSQL for production deployments and SQLite for development environments.

## Artifact Tracking

Model artifacts, datasets, and other ML assets need to be stored securely and versioned properly. deployml integrates artifact tracking with experiment tracking, ensuring that all artifacts from your experiments are automatically stored and versioned.

Artifacts are stored in Google Cloud Storage buckets with automatic bucket creation and permission management. You can configure custom bucket names or let deployml generate unique names automatically. All artifacts are versioned, allowing you to track changes over time and retrieve specific versions when needed.

## Model Registry

The model registry provides centralized model versioning and management. Once models are trained and evaluated, they can be registered in the model registry with metadata, tags, and version information. Models can be promoted through stages from development to staging to production, with clear lineage tracking showing which experiment produced each model version.

The registry integrates seamlessly with experiment tracking, allowing you to register models directly from experiments. Model serving components can pull models from the registry, ensuring that production deployments always use the correct model version.

## Model Serving

Once models are trained and registered, they need to be deployed as production-ready APIs. deployml supports FastAPI for model serving, providing RESTful API endpoints with automatic OpenAPI documentation.

FastAPI services can be deployed on Cloud Run for serverless, auto-scaling deployments, on GKE for Kubernetes-based production deployments, or on Cloud VMs for persistent deployments. The serving endpoints integrate with the model registry, allowing you to specify which model version to serve. Health check endpoints ensure services are running correctly, and metrics endpoints provide observability into service performance.

## Model Monitoring

Model monitoring is essential for maintaining model performance in production. deployml supports Grafana for monitoring dashboards, allowing you to visualize model performance metrics, prediction latency, request rates, error rates, and system health.

Additional monitoring capabilities include explainability monitoring to track model explainability metrics and feature importance over time, and fairness monitoring to detect bias and ensure models meet fairness requirements. These monitoring tools help identify model drift, performance degradation, and data quality issues before they impact production systems.

## Workflow Orchestration

MLOps pipelines often require scheduled tasks such as periodic model retraining, batch scoring, and monitoring report generation. deployml supports workflow orchestration through cron jobs that can be scheduled to run at specific intervals.

Cron jobs can be configured to run training pipelines, perform batch scoring on large datasets, validate data quality, generate monitoring reports, and perform other periodic tasks. These jobs run as Cloud Run services, providing serverless execution with automatic scaling and cost-effective operation.

Offline scoring capabilities allow you to run batch prediction jobs on large datasets, making it easy to score historical data or generate predictions for large batches without real-time API calls.

## Component Integration

All components in the deployml stack are designed to work together seamlessly. Experiment tracking feeds into the model registry, which provides models to serving endpoints. Model monitoring tracks the performance of deployed models, and workflow orchestration automates the entire pipeline from training to deployment to monitoring.

This integrated approach means you can focus on building and improving your ML models rather than managing the infrastructure that connects these components together.

## Database Backends

deployml supports multiple database backends to match different deployment scenarios. PostgreSQL through Cloud SQL provides a production-ready database solution suitable for multi-user deployments, scalable storage needs, and production environments. SQLite offers a lightweight alternative perfect for development, single-user deployments, and cost-effective small projects.

Components that use databases include MLflow for experiment tracking and model registry, and any custom components you might deploy.

## Storage Options

Storage is a critical component of any MLOps pipeline. Google Cloud Storage provides durable, scalable storage for MLflow artifacts, model files, and datasets.

## Next Steps

- Learn about [Cost Estimates](costs.md) for these components
- Explore [Tutorials](../tutorials/overview.md) for deployment examples
- Check [CLI Commands](../api/cli-commands.md) for configuration options

