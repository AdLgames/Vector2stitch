"""The checks, and the seeded bad files they have to catch.

The rules matter less than the misses. A check suite that passes everything is
worse than none, because it is trusted. Every rule here has at least one file
built specifically to break it.
"""

from __future__ import annotations

import pytest
from conftest import BLACK, RED, design, run_object

from engine.checks import Severity, run_checks
from engine.checks.rules import _segments
from engine.ir.schema import EmbroideryObject, FillShape, ObjectKind, ObjectParams, RailsShape
from engine.machines import load_machine, resolve_setup
from engine.plan import Cmd, PlanStitch, PlanThread, StitchPlan
from engine.profiles.loader import load_profile
from engine.stitchgen import generate

TWILL = load_profile("twill@1")


def _satin(object_id: str, width_mm: float = 3.0, length_mm: float = 40.0, **params):
    return EmbroideryObject(
        id=object_id,
        kind=ObjectKind.SATIN,
        shape=RailsShape(
            rails=([(0.0, 0.0), (length_mm, 0.0)], [(0.0, width_mm), (length_mm, width_mm)])
        ),
        thread=BLACK,
        params=ObjectParams(**params),
    )


def _fill(object_id: str, side: float = 25.0, **params):
    return EmbroideryObject(
        id=object_id,
        kind=ObjectKind.FILL,
        shape=FillShape(outer=[(0.0, 0.0), (side, 0.0), (side, side), (0.0, side)]),
        thread=BLACK,
        params=ObjectParams(**params),
    )


def _plan(points: list[tuple[float, float, Cmd]], object_id: str = "obj_001") -> StitchPlan:
    """A hand-built plan, for corrupting in ways the generator cannot."""
    return StitchPlan(
        profile_ref="twill@1",
        threads=[PlanThread(chart="c", code="1800", rgb="#1a1a1a")],
        stitches=[
            PlanStitch(x_mm=x, y_mm=y, cmd=cmd, object_id=object_id) for x, y, cmd in points
        ],
    )


def _rules_fired(report, severity: Severity) -> set[str]:
    return {f.rule for f in report.findings if f.severity is severity}


# --- what good output looks like -------------------------------------------


@pytest.mark.parametrize("profile_ref", ["twill@1", "pique@1", "cap@1"])
def test_engine_output_passes_its_own_checks(profile_ref):
    """If our own generators cannot pass, the thresholds are wrong or the
    generators are -- and either way it has to be settled before a customer
    file is judged by them."""
    profile = load_profile(profile_ref)
    doc = design([_satin("obj_001"), _fill("obj_002")], profile_ref)
    report = run_checks(doc, generate(doc, profile), profile)
    assert report.ok, [f.message for f in report.blockers]


def test_an_uncalibrated_profile_warns_on_every_file():
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    report = run_checks(doc, generate(doc, TWILL), TWILL)
    assert "profile_calibrated" in _rules_fired(report, Severity.WARN)


def test_passes_are_recorded_not_left_as_silence():
    """Silence cannot distinguish "fine" from "never looked"."""
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    report = run_checks(doc, generate(doc, TWILL), TWILL)
    assert _rules_fired(report, Severity.PASS)


def test_the_report_records_what_made_the_file():
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    plan = generate(doc, TWILL, ["compensation.pull_comp_mm_per_side"])
    report = run_checks(doc, plan, TWILL)
    assert report.profile_ref == "twill@1"
    assert report.profile_overrides == ["compensation.pull_comp_mm_per_side"]
    assert report.engine_version == plan.engine_version


# --- seeded bad files -------------------------------------------------------


def _short_stitch_plan(gap_mm: float) -> StitchPlan:
    return _plan([(0.0, 0.0, Cmd.STITCH), (gap_mm, 0.0, Cmd.STITCH), (20.0, 0.0, Cmd.STITCH)])


def _long_stitch_plan(length_mm: float) -> StitchPlan:
    return _plan([(0.0, 0.0, Cmd.STITCH), (length_mm, 0.0, Cmd.STITCH)])


@pytest.mark.parametrize("gap", [0.05, 0.1, 0.2, 0.3, 0.45])
def test_stitches_below_the_floor_are_blocked(gap):
    """Penetrations piling into one hole: thread break, then needle break."""
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    report = run_checks(doc, _short_stitch_plan(gap), TWILL)
    assert "stitch_length_min" in _rules_fired(report, Severity.BLOCK)


