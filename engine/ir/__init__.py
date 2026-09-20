"""The object model (IR). Everything upstream produces it; everything
downstream consumes it. Stitches are regenerated from objects, never edited."""

from engine.ir.migrate import migrate
from engine.ir.schema import (
    Design,
    EmbroideryObject,
    FillShape,
    IRDocument,
    ObjectKind,
    ObjectParams,
    ParamSource,
    Placement,
    PolylineShape,
    RailsShape,
    Review,
    Thread,
    load_ir,
    save_ir,
)

__all__ = [
    "Design",
    "EmbroideryObject",
    "FillShape",
    "IRDocument",
    "ObjectKind",
    "ObjectParams",
    "ParamSource",
    "Placement",
    "PolylineShape",
    "RailsShape",
    "Review",
    "Thread",
    "load_ir",
    "migrate",
    "save_ir",
]
