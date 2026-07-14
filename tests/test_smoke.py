"""Smoke tests: verify the package installs and its version resolves.

These are intentionally minimal and run against whatever source is on `main`.
The broader unit suite currently lives on the `dev` branch and targets modules
not yet merged to `main`; it should be wired in once those land here.
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