@pytest.mark.parametrize("length", [12.5, 15.0, 20.0, 40.0, 100.0])
def test_stitches_over_the_machine_limit_are_blocked(length):
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    report = run_checks(doc, _long_stitch_plan(length), TWILL)
    assert "stitch_length_max" in _rules_fired(report, Severity.BLOCK)


@pytest.mark.parametrize("count", [15, 20, 40])
def test_a_density_hotspot_is_blocked(count):
    """Perforating the fabric rather than covering it."""
    points = []
    for index in range(count):
        points.append((0.5 + (index % 2) * 0.1, 0.5, Cmd.STITCH))
        points.append((0.5, 0.5 + (index % 3) * 0.1, Cmd.STITCH))
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    report = run_checks(doc, _plan(points), TWILL)
    assert "density_hotspot" in _rules_fired(report, Severity.BLOCK)


@pytest.mark.parametrize("width", [8.0, 10.0, 15.0])
def test_an_unsplit_wide_satin_is_blocked(width):
    """A stitch that wide has nothing holding its middle down: it snags and
    pulls into a loop."""
    doc = design([_satin("obj_001", width_mm=width)])
    plan = _plan(
        [(0.0, 0.0, Cmd.STITCH), (0.0, width, Cmd.STITCH), (0.4, 0.0, Cmd.STITCH)]
    )
    report = run_checks(doc, plan, TWILL)
    assert "satin_width_max" in _rules_fired(report, Severity.BLOCK)


@pytest.mark.parametrize("cmd", [Cmd.TRIM, Cmd.COLOR_CHANGE, Cmd.END])
def test_an_untied_trim_stop_or_end_is_blocked(cmd):
    """Thread cut without a tie pulls straight back out, and the first thing a
    wearer does to a loose end is catch it."""
    points = [(float(index), 0.0, Cmd.STITCH) for index in range(0, 12, 2)]
    points.append((10.0, 0.0, cmd))
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    report = run_checks(doc, _plan(points), TWILL)
    assert "tie_off_before_trim" in _rules_fired(report, Severity.BLOCK)


def test_an_empty_design_is_blocked():
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    report = run_checks(doc, StitchPlan(profile_ref="twill@1"), TWILL)
    assert "not_empty" in _rules_fired(report, Severity.BLOCK)


@pytest.mark.parametrize("placement_profile", ["cap@1"])
def test_a_design_too_big_for_the_machine_is_blocked(placement_profile):
    from engine.ir.schema import Design, IRDocument, Placement

    doc = design([_fill("obj_001", side=200.0)], placement_profile)
    doc = IRDocument(
        design=Design(
            width_mm=200,
            height_mm=200,
            placement=Placement.CAP_FRONT,
            fabric_profile=placement_profile,
            thread_brand="madeira_polyneon_40",
        ),
        objects=doc.objects,
    )
    profile = load_profile(placement_profile)
    plan = generate(doc, profile)
    setup = resolve_setup(profile, doc, plan, load_machine("multineedle_6head@1"))
    report = run_checks(doc, plan, profile, setup)
    assert "machine_fit" in _rules_fired(report, Severity.BLOCK)


def test_a_cap_on_a_machine_with_no_cap_driver_is_blocked():
    from engine.ir.schema import Design, IRDocument, Placement

    doc = design([_fill("obj_001", side=25.0)], "cap@1")
    doc = IRDocument(
        design=Design(
            width_mm=40,
            height_mm=40,
            placement=Placement.CAP_FRONT,
            fabric_profile="cap@1",
            thread_brand="madeira_polyneon_40",
        ),
        objects=doc.objects,
    )
    profile = load_profile("cap@1")
    plan = generate(doc, profile)
    setup = resolve_setup(profile, doc, plan, load_machine("single_head@1"))
    report = run_checks(doc, plan, profile, setup)
    assert "machine_fit" in _rules_fired(report, Severity.BLOCK)


@pytest.mark.parametrize("colors", [14, 16, 20])
def test_too_many_colour_changes_warn(colors):
    """Each one stops the machine and costs the customer a rethread."""
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    plan = _plan([(0.0, 0.0, Cmd.STITCH), (2.0, 0.0, Cmd.STITCH)])
    plan = plan.model_copy(
        update={
            "threads": [
                PlanThread(chart="c", code=str(index), rgb="#1a1a1a") for index in range(colors)
            ]
        }
    )
    report = run_checks(doc, plan, TWILL)
    assert "color_change_budget" in _rules_fired(report, Severity.WARN)


