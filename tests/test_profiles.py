"""Fabric profiles: no profile, no file -- and no silent version drift."""

from __future__ import annotations

import pytest

from engine.profiles.loader import (
    ProfileNotFound,
    available_profiles,
    load_profile,
    parse_ref,
)

SHIPPED = ["cap@1", "pique@1", "twill@1"]


def test_v1_ships_three_profiles_done_properly():
    assert available_profiles() == SHIPPED


@pytest.mark.parametrize("ref", SHIPPED)
def test_every_shipped_profile_loads_and_self_describes(ref):
    profile = load_profile(ref)
    assert profile.ref == ref
    assert profile.description


@pytest.mark.parametrize("ref", SHIPPED)
def test_no_profile_claims_to_be_calibrated_yet(ref):
    """Calibration means sew-outs on our machines, which have not happened.

    When a profile is genuinely calibrated this test is the thing that has to
    be changed on purpose, by someone who did the sew-outs.
    """
    assert load_profile(ref).calibrated is False


def test_unpinned_reference_loads_current_version():
    assert load_profile("twill").ref == "twill@1"


def test_pinned_reference_refuses_a_different_version():
    with pytest.raises(ProfileNotFound, match="pins @9"):
        load_profile("twill@9")


def test_unknown_profile_is_refused():
    with pytest.raises(ProfileNotFound, match="no profile file"):
        load_profile("silk_organza")


def test_malformed_reference_is_refused():
    with pytest.raises(ProfileNotFound, match="malformed"):
        load_profile("twill@@1")


def test_parse_ref_splits_name_and_version():
    assert parse_ref("pique@3") == ("pique", 3)
    assert parse_ref("pique") == ("pique", None)


def test_satin_underlay_recipe_steps_up_with_column_width():
    underlay = load_profile("twill@1").underlay
    assert underlay.for_satin(1.0) == ["center_run"]
    assert underlay.for_satin(3.0) == ["edge_run"]
    assert underlay.for_satin(6.0) == ["edge_run", "zigzag"]


def test_cap_profile_sequences_center_out():
    """Not a preference: a cap is sewn on a driver, from the middle outward."""
    assert load_profile("cap@1").routing.sequencing == "center_out"


@pytest.mark.parametrize("ref", SHIPPED)
def test_stitch_floor_is_below_target_lengths(ref):
    stitch = load_profile(ref).stitch
    assert stitch.min_length_mm < stitch.run_length_mm < stitch.max_length_mm
    assert stitch.min_length_mm < stitch.fill_length_mm < stitch.max_length_mm


def test_knit_profiles_compensate_more_than_the_stable_baseline():
    """Pull comp exists to answer fabric movement; pique moves, twill does not."""
    twill = load_profile("twill@1").compensation.pull_comp_mm_per_side
    pique = load_profile("pique@1").compensation.pull_comp_mm_per_side
    assert pique > twill
