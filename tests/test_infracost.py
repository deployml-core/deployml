"""Unit tests for src/deployml/utils/infracost.py (v2 rewrite).

Covers:
  1. check_infracost_available  — OS-boundary mock (subprocess)
  2. check_infracost_authenticated — file-system + env var mocks
  3. parse_infracost_scan_data  — pure parsing, no I/O
  4. format_cost_for_confirmation — pure function
"""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, patch as _patch

from deployml.utils.infracost import (
    CostAnalysis,
    check_infracost_available,
    check_infracost_authenticated,
    format_cost_for_confirmation,
    parse_infracost_scan_data,
)


# ---------------------------------------------------------------------------
# check_infracost_available
# ---------------------------------------------------------------------------

def test_check_infracost_available_returns_true():
    with patch("deployml.utils.infracost.subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="infracost v2.4.2", stderr="")
        assert check_infracost_available() is True


def test_check_infracost_available_returns_false_when_not_installed():
    with patch("deployml.utils.infracost.subprocess.run", side_effect=FileNotFoundError):
        assert check_infracost_available() is False


def test_check_infracost_available_returns_false_on_nonzero_returncode():
    with patch("deployml.utils.infracost.subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="error")
        assert check_infracost_available() is False


# ---------------------------------------------------------------------------
# check_infracost_authenticated
# ---------------------------------------------------------------------------

def test_check_infracost_authenticated_returns_true_with_credentials_file(tmp_path):
    creds_file = tmp_path / ".config" / "infracost" / "credentials.yml"
    creds_file.parent.mkdir(parents=True)
    creds_file.write_text("api_key: test123\n")
    with patch("deployml.utils.infracost.Path.home", return_value=tmp_path):
        # INFRACOST_API_KEY must be absent so we exercise the file-path branch
        env_without_key = {k: v for k, v in os.environ.items() if k != "INFRACOST_API_KEY"}
        with patch.dict(os.environ, env_without_key, clear=True):
            assert check_infracost_authenticated() is True


def test_check_infracost_authenticated_returns_true_with_env_var(tmp_path):
    with patch("deployml.utils.infracost.Path.home", return_value=tmp_path):
        with patch.dict(os.environ, {"INFRACOST_API_KEY": "ic-test-key-abc"}):
            assert check_infracost_authenticated() is True


def test_check_infracost_authenticated_returns_false_when_neither(tmp_path):
    # tmp_path has no credentials.yml and INFRACOST_API_KEY is cleared
    env_without_key = {k: v for k, v in os.environ.items() if k != "INFRACOST_API_KEY"}
    with patch.dict(os.environ, env_without_key, clear=True):
        with patch("deployml.utils.infracost.Path.home", return_value=tmp_path):
            assert check_infracost_authenticated() is False


# ---------------------------------------------------------------------------
# parse_infracost_scan_data  (pure parsing, no subprocess)
# ---------------------------------------------------------------------------

# infracost inspect --json format (fields at top level)
_INSPECT_JSON = {
    "projects": 1,
    "resources": 6,
    "costed_resources": 1,
    "free_resources": 5,
    "monthly_cost": "26.4591683",
    "currency": "USD",
    "project_details": [],
    "failing_policy_list": [],
}

# infracost scan --json format (fields nested under "summary")
_SCAN_JSON = {
    "currency": "USD",
    "summary": {
        "projects": 1,
        "resources": 71,
        "costed_resources": 10,
        "free_resources": 61,
        "total_monthly_cost": "34.55",
    },
    "projects": [],
}


def test_parse_infracost_scan_data_inspect_format_extracts_all_fields():
    result = parse_infracost_scan_data(_INSPECT_JSON)
    assert result is not None
    assert abs(result.total_monthly_cost - 26.4591683) < 0.0001
    assert result.currency == "USD"
    assert result.resources == 6
    assert result.costed_resources == 1
    assert result.free_resources == 5


def test_parse_infracost_scan_data_scan_format_extracts_all_fields():
    # infracost scan --json wraps fields under "summary" with "total_monthly_cost"
    result = parse_infracost_scan_data(_SCAN_JSON)
    assert result is not None
    assert abs(result.total_monthly_cost - 34.55) < 0.001
    assert result.currency == "USD"
    assert result.resources == 71
    assert result.costed_resources == 10
    assert result.free_resources == 61


def test_parse_infracost_scan_data_handles_empty_dict():
    result = parse_infracost_scan_data({})
    assert result is not None
    assert result.total_monthly_cost == 0.0
    assert result.currency == "USD"
    assert result.resources == 0
    assert result.costed_resources == 0
    assert result.free_resources == 0


def test_parse_infracost_scan_data_handles_null_monthly_cost():
    data = {**_INSPECT_JSON, "monthly_cost": None}
    result = parse_infracost_scan_data(data)
    assert result is not None
    assert result.total_monthly_cost == 0.0


def test_parse_infracost_scan_data_handles_invalid_cost_string():
    # float("not-a-number") raises ValueError → function should return None
    data = {**_INSPECT_JSON, "monthly_cost": "not-a-number"}
    result = parse_infracost_scan_data(data)
    assert result is None


def test_parse_infracost_scan_data_handles_zero_cost():
    data = {**_INSPECT_JSON, "monthly_cost": "0", "costed_resources": 0, "free_resources": 6}
    result = parse_infracost_scan_data(data)
    assert result is not None
    assert result.total_monthly_cost == 0.0
    assert result.costed_resources == 0


# ---------------------------------------------------------------------------
# format_cost_for_confirmation  (pure function)
# ---------------------------------------------------------------------------

def test_format_cost_for_confirmation_nonzero_cost():
    result = format_cost_for_confirmation(26.46, "USD")
    assert "$26.46" in result
    assert "USD" in result


def test_format_cost_for_confirmation_zero_cost():
    result = format_cost_for_confirmation(0.0, "USD")
    assert "Variable" in result or "usage-based" in result.lower()