def test_trim_churn_warns_on_a_design_big_enough_to_judge():
    points: list[tuple[float, float, Cmd]] = []
    for index in range(1200):
        points.append((float(index % 50), float(index // 50), Cmd.STITCH))
        if index % 20 == 0:
            points.append((float(index % 50), float(index // 50), Cmd.TRIM))
    report = run_checks(
        design([run_object("obj_001", [(0, 0), (20, 0)])]), _plan(points), TWILL
    )
    assert "trim_budget" in _rules_fired(report, Severity.WARN)


def test_budgets_are_not_judged_on_a_small_design():
    """On a 200-stitch test pattern, "40 trims per thousand" describes the
    pattern's size, not its quality."""
    points = [(float(index), 0.0, Cmd.STITCH) for index in range(0, 60, 2)]
    points.append((58.0, 0.0, Cmd.TRIM))
    report = run_checks(
        design([run_object("obj_001", [(0, 0), (20, 0)])]), _plan(points), TWILL
    )
    assert "trim_budget" not in _rules_fired(report, Severity.WARN)


def test_a_satin_narrower_than_a_run_warns_rather_than_blocks():
    """It will sew; it just should have been a run."""
    doc = design([_satin("obj_001", width_mm=0.6)])
    report = run_checks(doc, generate(doc, TWILL), TWILL)
    assert "satin_width_min" in _rules_fired(report, Severity.WARN)
    assert report.ok


# --- the fill turn exception ------------------------------------------------


def test_a_fills_row_turns_are_not_mistaken_for_stubs():
    """A fill turns at the end of every row, about one row spacing long. A
    naive floor would condemn every fill ever made."""
    doc = design([_fill("obj_001")])
    plan = generate(doc, TWILL)
    shortest = min(length for _a, _b, length in _segments(plan) if length > 0)
    assert shortest < TWILL.stitch.min_length_mm
    assert run_checks(doc, plan, TWILL).ok


def test_the_exception_does_not_extend_to_runs_or_satins():
    """It is the fill's geometry that earns the exception, not a blanket
    lowering of the floor."""
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    report = run_checks(doc, _short_stitch_plan(0.2), TWILL)
    assert "stitch_length_min" in _rules_fired(report, Severity.BLOCK)


# --- the report itself ------------------------------------------------------


def test_a_blocking_finding_makes_the_report_not_ok():
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    assert not run_checks(doc, _short_stitch_plan(0.1), TWILL).ok


def test_warnings_alone_do_not_stop_a_file():
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    report = run_checks(doc, generate(doc, TWILL), TWILL)
    assert report.warnings
    assert report.ok


def test_findings_point_at_an_object_not_a_stitch_index():
    """A stitch index is not something a reviewer can act on."""
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    report = run_checks(doc, _short_stitch_plan(0.1), TWILL)
    finding = report.blockers[0]
    assert finding.object_id == "obj_001"
    assert finding.location_mm is not None


def test_every_rule_runs_even_after_one_blocks():
    """A report that gave up at the first blocker would send a reviewer round
    the loop once per problem."""
    points = [(0.0, 0.0, Cmd.STITCH), (0.05, 0.0, Cmd.STITCH), (40.0, 0.0, Cmd.STITCH)]
    report = run_checks(design([run_object("obj_001", [(0, 0), (20, 0)])]), _plan(points), TWILL)
    assert {"stitch_length_min", "stitch_length_max"} <= _rules_fired(report, Severity.BLOCK)


def test_the_report_formats_for_a_terminal():
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])])
    text = run_checks(doc, _short_stitch_plan(0.1), TWILL).format()
    assert "BLOCK" in text
    assert "blocking" in text.splitlines()[-1]


def test_two_colours_do_not_trip_the_colour_budget():
    doc = design(
        [
            run_object("obj_001", [(0, 0), (20, 0)]),
            run_object("obj_002", [(0, 10), (20, 10)], thread=RED, z_order=1),
        ]
    )
    report = run_checks(doc, generate(doc, TWILL), TWILL)
    assert "color_change_budget" not in _rules_fired(report, Severity.WARN)
