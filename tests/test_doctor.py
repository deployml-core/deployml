"""Unit tests for the deployml doctor checks. No real Docker daemon or GCP calls."""
from types import SimpleNamespace
from unittest.mock import patch

import deployml.diagnostics.doctor as doctor_mod
from deployml.diagnostics.doctor import DeployMLDoctor, CheckStatus


def test_docker_permissions_skips_when_docker_missing():
    """When docker is not on PATH, the permissions check should SKIP cleanly
    rather than emit a misleading FAIL. _check_docker already reports the
    missing binary, so a second 'cannot run docker' failure is noise."""
    d = DeployMLDoctor()
    d.results.clear()
    with patch.object(doctor_mod.shutil, "which", return_value=None), \
         patch.object(doctor_mod, "run_tool", side_effect=FileNotFoundError("docker")):
        d._check_docker_permissions()
    assert len(d.results) == 1
    result = d.results[0]
    assert result.name == "Docker Permissions"
    assert result.status == CheckStatus.SKIP


def test_docker_permissions_pass_when_docker_runs():
    """Regression lock: when docker is present and `docker ps` succeeds, the
    check still reports PASS through the new guard."""
    d = DeployMLDoctor()
    d.results.clear()
    ok = SimpleNamespace(returncode=0, stdout="", stderr="")
    with patch.object(doctor_mod.shutil, "which", return_value="/usr/local/bin/docker"), \
         patch.object(doctor_mod, "run_tool", return_value=ok):
        d._check_docker_permissions()
    assert d.results[0].status == CheckStatus.PASS
