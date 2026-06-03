"""Unit tests for src/deployml/utils/helpers.py.

First batch — covers three patterns:
  1. Pure functions (no mocks needed)         → generate_bucket_name
  2. Functions that call out to the OS        → check_command  (uses mocks)
  3. Functions that parse text                → estimate_terraform_time
"""

from unittest.mock import patch

from deployml.utils.helpers import (
    check_command,
    estimate_terraform_time,
    generate_bucket_name,
)


# ---------------------------------------------------------------------------
# generate_bucket_name — pure function, no I/O, easiest possible test
# ---------------------------------------------------------------------------

def test_generate_bucket_name_basic():
    # Arrange + Act
    name = generate_bucket_name("my-project-123")
    # Assert
    assert name == "mlflow-artifacts-my-project-123"


def test_generate_bucket_name_replaces_underscores():
    # GCS bucket names disallow underscores. The helper must convert them
    # to hyphens — otherwise a project ID like "my_project" would produce
    # an invalid bucket name and deploy would fail at apply time.
    name = generate_bucket_name("my_project_123")
    assert name == "mlflow-artifacts-my-project-123"
    assert "_" not in name


# ---------------------------------------------------------------------------
# check_command — calls shutil.which under the hood. We mock it so the test
# doesn't depend on what's installed on the machine running the suite.
# ---------------------------------------------------------------------------

def test_check_command_returns_true_when_found():
    with patch("deployml.utils.helpers.shutil.which", return_value="/usr/bin/terraform"):
        assert check_command("terraform") is True


def test_check_command_returns_false_when_missing():
    with patch("deployml.utils.helpers.shutil.which", return_value=None):
        assert check_command("nonexistent-cmd") is False


# ---------------------------------------------------------------------------
# estimate_terraform_time — parses terraform plan output with regex.
# We feed it realistic snippets and assert on the returned string.
# ---------------------------------------------------------------------------

def test_estimate_terraform_time_detects_cloud_sql():
    # Cloud SQL gets a special 20-min-per-instance estimate because
    # provisioning a Postgres instance is the slowest part of a deploy.
    plan_output = """
    Terraform will perform the following actions:

      # google_sql_database_instance.main will be created
      + resource "google_sql_database_instance" "main" {
        name = "mlflow-db"
      }
    """
    result = estimate_terraform_time(plan_output)
    assert "20 minutes" in result
    assert "Cloud SQL" in result


def test_estimate_terraform_time_small_stack_without_cloud_sql():
    # Two non-SQL resources → falls into the generic resource-count branch.
    # 2 resources × 0.5 min avg = 1 minute (clamped by max(1, ...)).
    plan_output = """
      # google_cloud_run_service.mlflow will be created
      # google_cloud_run_service.fastapi will be created
    """
    result = estimate_terraform_time(plan_output)
    assert result.startswith("~")
    assert "minute" in result
    assert "Cloud SQL" not in result
