"""The production worksheet.

The file tells the machine what to do; the worksheet tells the operator. A
delivery without one makes the shop guess at thread order, and a guess is a
ruined garment. Plain text in M0; the PDF/HTML version ships with delivery (M7).
"""

from __future__ import annotations

from engine.ir.schema import IRDocument
from engine.machines.setup import MachineSetup, resolve_setup
from engine.plan import Cmd, StitchPlan
from engine.profiles.loader import FabricProfile


def estimate_runtime_minutes(plan: StitchPlan, setup: MachineSetup) -> float:
    """Rough machine time at the speed this machine will actually hold.

    Needle time only. Trims, colour changes, hooping and operator handling are
    what actually separate this number from a shop's real throughput, so treat
    it as a floor, not a quote.
    """
    return plan.stitch_count() / setup.max_spm


def worksheet(
    doc: IRDocument,
    plan: StitchPlan,
    profile: FabricProfile,
    setup: MachineSetup | None = None,
) -> str:
    """Render the operator sheet for one design.

    Without a machine profile the sheet still prints, using the fabric
    profile's generic numbers and saying so -- a shop that has not described
    its hardware yet still gets a usable sheet.
    """
    setup = setup or resolve_setup(profile, doc, plan)
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
        *(
            [
                f"Sew field        : {setup.field_width_mm:.0f} x "
                f"{setup.field_height_mm:.0f} mm"
            ]
            if setup.field_width_mm and setup.field_height_mm
            else []
        ),
        "",
        f"Stitches         : {plan.stitch_count()}",
        f"Colour changes   : {max(len(plan.threads) - 1, 0)}",
        f"Trims / jumps    : {trims} / {jumps}",
        f"Est. run time    : {estimate_runtime_minutes(plan, setup):.1f} min at "
        f"{setup.max_spm} spm, needle time only",
        "",
        "MACHINE SETUP",
        "-" * 60,
        f"Machine          : {setup.machine_ref or 'not specified'}",
        f"Thread           : {profile.machine.thread_weight_wt} wt {profile.machine.thread_type}",
        f"Needle           : {profile.machine.needle_size}",
        f"Max speed        : {setup.max_spm} spm (from the {setup.speed_source} profile)",
        f"Bobbin tension   : {setup.bobbin_gf_min:.0f}-{setup.bobbin_gf_max:.0f} gf "
        f"({'gauged on this machine' if setup.tension_source == 'machine' else 'generic'})",
        f"Top tension      : ~{setup.top_gf:.0f} gf",
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
    if setup.blockers:
        lines += ["!! WILL NOT SEW ON THIS MACHINE", "-" * 60]
        lines += [f"!! {blocker}" for blocker in setup.blockers]
        lines.append("")
    if setup.warnings:
        lines += ["NOTES", "-" * 60]
        lines += [f"- {warning}" for warning in setup.warnings]
        lines.append("")

    lines += ["Test sew on scrap before any production run.", ""]
    return "\n".join(lines)
