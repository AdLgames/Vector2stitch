"""The production worksheet.

The file tells the machine what to do; the worksheet tells the operator. A
delivery without one makes the shop guess at thread order, and a guess is a
ruined garment. Plain text in M0; the PDF/HTML version ships with delivery (M7).
"""

from __future__ import annotations

from engine.ir.schema import IRDocument
from engine.plan import Cmd, StitchPlan
from engine.profiles.loader import FabricProfile


def estimate_runtime_minutes(plan: StitchPlan, profile: FabricProfile) -> float:
    """Rough machine time at the profile's recommended speed.

    Needle time only. Trims, colour changes, hooping and operator handling are
    what actually separate this number from a shop's real throughput, so treat
    it as a floor, not a quote.
    """
    return plan.stitch_count() / profile.machine.max_spm


def top_tension_gf(profile: FabricProfile) -> float:
    """Top tension target, derived from the gauge-measured bobbin baseline.

    Setting top tension by feel is how two operators produce two different
    results from the same file. The ratio comes from the profile.
    """
    baseline = (profile.machine.bobbin_tension_gf_min + profile.machine.bobbin_tension_gf_max) / 2
    return baseline * profile.machine.top_to_bobbin_tension_ratio


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
        f"Est. run time    : {estimate_runtime_minutes(plan, profile):.1f} min at "
        f"{profile.machine.max_spm} spm, needle time only",
        "",
        "MACHINE SETUP",
        "-" * 60,
        f"Thread           : {profile.machine.thread_weight_wt} wt {profile.machine.thread_type}",
        f"Needle           : {profile.machine.needle_size}",
        f"Max speed        : {profile.machine.max_spm} spm",
        f"Bobbin tension   : {profile.machine.bobbin_tension_gf_min:.0f}"
        f"-{profile.machine.bobbin_tension_gf_max:.0f} gf (gauge measured)",
        f"Top tension      : ~{top_tension_gf(profile):.0f} gf "
        f"({profile.machine.top_to_bobbin_tension_ratio:g}x the bobbin baseline)",
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
