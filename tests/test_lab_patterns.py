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
    is about to go through."""
    doc, _ = build_pattern(name, "twill@1")
    plan = generate(doc, load_profile("twill@1"))
    min_x, min_y, max_x, max_y = plan.extents_mm()
    assert doc.design.width_mm == pytest.approx(max_x - min_x, abs=0.01)
    assert doc.design.height_mm == pytest.approx(max_y - min_y, abs=0.01)


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
    """Half the set is waiting on satin, fill and text. Omitting them would
    hide exactly the gap the lab exists to close."""
    assert PENDING == ["column_ladder", "density_wedge", "text_ladder"]
    for name in PENDING:
        assert PATTERNS[name].requires in {"M1", "M6"}
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
