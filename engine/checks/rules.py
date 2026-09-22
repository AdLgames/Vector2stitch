"""The rules.

Each one answers a question a decorator would ask about a file before putting
it on a machine, and each one knows why it exists. A rule that cannot say what
failure it prevents does not belong here.

Every threshold comes from the fabric profile. A rule that hard-coded one
would be unfixable by the people who find out it is wrong.
"""

from __future__ import annotations

import math
from collections import Counter

from engine.checks.report import Finding, Severity
from engine.ir.schema import IRDocument, ObjectKind
from engine.machines.setup import MachineSetup
from engine.plan import Cmd, PlanStitch, StitchPlan
from engine.profiles.loader import FabricProfile
from engine.stitchgen.params import resolve


def _segments(plan: StitchPlan) -> list[tuple[PlanStitch, PlanStitch, float]]:
    """Consecutive pairs that are actually one stitch, with their lengths.

    Pairing penetrations without checking what sits between them would treat
    the two ends of a jump as a stitch -- which is how a travel gets mistaken
    for thread on the fabric.
    """
    out = []
    for a, b in zip(plan.stitches, plan.stitches[1:], strict=False):
        if a.cmd is Cmd.STITCH and b.cmd is Cmd.STITCH:
            out.append((a, b, math.hypot(b.x_mm - a.x_mm, b.y_mm - a.y_mm)))
    return out


def _object_kinds(doc: IRDocument) -> dict[str, ObjectKind]:
    return {obj.id: obj.kind for obj in doc.objects}


def check_not_empty(doc: IRDocument, plan: StitchPlan, profile: FabricProfile) -> list[Finding]:
    """A file with no stitches is not a file."""
    if plan.stitch_count() == 0:
        return [
            Finding(
                rule="not_empty",
                severity=Severity.BLOCK,
                message="the design produced no stitches",
            )
        ]
    return [
        Finding(
            rule="not_empty",
            severity=Severity.PASS,
            message=f"{plan.stitch_count()} penetrations",
        )
    ]


def check_stitch_length(
    doc: IRDocument, plan: StitchPlan, profile: FabricProfile
) -> list[Finding]:
    """Stitches too short pile thread in one hole; too long, they snag.

    The floor is not the same for every object. A fill turns at the end of
    every row, and that turn is about one row spacing long -- structural, and
    shorter than the floor by design. Applying the floor to it would condemn
    every fill ever made.
    """
    kinds = _object_kinds(doc)
    by_object = {obj.id: resolve(obj, profile) for obj in doc.objects}

    findings: list[Finding] = []
    shortest = (None, math.inf)
    longest = (None, 0.0)

    for a, _b, length in _segments(plan):
        params = by_object.get(a.object_id)
        if params is None:
            continue
        floor = params.min_stitch_length_mm
        if kinds.get(a.object_id) is ObjectKind.FILL:
            floor = min(floor, params.density_mm * profile.fill.min_turn_fraction)

        if length < floor and length < shortest[1]:
            shortest = (a, length)
        if length > params.max_stitch_length_mm and length > longest[1]:
            longest = (a, length)

    if shortest[0] is not None:
        stitch, length = shortest
        findings.append(
            Finding(
                rule="stitch_length_min",
                severity=Severity.BLOCK,
                message=f"stitch of {length:.2f} mm is below the floor for this object",
                object_id=stitch.object_id,
                location_mm=(stitch.x_mm, stitch.y_mm),
                value=length,
                limit=by_object[stitch.object_id].min_stitch_length_mm,
            )
        )
    if longest[0] is not None:
        stitch, length = longest
        findings.append(
            Finding(
                rule="stitch_length_max",
                severity=Severity.BLOCK,
                message=f"stitch of {length:.2f} mm is longer than the machine will sew",
                object_id=stitch.object_id,
                location_mm=(stitch.x_mm, stitch.y_mm),
                value=length,
                limit=by_object[stitch.object_id].max_stitch_length_mm,
            )
        )
    if not findings:
        findings.append(
            Finding(
                rule="stitch_length",
                severity=Severity.PASS,
                message="every stitch is within its object's bounds",
            )
        )
    return findings


