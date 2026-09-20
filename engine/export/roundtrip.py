"""Round-trip verification: write, read back, compare.

Every writer is verified on every file. A writer that silently drops a colour
change or shifts a penetration by a unit produces a file that looks fine in a
preview and sews wrong, which is exactly the failure this product cannot have.

What is compared, and why not everything:

* **Penetrations** -- exact equality, in order. This is the design.
* **Colour changes** -- exact count. A lost one merges two colours into one.
* **Move lengths** -- no move may exceed the format's per-axis limit after the
  writer's own encoding pass. Per axis, because that is how the formats encode
  a move: one delta per axis, each with its own field.

Trims are reported but not asserted, because formats legitimately differ: DST
encodes a trim as a jump sequence and it reads back as jumps, while PES inserts
implicit trims of its own. Asserting equality there would fail on correct files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pyembroidery

from engine.export.limits import limits_for
from engine.plan import Cmd, StitchPlan
from engine.units import mm_to_units, units_to_mm


class RoundTripError(AssertionError):
    """A written file does not read back as the plan that made it."""


@dataclass
class RoundTripReport:
    """What came back out of the file."""

    path: Path
    extension: str
    penetrations_expected: int
    penetrations_found: int
    first_mismatch: tuple[int, tuple[int, int], tuple[int, int]] | None
    color_changes_expected: int
    color_changes_found: int
    trims_expected: int
    trims_found: int
    max_move_mm: float
    """The longest single-axis delta in the file."""
    max_move_allowed_mm: float
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        state = "ok" if self.ok else "FAILED"
        return (
            f"{self.path.name}: {state} -- {self.penetrations_found} penetrations, "
            f"{self.color_changes_found} colour changes, longest move "
            f"{self.max_move_mm:.1f} mm (limit {self.max_move_allowed_mm:.1f} mm)"
        )


def _read_back(path: Path) -> list[tuple[int, int, int]]:
    pattern = pyembroidery.read(str(path))
    if pattern is None:
        raise RoundTripError(f"{path.name} could not be read back at all")
    return [(x, y, command & pyembroidery.COMMAND_MASK) for x, y, command in pattern.stitches]


def verify(plan: StitchPlan, path: str | Path) -> RoundTripReport:
    """Read a written file back and compare it against the plan."""
    path = Path(path)
    limits = limits_for(path.suffix)

    expected = [
        (mm_to_units(s.x_mm, limits.unit_mm), mm_to_units(-s.y_mm, limits.unit_mm))
        for s in plan.stitches
        if s.cmd is Cmd.STITCH
    ]
    expected_color_changes = sum(1 for s in plan.stitches if s.cmd is Cmd.COLOR_CHANGE)
    expected_trims = sum(1 for s in plan.stitches if s.cmd is Cmd.TRIM)

    read = _read_back(path)
    found = [(x, y) for x, y, cmd in read if cmd == pyembroidery.STITCH]
    found_color_changes = sum(1 for _, _, cmd in read if cmd == pyembroidery.COLOR_CHANGE)
    found_trims = sum(1 for _, _, cmd in read if cmd == pyembroidery.TRIM)

    first_mismatch = None
    for index, (want, got) in enumerate(zip(expected, found, strict=False)):
        if want != got:
            first_mismatch = (index, want, got)
            break

    longest = 0.0
    previous: tuple[int, int] | None = None
    for x, y, cmd in read:
        if cmd in (pyembroidery.STITCH, pyembroidery.JUMP):
            if previous is not None:
                span = max(abs(x - previous[0]), abs(y - previous[1]))
                longest = max(longest, units_to_mm(span, limits.unit_mm))
            previous = (x, y)

    report = RoundTripReport(
        path=path,
        extension=limits.extension,
        penetrations_expected=len(expected),
        penetrations_found=len(found),
        first_mismatch=first_mismatch,
        color_changes_expected=expected_color_changes,
        color_changes_found=found_color_changes,
        trims_expected=expected_trims,
        trims_found=found_trims,
        max_move_mm=longest,
        max_move_allowed_mm=limits.max_move_mm,
    )

    if len(expected) != len(found):
        report.problems.append(
            f"penetration count changed: wrote {len(expected)}, read {len(found)}"
        )
    if first_mismatch is not None:
        index, want, got = first_mismatch
        report.problems.append(f"penetration {index} moved: wrote {want}, read {got}")
    if expected_color_changes != found_color_changes:
        report.problems.append(
            f"colour changes changed: wrote {expected_color_changes}, read {found_color_changes}"
        )
    if longest > limits.max_move_mm + limits.unit_mm / 2:
        report.problems.append(
            f"longest single-axis move {longest:.2f} mm exceeds the {limits.extension} limit "
            f"of {limits.max_move_mm:.2f} mm"
        )
    return report


def verify_or_raise(plan: StitchPlan, path: str | Path) -> RoundTripReport:
    """Verify, and refuse to deliver a file that failed."""
    report = verify(plan, path)
    if not report.ok:
        raise RoundTripError(f"{report.path.name}: " + "; ".join(report.problems))
    return report
