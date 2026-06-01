"""Unit tests for deployml helpers and config validators. No GCP calls."""
from unittest.mock import patch, MagicMock

import pytest
import typer

import deployml.utils.helpers as helpers_mod
from deployml.cli.cli import (
    _load_config_or_exit,
    _validate_deploy_config_or_exit,
    _gcp_credentials_preflight_or_exit,
)
from deployml.utils.helpers import (
    check_gcp_adc,
    check_bq,
    check_docker_daemon,
    get_terraform_version,
    validate_gcp_project,
    validate_gcp_region,
    get_missing_iam_roles,
)


# ---------- _load_config_or_exit ----------

def test_load_config_valid_mapping(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("foo: bar\nnested:\n  key: 1\n")
    assert _load_config_or_exit(f) == {"foo": "bar", "nested": {"key": 1}}


def test_load_config_malformed_yaml_exits(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("this is: not valid: yaml: at all:\n")
    with pytest.raises(typer.Exit):
        _load_config_or_exit(f)


def test_load_config_list_top_level_exits(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("- item1\n- item2\n")
    with pytest.raises(typer.Exit):
        _load_config_or_exit(f)


def test_load_config_empty_file_exits(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("")
    with pytest.raises(typer.Exit):
        _load_config_or_exit(f)


def test_load_config_scalar_top_level_exits(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("just-a-string\n")
    with pytest.raises(typer.Exit):
        _load_config_or_exit(f)


# ---------- _validate_deploy_config_or_exit ----------

def test_validate_deploy_full_gcp():
    cfg = {
        "provider": {"name": "gcp", "project_id": "test-123"},
        "deployment": {"type": "cloud_run"},
    }
    _validate_deploy_config_or_exit(cfg)


def test_validate_deploy_full_aws_no_project_id_required():
    cfg = {
        "provider": {"name": "aws"},
        "deployment": {"type": "eks"},
    }
    _validate_deploy_config_or_exit(cfg)


def test_validate_deploy_missing_provider_exits():
    with pytest.raises(typer.Exit):
        _validate_deploy_config_or_exit({"deployment": {"type": "cloud_run"}})


def test_validate_deploy_provider_not_a_dict_exits():
    with pytest.raises(typer.Exit):
        _validate_deploy_config_or_exit({"provider": "gcp", "deployment": {"type": "x"}})


def test_validate_deploy_bad_provider_name_exits():
    cfg = {"provider": {"name": "gpc"}, "deployment": {"type": "cloud_run"}}
    with pytest.raises(typer.Exit):
        _validate_deploy_config_or_exit(cfg)


def test_validate_deploy_gcp_missing_project_id_exits():
    cfg = {"provider": {"name": "gcp"}, "deployment": {"type": "cloud_run"}}
    with pytest.raises(typer.Exit):
        _validate_deploy_config_or_exit(cfg)


def test_validate_deploy_missing_deployment_exits():
    cfg = {"provider": {"name": "gcp", "project_id": "x"}}
    with pytest.raises(typer.Exit):
        _validate_deploy_config_or_exit(cfg)


def test_validate_deploy_missing_deployment_type_exits():
    cfg = {"provider": {"name": "gcp", "project_id": "x"}, "deployment": {}}
    with pytest.raises(typer.Exit):
        _validate_deploy_config_or_exit(cfg)


# ---------- stack validation (#53) ----------

def test_validate_deploy_valid_stack_ok():
    cfg = {
        "provider": {"name": "gcp", "project_id": "x"},
        "deployment": {"type": "cloud_run"},
        "stack": [
            {"experiment_tracking": {"name": "mlflow", "params": {}}},
            {"model_serving": {"name": "fastapi"}},
        ],
    }
    _validate_deploy_config_or_exit(cfg)


def test_validate_deploy_stack_tool_as_set_exits():
    # Issue #53: a tool value parsed as a set crashed later with
    # "'set' object has no attribute 'get'". It must exit cleanly here.
    cfg = {
        "provider": {"name": "gcp", "project_id": "x"},
        "deployment": {"type": "cloud_run"},
        "stack": [{"experiment_tracking": {"mlflow", "params"}}],
    }
    with pytest.raises(typer.Exit):
        _validate_deploy_config_or_exit(cfg)


def test_validate_deploy_stack_not_a_list_exits():
    cfg = {
        "provider": {"name": "gcp", "project_id": "x"},
        "deployment": {"type": "cloud_run"},
        "stack": {"experiment_tracking": {"name": "mlflow"}},
    }
    with pytest.raises(typer.Exit):
        _validate_deploy_config_or_exit(cfg)


def test_validate_deploy_stage_not_a_dict_exits():
    cfg = {
        "provider": {"name": "gcp", "project_id": "x"},
        "deployment": {"type": "cloud_run"},
        "stack": ["experiment_tracking"],
    }
    with pytest.raises(typer.Exit):
        _validate_deploy_config_or_exit(cfg)


def test_validate_deploy_no_stack_key_still_ok():
    # Stack is validated only when present, so configs without it still pass.
    cfg = {"provider": {"name": "gcp", "project_id": "x"}, "deployment": {"type": "cloud_run"}}
    _validate_deploy_config_or_exit(cfg)


# ---------- _gcp_credentials_preflight_or_exit (#54) ----------

@patch("deployml.cli.cli.check_gcp_adc", return_value=True)
@patch("deployml.cli.cli.check_gcp_auth", return_value=True)
def test_gcp_preflight_passes_with_auth_and_adc(mock_auth, mock_adc):
    # Both present: no exit.
    _gcp_credentials_preflight_or_exit()


@patch("deployml.cli.cli.check_gcp_adc", return_value=True)
@patch("deployml.cli.cli.check_gcp_auth", return_value=False)
def test_gcp_preflight_exits_when_not_authenticated(mock_auth, mock_adc):
    with pytest.raises(typer.Exit):
        _gcp_credentials_preflight_or_exit()


@patch("deployml.cli.cli.check_gcp_adc", return_value=False)
@patch("deployml.cli.cli.check_gcp_auth", return_value=True)
def test_gcp_preflight_exits_when_adc_missing(mock_auth, mock_adc):
    # Issue #54: logged in but no ADC must fail at preflight, not at terraform apply.
    with pytest.raises(typer.Exit):
        _gcp_credentials_preflight_or_exit()


# ---------- check_gcp_adc ----------

@patch("deployml.utils.helpers.run_tool")
def test_check_gcp_adc_returncode_zero_true(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    assert check_gcp_adc() is True


@patch("deployml.utils.helpers.run_tool")
def test_check_gcp_adc_returncode_nonzero_false(mock_run):
    mock_run.return_value = MagicMock(returncode=1)
    assert check_gcp_adc() is False


@patch("deployml.utils.helpers.run_tool")
def test_check_gcp_adc_exception_returns_false(mock_run):
    mock_run.side_effect = OSError("boom")
    assert check_gcp_adc() is False


# ---------- check_bq ----------

@patch("deployml.utils.helpers.shutil.which")
def test_check_bq_binary_missing_false(mock_which):
    mock_which.return_value = None
    assert check_bq() is False


@patch("deployml.utils.helpers.shutil.which")
@patch("deployml.utils.helpers.run_tool")
def test_check_bq_binary_present_and_runs(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/bq"
    mock_run.return_value = MagicMock(returncode=0)
    assert check_bq() is True


@patch("deployml.utils.helpers.shutil.which")
@patch("deployml.utils.helpers.run_tool")
def test_check_bq_binary_present_but_errors(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/bq"
    mock_run.return_value = MagicMock(returncode=2)
    assert check_bq() is False


# ---------- get_terraform_version ----------

@patch("deployml.utils.helpers.shutil.which")
def test_get_terraform_version_binary_missing(mock_which):
    mock_which.return_value = None
    assert get_terraform_version() is None


@patch("deployml.utils.helpers.shutil.which")
@patch("deployml.utils.helpers.run_tool")
def test_get_terraform_version_parses_json(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/terraform"
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='{"terraform_version": "1.15.0", "format_version": "1.2"}',
    )
    assert get_terraform_version() == (1, 15, 0)


@patch("deployml.utils.helpers.shutil.which")
@patch("deployml.utils.helpers.run_tool")
def test_get_terraform_version_bad_json_returns_none(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/terraform"
    mock_run.return_value = MagicMock(returncode=0, stdout="not json")
    assert get_terraform_version() is None


# ---------- validate_gcp_project ----------

@patch("deployml.utils.helpers.run_tool")
def test_validate_gcp_project_exists(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="my-project\n")
    assert validate_gcp_project("my-project") is True


@patch("deployml.utils.helpers.run_tool")
def test_validate_gcp_project_missing(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
    assert validate_gcp_project("ghost") is False


@patch("deployml.utils.helpers.run_tool")
def test_validate_gcp_project_stdout_mismatch(mock_run):
    # returncode 0 but stdout does not match the project id we asked for
    mock_run.return_value = MagicMock(returncode=0, stdout="other-project\n")
    assert validate_gcp_project("my-project") is False


# ---------- validate_gcp_region ----------

@patch("deployml.utils.helpers.run_tool")
def test_validate_gcp_region_in_list(mock_run):
    helpers_mod._GCP_REGIONS_CACHE = None
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="us-west1\nus-central1\neurope-west1\n",
    )
    assert validate_gcp_region("us-west1") is True


@patch("deployml.utils.helpers.run_tool")
def test_validate_gcp_region_not_in_list(mock_run):
    helpers_mod._GCP_REGIONS_CACHE = None
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="us-west1\nus-central1\n",
    )
    assert validate_gcp_region("mars-central1") is False


@patch("deployml.utils.helpers.run_tool")
def test_validate_gcp_region_lookup_failure_does_not_block(mock_run):
    helpers_mod._GCP_REGIONS_CACHE = None
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="oops")
    assert validate_gcp_region("us-west1") is True


# ---------- check_docker_daemon ----------

@patch("deployml.utils.helpers.shutil.which")
def test_check_docker_daemon_binary_missing(mock_which):
    mock_which.return_value = None
    assert check_docker_daemon() is False


@patch("deployml.utils.helpers.shutil.which")
@patch("deployml.utils.helpers.run_tool")
def test_check_docker_daemon_up(mock_run, mock_which):
    mock_which.return_value = "/usr/local/bin/docker"
    mock_run.return_value = MagicMock(returncode=0)
    assert check_docker_daemon() is True


@patch("deployml.utils.helpers.shutil.which")
@patch("deployml.utils.helpers.run_tool")
def test_check_docker_daemon_down(mock_run, mock_which):
    mock_which.return_value = "/usr/local/bin/docker"
    mock_run.return_value = MagicMock(returncode=1, stderr="cannot connect")
    assert check_docker_daemon() is False


# ---------- get_missing_iam_roles ----------

@patch("deployml.utils.helpers.run_tool")
def test_get_missing_iam_roles_owner_short_circuits(mock_run):
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="me@example.com\n"),
        MagicMock(
            returncode=0,
            stdout='{"bindings": [{"role": "roles/owner", "members": ["user:me@example.com"]}]}',
        ),
    ]
    required = ["roles/cloudsql.admin", "roles/run.admin"]
    assert get_missing_iam_roles("proj", required) == []


@patch("deployml.utils.helpers.run_tool")
def test_get_missing_iam_roles_some_missing(mock_run):
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="me@example.com\n"),
        MagicMock(
            returncode=0,
            stdout='{"bindings": [{"role": "roles/cloudsql.admin", "members": ["user:me@example.com"]}]}',
        ),
    ]
    required = ["roles/cloudsql.admin", "roles/run.admin"]
    assert get_missing_iam_roles("proj", required) == ["roles/run.admin"]


@patch("deployml.utils.helpers.run_tool")
def test_get_missing_iam_roles_account_lookup_fails_returns_all(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="")
    assert get_missing_iam_roles("proj", ["roles/run.admin"]) == ["roles/run.admin"]


@patch("deployml.utils.helpers.run_tool")
def test_get_missing_iam_roles_policy_query_fails_returns_all(mock_run):
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="me@example.com\n"),
        MagicMock(returncode=1, stdout="", stderr="permission denied"),
    ]
    required = ["roles/run.admin", "roles/storage.admin"]
    assert get_missing_iam_roles("proj", required) == required


# ---------- teardown cron timezone correctness ----------

def test_calculate_cron_from_timestamp_round_trip():
    """The cron string must reflect the UTC time of the timestamp, with no
    TZ skew. Regression for the datetime.utcnow() bug that off-set teardown
    schedules by the local TZ offset."""
    from datetime import datetime, timezone, timedelta
    from deployml.utils.teardown import calculate_cron_from_timestamp

    now = datetime.now(timezone.utc)
    later = now + timedelta(hours=2)
    cron = calculate_cron_from_timestamp(int(later.timestamp()))
    expected = f"{later.minute} {later.hour} {later.day} {later.month} *"
    assert cron == expected


def test_deploy_path_timestamp_uses_timezone_aware_now():
    """The deploy path used datetime.utcnow() which silently corrupts
    .timestamp() by the local TZ offset. After the fix it uses
    datetime.now(timezone.utc). This test simulates the exact computation
    and confirms the cron lines up with what the user is told."""
    from datetime import datetime, timezone, timedelta
    from deployml.utils.teardown import calculate_cron_from_timestamp

    deployed_at = datetime.now(timezone.utc)
    teardown_at = deployed_at + timedelta(hours=24)
    cron = calculate_cron_from_timestamp(int(teardown_at.timestamp()))

    # Parse cron back. Expect minute, hour, day, month, *
    parts = cron.split()
    assert parts[0] == str(teardown_at.minute)
    assert parts[1] == str(teardown_at.hour)
    assert parts[2] == str(teardown_at.day)
    assert parts[3] == str(teardown_at.month)
    assert parts[4] == "*"
