"""The stitch plan: the engine's output, and the only thing /export consumes.

A plan is a flat, ordered command stream in millimetres. It is deliberately
format-agnostic: DST/PES/JEF/EXP quirks live in engine.export, never here.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from engine.version import SCHEMA_VERSION, engine_version


class Cmd(StrEnum):
    """Machine commands the engine emits."""

    STITCH = "stitch"
    JUMP = "jump"
    TRIM = "trim"
    COLOR_CHANGE = "color_change"
    STOP = "stop"
    END = "end"


class PlanStitch(BaseModel):
    """One command at one point, in millimetres."""

    model_config = ConfigDict(frozen=True)

    x_mm: float
    y_mm: float
    cmd: Cmd = Cmd.STITCH
    object_id: str | None = None
    """Which IR object produced this. Carried through so checks and the editor
    can point at an object rather than a stitch index."""


class PlanThread(BaseModel):
    """A thread in the colour sequence."""

    model_config = ConfigDict(frozen=True)

    chart: str
    code: str
    rgb: str = Field(pattern=r"^#[0-9a-f]{6}$")
    description: str = ""


class StitchPlan(BaseModel):
    """An ordered command stream plus the threads it references."""

    schema_version: str = SCHEMA_VERSION
    engine_version: str = Field(default_factory=engine_version)
    profile_ref: str
    stitches: list[PlanStitch] = Field(default_factory=list)
    threads: list[PlanThread] = Field(default_factory=list)

    def stitch_count(self) -> int:
        """Needle penetrations, which is what a decorator is billed for.

        Jumps, trims, colour changes and the end command do not penetrate.
        """
        return sum(1 for s in self.stitches if s.cmd is Cmd.STITCH)

    def extents_mm(self) -> tuple[float, float, float, float]:
        """(min_x, min_y, max_x, max_y) over penetrations and jumps."""
        points = [s for s in self.stitches if s.cmd in (Cmd.STITCH, Cmd.JUMP)]
        if not points:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [s.x_mm for s in points]
        ys = [s.y_mm for s in points]
        return (min(xs), min(ys), max(xs), max(ys))
