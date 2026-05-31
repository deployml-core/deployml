"""Cross platform helpers so the deployml CLI behaves identically on Windows,
macOS, and Linux.

All operating system awareness lives here. Command modules call run_tool instead
of subprocess.run for external tools, call configure_console_encoding once at
startup, and use robust_rmtree for workspace cleanup. This keeps every CLI command
the same across operating systems while the engine adapts underneath.

The Windows problems this module solves:

- gcloud, bq, and gsutil ship as .cmd batch wrappers, not .exe files, so
  subprocess.run with a bare name fails with FileNotFoundError, WinError 2.
  resolve_tool finds the real wrapper and run_tool launches it.
- The gcloud SDK and Docker also ship an extensionless launcher script beside the
  real wrapper. subprocess cannot execute that script, so resolve_tool prefers an
  executable extension and never returns the bare launcher.
- The default console code page is cp1252, so printing emoji or box glyphs raises
  UnicodeEncodeError. configure_console_encoding forces UTF-8 with replacement.
- Workspace cleanup hits read only files and transient locks, so a plain rmtree
  raises PermissionError. robust_rmtree clears the read only bit and retries.
"""

import os
import shutil
import stat
import subprocess
import sys
import time

IS_WINDOWS = os.name == "nt"

# Extensions Windows treats as directly executable. resolve_tool uses these to
# reject the extensionless launcher scripts that ship beside gcloud.cmd, bq.cmd,
# gsutil.cmd, and docker.exe.
_WINDOWS_EXEC_EXTS = (".exe", ".cmd", ".bat", ".com")


def resolve_tool(name: str) -> str:
    """Return the absolute path to an external tool, honoring PATHEXT on Windows.

    On Windows shutil.which can return an extensionless launcher script that ships
    alongside the real wrapper, for example the gcloud bash script next to
    gcloud.cmd. subprocess cannot launch that script, so when the first match has
    no executable extension we look specifically for a .cmd, .exe, or .bat wrapper.

    Raises FileNotFoundError with an actionable message if the tool is missing.
    """
    path = shutil.which(name)
    if path is None:
        raise FileNotFoundError(
            f"Required tool '{name}' was not found on PATH. "
            f"Install it and reopen your shell, then retry."
        )
    if IS_WINDOWS and os.path.splitext(path)[1].lower() not in _WINDOWS_EXEC_EXTS:
        for ext in (".cmd", ".exe", ".bat"):
            candidate = shutil.which(name + ext)
            if candidate:
                return candidate
    return path


def run_tool(name: str, args: list, **kwargs) -> subprocess.CompletedProcess:
    """Run an external command the same way on every operating system.

    Resolves the tool to its real path so .cmd wrappers like gcloud.cmd work on
    Windows. Pass the args list you would have passed after the tool name. Every
    subprocess.run keyword argument passes through unchanged, so capture_output,
    text, check, input, cwd, env, and stdout or stderr redirection behave exactly
    as a direct subprocess.run call would.
    """
    resolved = resolve_tool(name)
    try:
        return subprocess.run([resolved, *args], **kwargs)
    except OSError:
        # Some Windows Python builds cannot launch a .cmd or .bat directly and
        # raise OSError, WinError 193, when CreateProcess runs. That happens before
        # the child process starts, so retrying through the command interpreter is
        # safe and produces no duplicate side effects. Only batch wrappers need it.
        if IS_WINDOWS and resolved.lower().endswith((".cmd", ".bat")):
            comspec = os.environ.get("COMSPEC", "cmd.exe")
            return subprocess.run([comspec, "/c", resolved, *args], **kwargs)
        raise


def configure_console_encoding() -> None:
    """Force UTF-8 on Windows stdout and stderr so non ASCII output never crashes.

    Emoji and box drawing glyphs in CLI messages raise UnicodeEncodeError on a
    legacy cp1252 console. Reconfiguring with errors set to replace guarantees the
    command keeps running even on a strict console, degrading an unprintable glyph
    to a placeholder instead of crashing. No effect off Windows.
    """
    if not IS_WINDOWS:
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            # stdout or stderr was replaced by a plain object, for example under a
            # test harness, so there is nothing to reconfigure.
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def robust_rmtree(path) -> None:
    """Remove a directory tree, surviving Windows read only files and brief locks.

    Windows marks some files read only, which shutil.rmtree does not clear, and a
    sync client or scanner can hold a file open for a moment, so a plain rmtree
    raises PermissionError. The error handler clears the read only bit and retries,
    then pauses briefly and retries once more before giving up.
    """
    def _handle(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except Exception:
            time.sleep(0.2)
            func(target)

    if not os.path.exists(path):
        return
    try:
        # Python 3.12 renamed the rmtree error callback from onerror to onexc.
        shutil.rmtree(path, onexc=_handle)
    except TypeError:
        shutil.rmtree(path, onerror=_handle)
