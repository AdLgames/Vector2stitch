"""The measurement sheet: what the operator writes on at the machine.

Paired with a calibration pattern. Every row is one target, with the designed
dimension printed and a blank for the measured one, so a sew-out comes back as
numbers rather than as "looked about right".
"""

from __future__ import annotations

from engine.ir.schema import IRDocument
from engine.lab.targets import MeasurementTarget
from engine.machines.setup import MachineSetup
from engine.profiles.loader import FabricProfile


def measurement_sheet(
    pattern_name: str,
    doc: IRDocument,
    profile: FabricProfile,
    setup: MachineSetup,
    targets: list[MeasurementTarget],
) -> str:
    """Render the sheet for one sewn pattern."""
    lines = [
        f"MEASUREMENT SHEET -- {pattern_name}",
        "=" * 72,
        f"Fabric profile   : {profile.ref}"
        f"{'' if profile.calibrated else '   (NOT calibrated)'}",
        f"Machine          : {setup.machine_ref or 'not specified'}",
        f"Engine           : {doc.engine_version}",
        f"Speed            : {setup.max_spm} spm",
        f"Bobbin tension   : {setup.bobbin_gf_min:.0f}-{setup.bobbin_gf_max:.0f} gf"
        f"   Top: ~{setup.top_gf:.0f} gf",
        "",
        "Record these before sewing. An unrecorded variable makes the whole",
        "measurement worthless -- it moves a parameter for the wrong reason.",
        "",
        "  Date ............  Operator ........................",
        "  Thread ..........................................",
        "  Needle ..........  Stabilizer ....................",
        "  Topping .........  Actual speed ............. spm",
        "",
        "MEASUREMENTS",
        "-" * 72,
        f"{'target':<22}{'axis':<10}{'designed':>10}{'measured':>10}  {'tol':>5}",
        "-" * 72,
    ]
    for target in targets:
        lines.append(
            f"{target.id:<22}{target.axis.value:<10}{target.designed_mm:>9.2f} "
            f"{'':>10}  {target.tolerance_mm:>4.1f}"
        )
    lines += [
        "-" * 72,
        "",
        "WHAT EACH TARGET IS",
        "-" * 72,
    ]
    for target in targets:
        lines.append(f"{target.id:<22}{target.description}")

    lines += [
        "",
        "DEFECTS SEEN (circle)",
        "-" * 72,
        "  gapping   puckering   thread_break   bulletproof   looping_satin",
        "  sunken_stitches   illegible_text   jagged_curves   visible_travel",
        "  fill_distortion",
        "",
        "Photograph the sew-out under the lab's standard lighting before it",
        "leaves the machine.",
        "",
    ]
    return "\n".join(lines)