def check_density(doc: IRDocument, plan: StitchPlan, profile: FabricProfile) -> list[Finding]:
    """Too many penetrations in one place perforates the fabric.

    Counted per square millimetre rather than per object, because the failure
    is a hotspot where layers meet -- exactly where no single object's density
    looks wrong.
    """
    bin_mm = profile.checks.penetration_bin_mm
    bins: Counter[tuple[int, int]] = Counter()
    owner: dict[tuple[int, int], str | None] = {}
    for stitch in plan.stitches:
        if stitch.cmd is not Cmd.STITCH:
            continue
        key = (int(stitch.x_mm // bin_mm), int(stitch.y_mm // bin_mm))
        bins[key] += 1
        owner.setdefault(key, stitch.object_id)

    if not bins:
        return []
    key, peak = bins.most_common(1)[0]
    limit = profile.checks.max_penetrations_per_mm2 * bin_mm * bin_mm
    if peak > limit:
        return [
            Finding(
                rule="density_hotspot",
                severity=Severity.BLOCK,
                message=f"{peak:.0f} penetrations in one {bin_mm} mm square",
                object_id=owner[key],
                location_mm=(key[0] * bin_mm, key[1] * bin_mm),
                value=float(peak),
                limit=limit,
            )
        ]
    return [
        Finding(
            rule="density_hotspot",
            severity=Severity.PASS,
            message=f"peak {peak:.0f} penetrations per {bin_mm} mm square",
            value=float(peak),
            limit=limit,
        )
    ]


def check_satin_width(
    doc: IRDocument, plan: StitchPlan, profile: FabricProfile
) -> list[Finding]:
    """A satin stitch wider than the limit loops and snags; one narrower than
    a run should have been a run."""
    from engine.stitchgen import mean_column_width

    kinds = _object_kinds(doc)
    objects = {obj.id: obj for obj in doc.objects}
    by_object = {obj.id: resolve(obj, profile) for obj in doc.objects}
    findings: list[Finding] = []

    widths: dict[str, list[float]] = {}
    for a, _b, length in _segments(plan):
        if kinds.get(a.object_id) is ObjectKind.SATIN:
            widths.setdefault(a.object_id, []).append(length)

    for object_id, lengths in sorted(widths.items()):
        params = by_object[object_id]
        limit = params.max_width_mm + 2 * params.split_overlap_mm
        widest = max(lengths)
        if widest > limit:
            findings.append(
                Finding(
                    rule="satin_width_max",
                    severity=Severity.BLOCK,
                    message=f"satin stitch of {widest:.2f} mm should have been split",
                    object_id=object_id,
                    value=widest,
                    limit=limit,
                )
            )
        # Measured on the geometry, not on the stitches: a stitch is the
        # column width plus twice the compensation, so judging drawn width by
        # stitched length would call a 0.6 mm column a 1.0 mm one.
        drawn = mean_column_width(objects[object_id])
        if drawn < profile.classification.run_max_width_mm:
            findings.append(
                Finding(
                    rule="satin_width_min",
                    severity=Severity.WARN,
                    message=(
                        f"column is drawn {drawn:.2f} mm wide; below "
                        f"{profile.classification.run_max_width_mm} mm a run sews cleaner"
                    ),
                    object_id=object_id,
                    value=drawn,
                    limit=profile.classification.run_max_width_mm,
                )
            )

    if widths and not findings:
        findings.append(
            Finding(
                rule="satin_width",
                severity=Severity.PASS,
                message=f"{len(widths)} satin column(s) within bounds",
            )
        )
    return findings


def check_ties(doc: IRDocument, plan: StitchPlan, profile: FabricProfile) -> list[Finding]:
    """Thread that is not tied off before a trim pulls straight back out.

    The first thing a wearer does to an untied end is catch it. Checked
    structurally: the penetrations immediately before a trim have to be the
    short alternating pair a tie is made of.
    """
    findings: list[Finding] = []
    tie_length = profile.stitch.tie_length_mm
    tie_stitches = profile.stitch.tie_stitches
    if tie_stitches == 0:
        return findings

    untied = 0
    first: PlanStitch | None = None
    for index, stitch in enumerate(plan.stitches):
        if stitch.cmd not in (Cmd.TRIM, Cmd.COLOR_CHANGE, Cmd.END):
            continue
        preceding = [s for s in plan.stitches[:index] if s.cmd is Cmd.STITCH][-tie_stitches:]
        if len(preceding) < tie_stitches:
            continue
        spans = [
            math.hypot(b.x_mm - a.x_mm, b.y_mm - a.y_mm)
            for a, b in zip(preceding, preceding[1:], strict=False)
        ]
        if not spans or max(spans) > tie_length * 1.5:
            untied += 1
            first = first or stitch

    if untied:
        findings.append(
            Finding(
                rule="tie_off_before_trim",
                severity=Severity.BLOCK,
                message=f"{untied} trim(s) or stop(s) with no tie-off before them",
                object_id=first.object_id if first else None,
                location_mm=(first.x_mm, first.y_mm) if first else None,
                value=float(untied),
                limit=0.0,
            )
        )
    else:
        findings.append(
            Finding(
                rule="tie_off_before_trim",
                severity=Severity.PASS,
                message="every trim, stop and end is tied off",
            )
        )
    return findings


def check_budgets(doc: IRDocument, plan: StitchPlan, profile: FabricProfile) -> list[Finding]:
    """Trims, jumps and colour changes are the customer's machine time.

    Judged only on designs big enough for a ratio to mean anything: on a
    200-stitch test pattern, "40 trims per thousand" describes the pattern's
    size, not its quality.
    """
    count = plan.stitch_count()
    findings: list[Finding] = []
    colors = max(len(plan.threads) - 1, 0)

    if colors > profile.checks.color_change_budget:
        findings.append(
            Finding(
                rule="color_change_budget",
                severity=Severity.WARN,
                message=f"{colors} colour changes; each one stops the machine",
                value=float(colors),
                limit=float(profile.checks.color_change_budget),
            )
        )

    if count < profile.checks.budget_min_stitches:
        findings.append(
            Finding(
                rule="budgets",
                severity=Severity.PASS,
                message=f"design is {count} stitches; ratios not judged below "
                f"{profile.checks.budget_min_stitches}",
            )
        )
        return findings

    for cmd, budget, rule in (
        (Cmd.TRIM, profile.checks.trim_budget_per_1000, "trim_budget"),
        (Cmd.JUMP, profile.checks.jump_budget_per_1000, "jump_budget"),
    ):
        used = sum(1 for s in plan.stitches if s.cmd is cmd)
        rate = used * 1000 / count
        if rate > budget:
            findings.append(
                Finding(
                    rule=rule,
                    severity=Severity.WARN,
                    message=f"{used} {cmd.value}s, {rate:.0f} per 1000 stitches",
                    value=rate,
                    limit=budget,
                )
            )
        else:
            findings.append(
                Finding(
                    rule=rule,
                    severity=Severity.PASS,
                    message=f"{used} {cmd.value}s, {rate:.0f} per 1000 stitches",
                    value=rate,
                    limit=budget,
                )
            )
    return findings


def check_calibration(
    doc: IRDocument, plan: StitchPlan, profile: FabricProfile
) -> list[Finding]:
    """An uncalibrated profile is a warning on every file it makes.

    It stops being true the day someone sews the calibration set and sets the
    flag. Until then, every file says so out loud rather than implying our
    defaults were tested.
    """
    if profile.calibrated:
        return [
            Finding(
                rule="profile_calibrated",
                severity=Severity.PASS,
                message=f"{profile.ref} is calibrated",
            )
        ]
    return [
        Finding(
            rule="profile_calibrated",
            severity=Severity.WARN,
            message=(
                f"{profile.ref} is not calibrated: its numbers are industry defaults, "
                "not values proven on a machine. Test sew on scrap."
            ),
        )
    ]


def check_machine_fit(setup: MachineSetup | None) -> list[Finding]:
    """Whatever the machine profile already refused, said as a finding."""
    if setup is None:
        return []
    findings = [
        Finding(rule="machine_fit", severity=Severity.BLOCK, message=blocker)
        for blocker in setup.blockers
    ]
    if not findings:
        findings.append(
            Finding(
                rule="machine_fit",
                severity=Severity.PASS,
                message=f"fits {setup.machine_ref or 'the declared field'}",
            )
        )
    return findings
