"""Writing machine files.

The only place in the engine that knows about machine units, and the only
place that touches pyembroidery. Everything above here is millimetres.

Coordinate convention: engine design space is y-up (the way a machine field and
a digitizer both think). pyembroidery's internal space is y-down, so y is
negated at this boundary and negated back when reading. Whether the design
lands right way up on a real hoop is not something a round-trip test can prove
-- that is what the M0 acceptance sew-out is for.
"""

from __future__ import annotations

import math
from pathlib import Path

import pyembroidery

from engine.export.limits import FormatLimits, limits_for
from engine.plan import Cmd, PlanStitch, StitchPlan
from engine.units import mm_to_units

FIXED_FILE_TIMESTAMP = "19800101000000"
"""The creation timestamp written into formats that carry one (JEF).

Deliberately fixed rather than "now". Two runs of the same engine on the same
design must produce byte-identical files -- that is what makes a golden suite
meaningful and a customer complaint reproducible -- and a wall-clock stamp
breaks that for no benefit. Real provenance (engine, profile and schema
version, order and delivery time) lives in the worksheet and the delivery
record, not in a header field no operator reads. Override per call where a
customer's workflow genuinely needs a real date.
"""

_COMMAND = {
    Cmd.STITCH: pyembroidery.STITCH,
    Cmd.JUMP: pyembroidery.JUMP,
    Cmd.TRIM: pyembroidery.TRIM,
    Cmd.COLOR_CHANGE: pyembroidery.COLOR_CHANGE,
    Cmd.STOP: pyembroidery.STOP,
    Cmd.END: pyembroidery.END,
}


def split_long_moves(stitches: list[PlanStitch], max_move_mm: float) -> list[PlanStitch]:
    """Break moves longer than the format allows into legal steps.

    A DST jump cannot exceed 12.1 mm, so a 40 mm travel is four jumps. We split
    here rather than leaving it to the writer library: the split points end up
    in the file, in the checks, and in the simulator, so all three agree on
    what the machine will do.
    """
    if max_move_mm <= 0:
        raise ValueError("max_move_mm must be positive")

    out: list[PlanStitch] = []
    previous: PlanStitch | None = None
    for stitch in stitches:
        if previous is not None and stitch.cmd in (Cmd.STITCH, Cmd.JUMP):
            span = math.hypot(stitch.x_mm - previous.x_mm, stitch.y_mm - previous.y_mm)
            if span > max_move_mm:
                steps = math.ceil(round(span / max_move_mm, 9))
                for step in range(1, steps):
                    ratio = step / steps
                    out.append(
                        PlanStitch(
                            x_mm=previous.x_mm + (stitch.x_mm - previous.x_mm) * ratio,
                            y_mm=previous.y_mm + (stitch.y_mm - previous.y_mm) * ratio,
                            cmd=stitch.cmd,
                            object_id=stitch.object_id,
                        )
                    )
        out.append(stitch)
        if stitch.cmd in (Cmd.STITCH, Cmd.JUMP):
            previous = stitch
    return out


def to_pattern(plan: StitchPlan, limits: FormatLimits) -> pyembroidery.EmbPattern:
    """Build a pyembroidery pattern from a plan, in machine units."""
    pattern = pyembroidery.EmbPattern()
    for thread in plan.threads:
        pattern.add_thread(
            {
                "hex": thread.rgb,
                "description": thread.description or thread.code,
                "catalog": thread.code,
                "brand": thread.chart,
            }
        )

    for stitch in split_long_moves(plan.stitches, limits.max_move_mm):
        pattern.add_stitch_absolute(
            _COMMAND[stitch.cmd],
            mm_to_units(stitch.x_mm, limits.unit_mm),
            mm_to_units(-stitch.y_mm, limits.unit_mm),
        )
    return pattern


def write(plan: StitchPlan, path: str | Path, *, created: str | None = None) -> Path:
    """Write one machine file. Format comes from the extension.

    `created` is a "YYYYMMDDHHMMSS" stamp for formats that store one; it
    defaults to FIXED_FILE_TIMESTAMP so output stays byte-reproducible.
    """
    path = Path(path)
    limits = limits_for(path.suffix)
    pattern = to_pattern(plan, limits)
    pattern.write(str(path), date=created or FIXED_FILE_TIMESTAMP)
    return path


def write_all(
    plan: StitchPlan,
    directory: str | Path,
    stem: str,
    formats: list[str],
    *,
    created: str | None = None,
) -> list[Path]:
    """Write the delivery set. Order of `formats` is preserved."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return [
        write(plan, directory / f"{stem}.{fmt.lstrip('.')}", created=created) for fmt in formats
    ]
