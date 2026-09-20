"""The production worksheet.

The file tells the machine what to do; the worksheet tells the operator. A
delivery without one makes the shop guess at thread order, and a guess is a
ruined garment. Plain text in M0; the PDF/HTML version ships with delivery (M7).
"""

from __future__ import annotations

from engine.ir.schema import IRDocument
from engine.plan import Cmd, StitchPlan
from engine.profiles.loader import FabricProfile

_RUN_TIME_SPM = 700
"""Stitches per minute. A conservative commercial multi-needle average, used
only for an estimate on the worksheet -- never for anything the engine decides."""


def estimate_runtime_minutes(plan: StitchPlan) -> float:
    """Rough machine time. Trims and colour changes add handling this ignores."""
    return plan.stitch_count() / _RUN_TIME_SPM


def worksheet(doc: IRDocument, plan: StitchPlan, profile: FabricProfile) -> str:
    """Render the operator sheet for one design."""
    min_x, min_y, max_x, max_y = plan.extents_mm()
    trims = sum(1 for s in plan.stitches if s.cmd is Cmd.TRIM)
    jumps = sum(1 for s in plan.stitches if s.cmd is Cmd.JUMP)

    lines = [
        "PRODUCTION WORKSHEET",
        "=" * 60,
        f"Placement        : {doc.design.placement.value}",
        f"Sewn size        : {max_x - min_x:.1f} x {max_y - min_y:.1f} mm",
        f"Ordered size     : {doc.design.width_mm:.1f} x {doc.design.height_mm:.1f} mm",
        f"Fabric profile   : {profile.ref}  ({profile.description})",
        f"Stabilizer       : {profile.materials.stabilizer}",
        f"Topping          : {'yes' if profile.materials.topping else 'no'}",
        "",
        f"Stitches         : {plan.stitch_count()}",
        f"Colour changes   : {max(len(plan.threads) - 1, 0)}",
        f"Trims / jumps    : {trims} / {jumps}",
        f"Est. run time    : {estimate_runtime_minutes(plan):.1f} min at {_RUN_TIME_SPM} spm",
        "",
        "COLOUR SEQUENCE",
        "-" * 60,
    ]
    for index, thread in enumerate(plan.threads, start=1):
        label = thread.description or thread.code
        lines.append(f"{index:>2}. {thread.chart} {thread.code:<8} {thread.rgb}  {label}")

    lines += [
        "",
        "VERSIONS",
        "-" * 60,
        f"Engine  : {plan.engine_version}",
        f"Schema  : {plan.schema_version}",
        f"Profile : {profile.ref}",
        "",
    ]
    if not profile.calibrated:
        lines += [
            "!! This profile is NOT calibrated. Its densities, compensation and",
            "!! underlay are industry starting defaults, not values proven on our",
            "!! machines. Test sew on scrap before any production run.",
            "",
        ]
    lines += ["Test sew on scrap before any production run.", ""]
    return "\n".join(lines)
