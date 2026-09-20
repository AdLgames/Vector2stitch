"""Schema migrations.

An old design must always reopen. Every schema bump adds one step here; the
chain runs in order until the document reaches SCHEMA_VERSION.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from engine.version import SCHEMA_VERSION

Migration = Callable[[dict[str, Any]], dict[str, Any]]

_STEPS: dict[str, tuple[str, Migration]] = {}
"""from_version -> (to_version, step). Empty at schema 1.0; the first bump
registers "1.0" -> ("1.1", _v1_0_to_v1_1)."""


class UnknownSchemaVersion(ValueError):
    """The document is newer than this engine, or from a fork we do not know."""


def migrate(raw: dict[str, Any]) -> dict[str, Any]:
    """Bring a raw IR payload up to the current schema version."""
    doc = dict(raw)
    version = doc.get("schema_version")
    if version is None:
        raise UnknownSchemaVersion("document has no schema_version")

    seen: set[str] = set()
    while version != SCHEMA_VERSION:
        if version in seen:
            raise UnknownSchemaVersion(f"migration cycle at schema {version!r}")
        seen.add(version)
        step = _STEPS.get(version)
        if step is None:
            raise UnknownSchemaVersion(
                f"no migration path from schema {version!r} to {SCHEMA_VERSION!r}"
            )
        target, fn = step
        doc = fn(doc)
        doc["schema_version"] = target
        version = target
    return doc
