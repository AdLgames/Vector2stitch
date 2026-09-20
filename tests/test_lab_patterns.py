"""Calibration patterns: the instrument the profiles get measured with."""

from __future__ import annotations

import pytest

from engine.lab import AVAILABLE, PATTERNS, PENDING, PatternNotAvailable, build_pattern
from engine.lab.targets import Axis
from engine.machines import load_machine, resolve_setup
from engine.profiles.loader import load_profile
from engine.stitchgen import generate


@pytest.mark.parametrize("name", AVAILABLE)
def test_every_available_pattern_generates_a_sewable_plan(name):
    profile = load_profile("twill@1")
    doc, targets = build_pattern(name, profile.ref)
    plan = generate(doc, profile)
    assert plan.stitch_count() > 0
    assert targets


@pytest.mark.parametrize("name", AVAILABLE)
def test_declared_size_matches_the_geometry(name):
    """A pattern that overstated its size would defeat the sew-field check it
    is about to go through.

    Declared size is the drawn size -- what was asked for. The sewn extents
    can exceed it by the pull compensation, because compensation deliberately
    stitches wider than drawn so the fabric draws back to size. They can never
    fall short of it.
    """
    profile = load_profile("twill@1")
    doc, _ = build_pattern(name, profile.ref)
    plan = generate(doc, profile)
    min_x, min_y, max_x, max_y = plan.extents_mm()
    slack = 2 * profile.compensation.pull_comp_mm_per_side + 0.01

    assert doc.design.width_mm <= max_x - min_x + 0.01
    assert doc.design.height_mm <= max_y - min_y + 0.01
    assert doc.design.width_mm >= max_x - min_x - slack
    assert doc.design.height_mm >= max_y - min_y - slack


@pytest.mark.parametrize("name", AVAILABLE)
def test_every_target_has_a_designed_dimension_and_an_axis(name):
    """A target without a number to compare against is a note, not a measurement."""
    _, targets = build_pattern(name, "twill@1")
    for target in targets:
        assert target.designed_mm > 0
        assert target.axis in set(Axis)
        assert target.description


@pytest.mark.parametrize("name", AVAILABLE)
def test_target_ids_are_unique_within_a_pattern(name):
    _, targets = build_pattern(name, "twill@1")
    ids = [target.id for target in targets]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("name", AVAILABLE)
def test_patterns_are_deterministic(name):
    first, _ = build_pattern(name, "twill@1")
    second, _ = build_pattern(name, "twill@1")
    assert first.model_dump_json() == second.model_dump_json()


@pytest.mark.parametrize("name", AVAILABLE)
def test_every_pattern_fits_a_commercial_sew_field(name):
    """A calibration pattern nobody can hoop measures nothing."""
    profile = load_profile("twill@1")
    doc, _ = build_pattern(name, profile.ref)
    plan = generate(doc, profile)
    setup = resolve_setup(profile, doc, plan, load_machine("multineedle_6head@1"))
    assert setup.ok, setup.blockers


def test_the_column_ladder_covers_every_underlay_band():
    """Column width decides the underlay recipe. A ladder that stayed inside
    one band would never test the switch."""
    profile = load_profile("twill@1")
    doc, _ = build_pattern("column_ladder", profile.ref)
    recipes = set()
    for obj in doc.objects:
        left, right = obj.shape.rails
        width = abs(right[0][1] - left[0][1])
        recipes.add(tuple(profile.underlay.for_satin(width)))
    assert len(recipes) == 3


def test_the_column_ladder_goes_past_the_split_point_on_purpose():
    """The widest column is there to show what a split looks like."""
    profile = load_profile("twill@1")
    doc, targets = build_pattern("column_ladder", profile.ref)
    widths = [t.designed_mm for t in targets if t.id.endswith("_width")]
    assert max(widths) > profile.classification.satin_max_width_mm
    assert any("expect a split" in t.description for t in targets)


def test_the_column_ladder_measures_along_as_well_as_across():
    """Across reads pull; along reads push at the ends. One number would hide
    which of the two is wrong."""
    _, targets = build_pattern("column_ladder", "twill@1")
    axes = {t.axis for t in targets}
    assert axes == {Axis.X, Axis.Y}


def test_dimension_grid_measures_both_axes_separately():
    """Pull draws in along the stitch direction and pushes out at the ends, so
    one number for a square would hide which one is wrong."""
    _, targets = build_pattern("dimension_grid", "twill@1")
    axes = {target.axis for target in targets}
    assert Axis.X in axes and Axis.Y in axes


def test_registration_target_sews_two_colours():
    doc, _ = build_pattern("registration_target", "twill@1")
    plan = generate(doc, load_profile("twill@1"))
    assert len(plan.threads) == 2


def test_stitch_length_ladder_actually_varies_stitch_length():
    doc, _ = build_pattern("stitch_length_ladder", "twill@1")
    lengths = {obj.params.stitch_length_mm for obj in doc.objects}
    assert len(lengths) == len(doc.objects)
    assert None not in lengths


def test_patterns_that_need_generators_we_lack_are_declared_not_hidden():
    """Only text is left now, waiting on licensed embroidery fonts."""
    assert PENDING == ["text_ladder"]
    for name in PENDING:
        assert PATTERNS[name].requires == "M6"
        assert PATTERNS[name].purpose


@pytest.mark.parametrize("name", PENDING)
def test_an_unavailable_pattern_names_its_milestone(name):
    with pytest.raises(PatternNotAvailable, match=r"M\d"):
        build_pattern(name, "twill@1")


def test_an_unknown_pattern_is_refused():
    with pytest.raises(KeyError):
        build_pattern("not_a_pattern", "twill@1")


@pytest.mark.parametrize("profile_ref", ["twill@1", "pique@1", "cap@1"])
def test_patterns_build_for_every_shipped_profile(profile_ref):
    """Each fabric gets its own calibration run; the profile is what is
    being measured."""
    doc, _ = build_pattern("dimension_grid", profile_ref)
    assert doc.design.fabric_profile == profile_ref
    assert generate(doc, load_profile(profile_ref)).stitch_count() > 0


@pytest.mark.parametrize("profile_ref", ["twill@1", "pique@1", "cap@1"])
def test_no_calibration_pattern_sews_an_illegal_stitch(profile_ref):
    """A calibration pattern that breaks thread teaches nothing about the
    fabric -- it teaches that the pattern was wrong."""
    from engine.plan import Cmd
    from engine.stitchgen.geometry import distance

    profile = load_profile(profile_ref)
    for name in AVAILABLE:
        doc, _ = build_pattern(name, profile.ref)
        plan = generate(doc, profile)
        lengths = [
            distance((a.x_mm, a.y_mm), (b.x_mm, b.y_mm))
            for a, b in zip(plan.stitches, plan.stitches[1:], strict=False)
            if a.cmd is Cmd.STITCH and b.cmd is Cmd.STITCH
        ]
        shortest = min(length for length in lengths if length > 0)
        assert max(lengths) <= profile.stitch.max_length_mm, name
        # The stitch floor applies within a row or column. A fill's turn from
        # one row to the next is about one row spacing long by construction --
        # shorter where the boundary runs diagonally to the rows -- and those
        # turns are structural, so they are not filtered. M2's checks will
        # need to know the difference.
        floor = min(profile.stitch.min_length_mm, profile.density.fill_row_spacing_mm * 0.5)
        assert shortest >= floor, name
