"""Resolving a fabric profile against the machine that will sew it.

The fabric profile holds generic, industry-derived numbers. The machine
profile holds what the hardware in the room actually does. This module
combines them into the setup an operator works to, and says plainly what will
not work.

The rule it follows everywhere: **take the more conservative value, and never
change a stitch.** A slower ceiling wins over a faster one. A locally measured
tension wins over a generic one. A design that does not fit the field is
refused, not shrunk.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.ir.schema import IRDocument, Placement
from engine.machines.loader import MachineProfile
from engine.plan import Cmd, StitchPlan
from engine.profiles.loader import FabricProfile

CAP_PLACEMENTS = {Placement.CAP_FRONT}
_FIT_TOLERANCE_MM = 0.1
"""One machine unit. Below this, a size difference is rounding, not a misfit."""


@dataclass
class MachineSetup:
    """What to set the machine to, and what stands in the way."""

    fabric_ref: str
    machine_ref: str | None
    max_spm: int
    speed_source: str
    bobbin_gf_min: float
    bobbin_gf_max: float
    top_gf: float
    tension_source: str
    """"machine" once someone has gauged this machine; "fabric" until then."""
    field_width_mm: float | None
    field_height_mm: float | None
    blockers: list[str] = field(default_factory=list)
    """Reasons this design cannot sew here. A file should not be delivered
    against a machine that has one."""
    warnings: list[str] = field(default_factory=list)
    """Things the operator needs to know but that do not stop the run."""

    @property
    def ok(self) -> bool:
        return not self.blockers


def resolve_setup(
    fabric: FabricProfile,
    doc: IRDocument,
    plan: StitchPlan | None = None,
    machine: MachineProfile | None = None,
    formats: list[str] | None = None,
) -> MachineSetup:
    """Combine a fabric profile with a machine profile, if there is one."""
    is_cap = doc.design.placement in CAP_PLACEMENTS

    if machine is None:
        return MachineSetup(
            fabric_ref=fabric.ref,
            machine_ref=None,
            max_spm=fabric.machine.max_spm,
            speed_source="fabric",
            bobbin_gf_min=fabric.machine.bobbin_tension_gf_min,
            bobbin_gf_max=fabric.machine.bobbin_tension_gf_max,
            top_gf=_top_gf(
                fabric.machine.bobbin_tension_gf_min,
                fabric.machine.bobbin_tension_gf_max,
                fabric.machine.top_to_bobbin_tension_ratio,
            ),
            tension_source="fabric",
            field_width_mm=None,
            field_height_mm=None,
            warnings=[
                "No machine profile: speed and tension are the fabric profile's generic "
                "values, and nothing has been checked against a real sew field."
            ],
        )

    machine_ceiling = machine.speed.max_spm_cap if is_cap else machine.speed.max_spm_flat
    max_spm = min(fabric.machine.max_spm, machine_ceiling)
    speed_source = "machine" if machine_ceiling <= fabric.machine.max_spm else "fabric"

    if machine.tension is not None:
        bobbin_min, bobbin_max = machine.tension.bobbin_gf_min, machine.tension.bobbin_gf_max
        ratio = machine.tension.top_to_bobbin_ratio
        tension_source = "machine"
    else:
        bobbin_min = fabric.machine.bobbin_tension_gf_min
        bobbin_max = fabric.machine.bobbin_tension_gf_max
        ratio = fabric.machine.top_to_bobbin_tension_ratio
        tension_source = "fabric"

    if is_cap:
        width = machine.fields.cap_width_mm
        height = machine.fields.cap_height_mm
    else:
        width = machine.fields.flat_width_mm
        height = machine.fields.flat_height_mm

    setup = MachineSetup(
        fabric_ref=fabric.ref,
        machine_ref=machine.ref,
        max_spm=max_spm,
        speed_source=speed_source,
        bobbin_gf_min=bobbin_min,
        bobbin_gf_max=bobbin_max,
        top_gf=_top_gf(bobbin_min, bobbin_max, ratio),
        tension_source=tension_source,
        field_width_mm=width,
        field_height_mm=height,
    )

    if is_cap and not machine.capabilities.cap_driver:
        setup.blockers.append(
            f"{doc.design.placement.value} needs a cap driver; {machine.ref} does not have one"
        )

    if plan is not None:
        _check_fit(setup, plan, width, height)
        _check_colors(setup, plan, machine)
        _check_trims(setup, plan, machine)

    if formats:
        unsupported = [f for f in formats if f not in machine.capabilities.formats]
        if unsupported:
            setup.warnings.append(
                f"{machine.ref} does not read {', '.join(sorted(unsupported))}; "
                f"it reads {', '.join(machine.capabilities.formats)}"
            )

    if not machine.calibrated:
        setup.warnings.append(
            f"{machine.ref} is not calibrated: these are spec-sheet numbers, not readings "
            "taken off this machine."
        )

    if tension_source == "fabric":
        setup.warnings.append(
            "No gauged tension for this machine; using the fabric profile's generic range."
        )

    return setup


def _top_gf(bobbin_min: float, bobbin_max: float, ratio: float) -> float:
    return (bobbin_min + bobbin_max) / 2 * ratio


def _check_fit(
    setup: MachineSetup, plan: StitchPlan, width: float | None, height: float | None
) -> None:
    """A design larger than the field cannot sew, at any speed."""
    if width is None or height is None:
        return
    min_x, min_y, max_x, max_y = plan.extents_mm()
    design_width, design_height = max_x - min_x, max_y - min_y
    if design_width > width + _FIT_TOLERANCE_MM or design_height > height + _FIT_TOLERANCE_MM:
        setup.blockers.append(
            f"design is {design_width:.1f} x {design_height:.1f} mm; the field is "
            f"{width:.1f} x {height:.1f} mm"
        )


def _check_colors(setup: MachineSetup, plan: StitchPlan, machine: MachineProfile) -> None:
    """More colours than needles means a rethread mid-run, not a failure."""
    colors = len(plan.threads)
    if colors > machine.needles_per_head:
        setup.warnings.append(
            f"design uses {colors} colours; {machine.ref} has {machine.needles_per_head} "
            "needles, so the run needs a rethread partway through"
        )


def _check_trims(setup: MachineSetup, plan: StitchPlan, machine: MachineProfile) -> None:
    """A machine without a trimmer stops on every trim for a manual cut."""
    if machine.capabilities.auto_trim:
        return
    trims = sum(1 for s in plan.stitches if s.cmd is Cmd.TRIM)
    if trims:
        setup.warnings.append(
            f"{machine.ref} has no auto trimmer; {trims} trim(s) will stop the machine "
            "for a manual cut"
        )
