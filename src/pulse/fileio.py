"""Private-file helpers: everything sensitive is written atomically with mode 0600."""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Any

PRIVATE_MODE = 0o600


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except PermissionError:
        # Bind-mount roots (e.g. Docker volumes on macOS/Colima) may refuse chmod; the
        # host-side directory is created 0700 by the setup steps, and files stay 0600.
        logging.getLogger(__name__).warning("could not chmod %s to 0700", path)


def write_private(path: Path, data: str | bytes) -> None:
    """Atomically write ``data`` to ``path`` with 0600 permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    raw = data.encode() if isinstance(data, str) else data
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, PRIVATE_MODE)
    try:
        os.fchmod(fd, PRIVATE_MODE)  # umask can't widen it, but be explicit
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    tmp.replace(path)


def write_private_json(path: Path, obj: Any) -> None:
    write_private(path, json.dumps(obj, indent=2, sort_keys=False) + "\n")


def is_private(path: Path) -> bool:
    mode = stat.S_IMODE(path.stat().st_mode)
    return mode & 0o077 == 0
