"""Fabric profiles: no profile, no file -- and no silent version drift."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.profiles.loader import (
    ProfileNotFound,
    available_profiles,
    current_profiles,
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


@pytest.mark.parametrize("ref", SHIPPED)
def test_every_profile_specifies_the_machine_setup(ref):
    """A profile that specifies stitches but leaves thread, needle, speed and
    tension to memory is half a recipe -- and the half the operator needs."""
    machine = load_profile(ref).machine
    assert machine.thread_weight_wt == 40
    assert machine.needle_size
    assert machine.max_spm > 0
    assert machine.bobbin_tension_gf_min <= machine.bobbin_tension_gf_max


def test_cap_runs_slower_and_tighter_than_flat_goods():
    """A structured cap on a driver throttles; its dense seams loop at flat-goods
    bobbin tension."""
    cap = load_profile("cap@1").machine
    twill = load_profile("twill@1").machine
    assert cap.max_spm < twill.max_spm
    assert cap.bobbin_tension_gf_min > twill.bobbin_tension_gf_min


def test_knit_profiles_stay_open_enough_to_avoid_puckering():
    """Commercial practice on pique is 0.45-0.50 mm between fill rows; twill,
    being stable, takes a denser fill."""
    pique = load_profile("pique@1").density.fill_row_spacing_mm
    twill = load_profile("twill@1").density.fill_row_spacing_mm
    assert 0.45 <= pique <= 0.50
    assert twill < pique


def test_textured_fabric_calls_for_a_topping():
    """Without a topping, stitches sink into the texture and edges disappear."""
    assert load_profile("pique@1").materials.topping is True
    assert load_profile("twill@1").materials.topping is False


def _write_profile(directory, name, version, **overrides):
    """Copy a shipped profile to a temp directory under a new version."""
    import yaml

    source = Path(__file__).resolve().parents[1] / "engine/profiles/data/twill@1.yaml"
    raw = yaml.safe_load(source.read_text())
    raw["name"] = name
    raw["version"] = version
    raw.update(overrides)
    (directory / f"{name}@{version}.yaml").write_text(yaml.safe_dump(raw))


def test_a_superseded_version_still_loads(tmp_path):
    """Old designs must always reopen: a design delivered against @1 has to
    reproduce even after @2 ships."""
    _write_profile(tmp_path, "linen", 1)
    _write_profile(tmp_path, "linen", 2)
    assert load_profile("linen@1", str(tmp_path)).version == 1
    assert load_profile("linen@2", str(tmp_path)).version == 2


def test_an_unpinned_name_loads_the_newest_version(tmp_path):
    _write_profile(tmp_path, "hemp", 1)
    _write_profile(tmp_path, "hemp", 3)
    assert load_profile("hemp", str(tmp_path)).version == 3


def test_a_pin_to_a_missing_version_says_what_exists(tmp_path):
    _write_profile(tmp_path, "denim", 1)
    with pytest.raises(ProfileNotFound, match=r"has versions \[1\], design pins @7"):
        load_profile("denim@7", str(tmp_path))


def test_a_file_that_misdeclares_itself_is_refused(tmp_path):
    """The filename and the declared identity must agree, or the pin recorded
    on a delivered design points at something else."""
    _write_profile(tmp_path, "wool", 1)
    path = tmp_path / "wool@1.yaml"
    path.write_text(path.read_text().replace("name: wool", "name: cashmere"))
    with pytest.raises(ProfileNotFound, match="declares"):
        load_profile("wool@1", str(tmp_path))


def test_current_profiles_lists_one_version_per_fabric(tmp_path):
    _write_profile(tmp_path, "linen", 1)
    _write_profile(tmp_path, "linen", 2)
    _write_profile(tmp_path, "hemp", 1)
    assert current_profiles(str(tmp_path)) == ["hemp@1", "linen@2"]
    assert available_profiles(str(tmp_path)) == ["hemp@1", "linen@1", "linen@2"]
