# Installation Guide

## Prerequisites

Before installing deployml, ensure you have:

- **Python 3.10+**
- **Docker** (running)
- **gcloud CLI** — authenticated with `gcloud auth login` and `gcloud auth application-default login`
- **Terraform**

## Install deployml

```bash
pip install deployml-core
```

## Verify Installation

```bash
deployml doctor
```

This checks that all required tools (`gcloud`, `docker`, `terraform`, `bq`) are installed and authenticated. Install any missing tools and rerun until it passes.

- [Get Started →](tutorials/overview.md)
