"""Unit tests for deployml.utils.platform_compat.

These close the coverage gap noted in the macOS re-validation: the helper test
suite mocks run_tool wholesale, so resolve_tool's resolve/raise contract and
run_tool's kwarg passthrough were never exercised. No real external tools are
launched; the only real side effect is rmtree on a pytest tmp_path.
"""
import os
import stat
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import deployml.utils.platform_compat as pc


# ---------- resolve_tool ----------

def test_resolve_tool_returns_path_when_found():
    with patch.object(pc.shutil, "which", return_value="/usr/local/bin/gcloud"):
        assert pc.resolve_tool("gcloud") == "/usr/local/bin/gcloud"


def test_resolve_tool_raises_filenotfound_when_missing():
    with patch.object(pc.shutil, "which", return_value=None):
        with pytest.raises(FileNotFoundError) as exc:
            pc.resolve_tool("nonexistent-tool-xyz")
    assert "nonexistent-tool-xyz" in str(exc.value)


# ---------- run_tool ----------

def test_run_tool_forwards_resolved_path_args_and_kwargs():
    """run_tool must prepend the resolved path and pass every kwarg straight
    through to subprocess.run. The whole blocker 1 refactor depends on this."""
    completed = SimpleNamespace(returncode=0)
    with patch.object(pc, "resolve_tool", return_value="/usr/local/bin/gcloud"), \
         patch.object(pc.subprocess, "run", return_value=completed) as mock_run:
        result = pc.run_tool("gcloud", ["version", "--quiet"],
                             capture_output=True, check=True)
    assert result is completed
    mock_run.assert_called_once_with(
        ["/usr/local/bin/gcloud", "version", "--quiet"],
        capture_output=True, check=True,
    )


def test_run_tool_decodes_utf8_in_windows_text_mode():
    """On Windows, text-mode captures must be decoded as UTF-8 with replacement
    to avoid the cp1252 UnicodeDecodeError. Off Windows this branch is skipped."""
    completed = SimpleNamespace(returncode=0)
    with patch.object(pc, "IS_WINDOWS", True), \
         patch.object(pc, "resolve_tool", return_value=r"C:\sdk\bin\gcloud.cmd"), \
         patch.object(pc.subprocess, "run", return_value=completed) as mock_run:
        pc.run_tool("gcloud", ["version"], text=True)
    _, kwargs = mock_run.call_args
    assert kwargs.get("encoding") == "utf-8"
    assert kwargs.get("errors") == "replace"


# ---------- robust_rmtree ----------

def test_robust_rmtree_removes_directory_tree(tmp_path):
    target = tmp_path / "ws"
    (target / "sub").mkdir(parents=True)
    (target / "sub" / "f.txt").write_text("data")
    pc.robust_rmtree(str(target))
    assert not target.exists()


def test_robust_rmtree_is_noop_on_missing_path(tmp_path):
    missing = tmp_path / "does-not-exist"
    pc.robust_rmtree(str(missing))  # must not raise
    assert not missing.exists()


def test_robust_rmtree_removes_tree_with_readonly_file(tmp_path):
    target = tmp_path / "ws"
    target.mkdir()
    ro = target / "ro.txt"
    ro.write_text("x")
    os.chmod(ro, stat.S_IREAD)
    pc.robust_rmtree(str(target))
    assert not target.exists()


# ---------- configure_console_encoding ----------

def test_configure_console_encoding_is_noop_off_windows():
    fake_sys = SimpleNamespace(stdout=MagicMock(), stderr=MagicMock())
    with patch.object(pc, "IS_WINDOWS", False), patch.object(pc, "sys", fake_sys):
        assert pc.configure_console_encoding() is None
    fake_sys.stdout.reconfigure.assert_not_called()
    fake_sys.stderr.reconfigure.assert_not_called()


def test_configure_console_encoding_forces_utf8_on_windows():
    fake_sys = SimpleNamespace(stdout=MagicMock(), stderr=MagicMock())
    with patch.object(pc, "IS_WINDOWS", True), patch.object(pc, "sys", fake_sys):
        pc.configure_console_encoding()
    fake_sys.stdout.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")
    fake_sys.stderr.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")
