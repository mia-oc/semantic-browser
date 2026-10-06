"""Where the daemon keeps its private files. Stdlib only (imported by the thin client)."""

from __future__ import annotations

import contextlib
import os
import stat
import tempfile
from pathlib import Path

# macOS limits AF_UNIX paths to 104 bytes; leave room for "<name>.sock" (max 32 + 5).
_MAX_DIR = 60


def home() -> Path:
    return Path(os.environ.get("SB_HOME") or (Path.home() / ".semantic-browser"))


def private_dir(d: Path) -> Path:
    """Create ``d`` (0700) and refuse it unless it is a real directory owned by us that nobody else can enter.

    Protects against a pre-created ``/tmp/sb-<uid>`` (symlink or another user's directory) in the short-path
    fallback, where an attacker could otherwise plant a fake daemon socket and read what the agent types.
    """
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    with contextlib.suppress(OSError):
        d.chmod(0o700)
    if not hasattr(os, "getuid"):  # pragma: no cover - non-POSIX
        return d
    st = d.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise PermissionError(f"{d} must be a private directory owned by you (mode 0700); remove or fix it")
    return d


def run_dir() -> Path:
    d = home() / "run"
    if len(str(d)) > _MAX_DIR:  # long $HOME / $SB_HOME: fall back to a short per-user dir
        d = Path(tempfile.gettempdir()) / f"sb-{os.getuid()}" / "run"
        if len(str(d)) > _MAX_DIR:
            d = Path("/tmp") / f"sb-{os.getuid()}" / "run"
    private_dir(d.parent)
    return private_dir(d)
