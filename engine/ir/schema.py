"""IR schema v1.

Rules that the rest of the engine depends on:

* Units are millimetres everywhere. Machine units appear only in engine.export.
* ``pull_comp_mm_per_side`` is per side, applied along stitch direction.
  Vendors differ on this; ours is per side. Do not reinterpret it downstream.
* ``param_source`` records where each parameter value came from. This is what
  makes a reviewer's edit legible later: a human overriding a profile value is
  a different signal from a human overriding an ML suggestion.
* Serialization is deterministic -- see ``save_ir``.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.version import SCHEMA_VERSION, engine_version

Point = tuple[float, float]
"""(x_mm, y_mm) in design space."""


class ObjectKind(StrEnum):
    RUN = "run"
    SATIN = "satin"
    FILL = "fill"
    TEXT = "text"


class Placement(StrEnum):
    LEFT_CHEST = "left_chest"
    RIGHT_CHEST = "right_chest"
    FULL_BACK = "full_back"
    CAP_FRONT = "cap_front"
    SLEEVE = "sleeve"


class ParamSource(StrEnum):
    """Provenance of a single parameter value."""

    DEFAULT = "default"
    PROFILE = "profile"
    RULE = "rule"
    ML = "ml"
    HUMAN = "human"


class PolylineShape(BaseModel):
    """An open or closed path. Used by run objects."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["polyline"] = "polyline"
    points: list[Point]
    closed: bool = False

    @model_validator(mode="after")
    def _at_least_two_points(self) -> PolylineShape:
        if len(self.points) < 2:
            raise ValueError("polyline needs at least 2 points")
        return self


class RailsShape(BaseModel):
    """A pair of rails. Used by satin objects; stitches span rail to rail."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["rails"] = "rails"
    rails: tuple[list[Point], list[Point]]

    @model_validator(mode="after")
    def _rails_are_paths(self) -> RailsShape:
        left, right = self.rails
        if len(left) < 2 or len(right) < 2:
            raise ValueError("each satin rail needs at least 2 points")
        return self


class FillShape(BaseModel):
    """An outer boundary with optional holes. Used by fill objects."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["polygon"] = "polygon"
    outer: list[Point]
    holes: list[list[Point]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _outer_is_a_ring(self) -> FillShape:
        if len(self.outer) < 3:
            raise ValueError("fill outer boundary needs at least 3 points")
        if any(len(h) < 3 for h in self.holes):
            raise ValueError("every hole needs at least 3 points")
        return self


Shape = Annotated[PolylineShape | RailsShape | FillShape, Field(discriminator="kind")]

_SHAPE_FOR_KIND: dict[ObjectKind, tuple[str, ...]] = {
    ObjectKind.RUN: ("polyline",),
    ObjectKind.SATIN: ("rails",),
    ObjectKind.FILL: ("polygon",),
    ObjectKind.TEXT: ("polyline", "rails", "polygon"),
}


class Thread(BaseModel):
    """A thread on a real chart. Arbitrary RGB is not a thread."""

    model_config = ConfigDict(frozen=True)

    chart: str
    code: str
    rgb: str = Field(pattern=r"^#[0-9a-f]{6}$")
    description: str = ""


class ObjectParams(BaseModel):
    """Stitch parameters for one object.

    Every value here is resolved from the fabric profile unless a rule, a model
    or a human overrode it. Engine logic must not substitute its own constants
    when a field is None -- it resolves against the profile instead.
    """

    model_config = ConfigDict(extra="forbid")

    density_mm: float | None = Field(default=None, gt=0)
    stitch_length_mm: float | None = Field(default=None, gt=0)
    min_stitch_length_mm: float | None = Field(default=None, gt=0)
    pull_comp_mm_per_side: float | None = Field(default=None, ge=0)
    underlay: list[str] | None = None
    max_width_mm: float | None = Field(default=None, gt=0)
    short_stitch: bool | None = None
    bean_repeats: int | None = Field(default=None, ge=1)
    """1 = a plain run. 3 = a bean (triple) stitch for weight."""
    angle_deg: float | None = None


class Locks(BaseModel):
    """A reviewer's decision to keep the engine's hands off this object."""

    model_config = ConfigDict(frozen=True)

    sequence: bool = False
    params: bool = False


class EmbroideryObject(BaseModel):
    """One parametric object. Its stitches are always regenerated from this."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ObjectKind
    shape: Shape
    thread: Thread
    params: ObjectParams = Field(default_factory=ObjectParams)
    param_source: dict[str, ParamSource] = Field(default_factory=dict)
    z_order: int = 0
    entry: Point | None = None
    exit: Point | None = None
    """Entry/exit are chosen by the sequencer unless a reviewer pinned them."""
    locks: Locks = Field(default_factory=Locks)
    flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _shape_matches_kind(self) -> EmbroideryObject:
        allowed = _SHAPE_FOR_KIND[self.kind]
        if self.shape.kind not in allowed:
            raise ValueError(
                f"object kind {self.kind.value!r} takes shape {allowed}, "
                f"got {self.shape.kind!r}"
            )
        unknown = set(self.param_source) - set(ObjectParams.model_fields)
        if unknown:
            raise ValueError(f"param_source names unknown params: {sorted(unknown)}")
        return self


class Design(BaseModel):
    """Everything the engine needs to know about the job, not the artwork."""

    model_config = ConfigDict(extra="forbid")

    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    placement: Placement
    fabric_profile: str
    """A pinned profile reference, e.g. "pique@3". No profile, no file."""
    thread_brand: str


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "approved", "approved_with_edits", "rejected"] = "pending"
    route: Literal["auto", "manual"] = "auto"


class IRDocument(BaseModel):
    """A complete design."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    engine_version: str = Field(default_factory=engine_version)
    design: Design
    objects: list[EmbroideryObject]
    sequence: list[str] = Field(default_factory=list)
    review: Review = Field(default_factory=Review)

    @model_validator(mode="after")
    def _ids_and_sequence_agree(self) -> IRDocument:
        ids = [o.id for o in self.objects]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate object ids: {duplicates}")
        if self.sequence:
            if sorted(self.sequence) != sorted(ids):
                raise ValueError("sequence must list every object id exactly once")
        return self

    def ordered_objects(self) -> list[EmbroideryObject]:
        """Objects in sew order.

        Falls back to z_order (then id, so the result never depends on input
        ordering) when the sequencer has not run yet.
        """
        if self.sequence:
            by_id = {o.id: o for o in self.objects}
            return [by_id[i] for i in self.sequence]
        return sorted(self.objects, key=lambda o: (o.z_order, o.id))


def save_ir(doc: IRDocument, path: str | Path) -> Path:
    """Write an IR document deterministically.

    Same document, same bytes, on any host: sorted keys, fixed separators, and
    a trailing newline so the file is diffable in review.
    """
    path = Path(path)
    payload = json.dumps(
        doc.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    path.write_text(payload + "\n", encoding="utf-8")
    return path


def load_ir(path: str | Path) -> IRDocument:
    """Read an IR document, migrating it forward if it is an older schema."""
    from engine.ir.migrate import migrate

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return IRDocument.model_validate(migrate(raw))
