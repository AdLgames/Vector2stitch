"""The golden suite.

Unit tests say a function still does what it did. The golden suite says the
*engine* still does: real designs, generated end to end, compared against
output a digitizer once approved.

It compares metrics rather than bytes. Byte equality would fail on every
harmless refactor and teach everyone to regenerate without looking, which is
how a regression net becomes a rubber stamp. Metrics fail when the stitches
actually move, and the diff says which way.

Approving a change is deliberate: `v2s-lab golden run --approve`, and once a
digitizer exists, their sign-off on what moved and why.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.checks import run_checks
from engine.ir.schema import IRDocument, load_ir
from engine.plan import Cmd, StitchPlan
from engine.profiles.loader import load_profile
from engine.stitchgen import generate

DESIGNS = Path("golden/designs")
APPROVED = Path("golden/approved")

STITCH_COUNT_TOLERANCE = 0.01
"""A one per cent drift in stitch count passes. Anything the engine does to
geometry moves it further than that; rounding does not."""
EXTENT_TOLERANCE_MM = 0.05
"""Half a machine unit. Below this the design has not moved."""
LENGTH_BUCKET_MM = 0.5
"""Stitch lengths are compared as a histogram at this resolution: a change in
the *distribution* is what density and compensation changes look like."""


@dataclass
class Comparison:
    """One design's metrics against what was approved."""

    design: str
    profile_ref: str
    differences: list[str] = field(default_factory=list)
    approved: bool = True
    """False when nothing has ever been approved for this design."""

    @property
    def ok(self) -> bool:
        return self.approved and not self.differences


def metrics(doc: IRDocument, plan: StitchPlan) -> dict[str, Any]:
    """The numbers a regression is visible in."""
    profile = load_profile(plan.profile_ref)
    report = run_checks(doc, plan, profile)
    min_x, min_y, max_x, max_y = plan.extents_mm()

    lengths: Counter[float] = Counter()
    previous = None
    for stitch in plan.stitches:
        if stitch.cmd is not Cmd.STITCH:
            previous = None
            continue
        if previous is not None:
            span = (
                (stitch.x_mm - previous.x_mm) ** 2 + (stitch.y_mm - previous.y_mm) ** 2
            ) ** 0.5
            lengths[round(span / LENGTH_BUCKET_MM) * LENGTH_BUCKET_MM] += 1
        previous = stitch

    return {
        "profile_ref": plan.profile_ref,
        "stitch_count": plan.stitch_count(),
        "trims": sum(1 for s in plan.stitches if s.cmd is Cmd.TRIM),
        "jumps": sum(1 for s in plan.stitches if s.cmd is Cmd.JUMP),
        "color_changes": sum(1 for s in plan.stitches if s.cmd is Cmd.COLOR_CHANGE),
        "threads": len(plan.threads),
        "width_mm": round(max_x - min_x, 3),
        "height_mm": round(max_y - min_y, 3),
        "length_histogram": {str(k): v for k, v in sorted(lengths.items())},
        "blocking_findings": sorted(f.rule for f in report.blockers),
        "warning_findings": sorted(f.rule for f in report.warnings),
    }


def compare(design: str, current: dict[str, Any], approved: dict[str, Any]) -> Comparison:
    """Diff current metrics against approved ones, tolerance by tolerance."""
    result = Comparison(design=design, profile_ref=current["profile_ref"])

    expected = approved["stitch_count"]
    drift = abs(current["stitch_count"] - expected) / max(expected, 1)
    if drift > STITCH_COUNT_TOLERANCE:
        result.differences.append(
            f"stitch count {approved['stitch_count']} -> {current['stitch_count']} "
            f"({drift * 100:.1f}%)"
        )

    for key in ("trims", "jumps", "color_changes", "threads"):
        if current[key] != approved[key]:
            result.differences.append(f"{key} {approved[key]} -> {current[key]}")

    for key in ("width_mm", "height_mm"):
        if abs(current[key] - approved[key]) > EXTENT_TOLERANCE_MM:
            result.differences.append(f"{key} {approved[key]} -> {current[key]}")

    if current["length_histogram"] != approved["length_histogram"]:
        moved = _histogram_diff(current["length_histogram"], approved["length_histogram"])
        result.differences.append(f"stitch length distribution moved: {moved}")

    for key in ("blocking_findings", "warning_findings"):
        if current[key] != approved[key]:
            result.differences.append(f"{key} {approved[key]} -> {current[key]}")

    return result


def _histogram_diff(current: dict[str, int], approved: dict[str, int]) -> str:
    """The three buckets that moved most, so a diff says what changed."""
    keys = set(current) | set(approved)
    deltas = sorted(
        ((key, current.get(key, 0) - approved.get(key, 0)) for key in keys),
        key=lambda item: -abs(item[1]),
    )
    return ", ".join(f"{key} mm {delta:+d}" for key, delta in deltas[:3] if delta)


def _design_name(path: Path) -> str:
    return path.name.removesuffix(".ir.json")


def run(
    designs_dir: str | Path = DESIGNS,
    approved_dir: str | Path = APPROVED,
    approve: bool = False,
) -> list[Comparison]:
    """Regenerate every golden design and compare it against approval."""
    designs_dir, approved_dir = Path(designs_dir), Path(approved_dir)
    approved_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for path in sorted(designs_dir.glob("*.ir.json")):
        name = _design_name(path)
        doc = load_ir(path)
        plan = generate(doc, load_profile(doc.design.fabric_profile))
        current = metrics(doc, plan)
        approved_path = approved_dir / f"{name}.json"

        if approve:
            approved_path.write_text(
                json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            results.append(Comparison(design=name, profile_ref=current["profile_ref"]))
            continue

        if not approved_path.exists():
            results.append(
                Comparison(
                    design=name,
                    profile_ref=current["profile_ref"],
                    differences=["never approved"],
                    approved=False,
                )
            )
            continue

        approved = json.loads(approved_path.read_text(encoding="utf-8"))
        results.append(compare(name, current, approved))
    return results
