"""Version identity stamped onto every design and every delivered file."""

from __future__ import annotations

import os
import subprocess

SCHEMA_VERSION = "1.0"
"""IR schema version. Bumped only alongside a migration (see engine.ir.migrate)."""

_UNKNOWN = "unknown"


def engine_version() -> str:
    """Return the engine build identity.

    Resolution order: V2S_ENGINE_VERSION (set by CI and by the service at
    deploy time), then the working-tree git sha, then "unknown". Tests and the
    golden suite pin the env var so output is reproducible.
    """
    pinned = os.environ.get("V2S_ENGINE_VERSION")
    if pinned:
        return pinned
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
    except (OSError, subprocess.SubprocessError):
        return _UNKNOWN
    if sha.returncode != 0:
        return _UNKNOWN
    return sha.stdout.strip() or _UNKNOWN
