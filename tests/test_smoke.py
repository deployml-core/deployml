"""Smoke tests: verify the package installs and its version resolves.

These are intentionally minimal and independent of the rest of the suite in
`tests/`, which `pytest` already collects and runs alongside these.
"""

import importlib.metadata


def test_distribution_is_installed():
    """The built/installed distribution exposes a version (packaging works)."""
    assert importlib.metadata.version("deployml-core")


def test_cli_get_version_resolves():
    """The CLI resolves its version from package metadata, not the fallback."""
    from deployml.cli.cli import get_version

    version = get_version()
    assert isinstance(version, str)
    assert version not in ("", "version unknown")
    assert version == importlib.metadata.version("deployml-core")
