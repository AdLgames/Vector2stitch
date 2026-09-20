"""Vector2stitch engine: a pure library.

The engine never imports from /service, /web or /editor, and it never reaches
for a network, database or queue. The service, the golden suite and the lab
tools all call this same code path.
"""

from engine.version import SCHEMA_VERSION, engine_version

__all__ = ["engine_version", "SCHEMA_VERSION"]
