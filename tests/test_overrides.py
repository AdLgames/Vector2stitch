"""Shop overrides: one decorator's floor against our defaults."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml
from conftest import design, run_object
from pydantic import ValidationError

from engine.cli.main import EXIT_ERROR, EXIT_OK, main
from engine.cli.worksheet import worksheet
from engine.ir.schema import EmbroideryObject, FillShape, ObjectKind
from engine.profiles.loader import load_profile
from engine.profiles.overrides import (
    LARGE_CHANGE_FACTOR,
    OverrideEntry,
    OverrideError,
    ProfileOverride,
    apply_override,
    available_overrides,
    effective_profile,
    load_override,
    override_template,
)
from engine.stitchgen import generate


def _write_override(directory: Path, profile_ref: str = "pique@1", **overrides) -> Path:
    payload = {
        "profile": profile_ref,
        "shop": "Acme Decorators",
        "recorded_on": "2026-09-18",
        "overrides": {
            path: {"value": value, "reason": f"because of {path}"}
            for path, value in overrides.items()
        },
    }
    path = directory / f"{profile_ref}.override.yaml"
    path.write_text(yaml.safe_dump(payload))
    return path


def _fill_object(profile_ref: str) -> EmbroideryObject:
    from conftest import BLACK

    return EmbroideryObject(
        id="obj_001",
        kind=ObjectKind.FILL,
        shape=FillShape(outer=[(0.0, 0.0), (25.0, 0.0), (25.0, 25.0), (0.0, 25.0)]),
        thread=BLACK,
    )


# --- the file itself --------------------------------------------------------


def test_an_override_must_say_why():
    """An override without a reason cannot be reviewed, cannot be aggregated,
    and cannot be told from a typo a year from now."""
    with pytest.raises(ValidationError):
        OverrideEntry(value=0.5, reason="")


def test_evidence_is_optional_but_its_absence_is_visible():
    entry = OverrideEntry(value=0.5, reason="puckers otherwise")
    assert entry.evidence == ""


def test_an_override_names_the_profile_version_it_was_formed_against(tmp_path):
    """A shop's reasons were formed against a specific version of our numbers."""
    path = _write_override(tmp_path, "pique@1", **{"density.fill_row_spacing_mm": 0.48})
    raw = yaml.safe_load(path.read_text())
    raw["profile"] = "twill@1"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(OverrideError, match="declares profile"):
        load_override("pique@1", tmp_path)


def test_no_override_file_is_the_normal_case(tmp_path):
    assert load_override("pique@1", tmp_path) is None
    profile, applied = effective_profile("pique@1", tmp_path)
    assert applied == []
    assert profile == load_profile("pique@1")


# --- applying ---------------------------------------------------------------


def test_an_override_changes_the_profile(tmp_path):
    _write_override(tmp_path, "pique@1", **{"density.fill_row_spacing_mm": 0.48})
    profile, applied = effective_profile("pique@1", tmp_path)
    assert profile.density.fill_row_spacing_mm == 0.48
    assert [a.path for a in applied] == ["density.fill_row_spacing_mm"]
    assert applied[0].shipped == 0.45


def test_overriding_does_not_touch_the_shipped_profile(tmp_path):
    """The loader caches profiles. An override that mutated one would change
    what every other design in the process gets."""
    _write_override(tmp_path, "pique@1", **{"density.fill_row_spacing_mm": 0.48})
    effective_profile("pique@1", tmp_path)
    assert load_profile("pique@1").density.fill_row_spacing_mm == 0.45


def test_a_field_that_does_not_exist_is_refused(tmp_path):
    _write_override(tmp_path, "pique@1", **{"density.sparkle_mm": 0.4})
    with pytest.raises(OverrideError, match="no field"):
        effective_profile("pique@1", tmp_path)


def test_a_whole_section_cannot_be_overridden(tmp_path):
    _write_override(tmp_path, "pique@1", **{"density": 0.4})
    with pytest.raises(OverrideError, match="is a section"):
        effective_profile("pique@1", tmp_path)


def test_a_value_the_engine_would_reject_on_disk_is_rejected_here(tmp_path):
    """An override cannot produce a profile that could not have shipped."""
    _write_override(tmp_path, "pique@1", **{"density.fill_row_spacing_mm": -1.0})
    with pytest.raises(OverrideError, match="invalid profile"):
        effective_profile("pique@1", tmp_path)


def test_several_fields_apply_together(tmp_path):
    _write_override(
        tmp_path,
        "pique@1",
        **{
            "density.fill_row_spacing_mm": 0.48,
            "compensation.pull_comp_mm_per_side": 0.30,
        },
    )
    profile, applied = effective_profile("pique@1", tmp_path)
    assert profile.density.fill_row_spacing_mm == 0.48
    assert profile.compensation.pull_comp_mm_per_side == 0.30
    assert len(applied) == 2


def test_a_tenfold_change_is_flagged_as_probably_a_typo(tmp_path):
    """0.175 to 0.22 is experience. 0.175 to 1.75 is a misplaced decimal, and
    it should be said out loud before it reaches a garment."""
    _write_override(tmp_path, "twill@1", **{"compensation.pull_comp_mm_per_side": 1.75})
    _, applied = effective_profile("twill@1", tmp_path)
    assert applied[0].is_large


def test_a_plausible_adjustment_is_not_flagged(tmp_path):
    _write_override(tmp_path, "twill@1", **{"compensation.pull_comp_mm_per_side": 0.22})
    _, applied = effective_profile("twill@1", tmp_path)
    assert not applied[0].is_large
    assert LARGE_CHANGE_FACTOR > 1


def test_a_flagged_change_is_still_applied(tmp_path):
    """Their floor, their call. We say so; we do not overrule them."""
    _write_override(tmp_path, "twill@1", **{"compensation.pull_comp_mm_per_side": 1.75})
    profile, applied = effective_profile("twill@1", tmp_path)
    assert profile.compensation.pull_comp_mm_per_side == 1.75
    assert applied[0].is_large


# --- search path ------------------------------------------------------------


def test_the_environment_directory_is_searched(tmp_path, monkeypatch):
    _write_override(tmp_path, "pique@1", **{"density.fill_row_spacing_mm": 0.48})
    monkeypatch.setenv("V2S_PROFILE_DIR", str(tmp_path))
    profile, _ = effective_profile("pique@1")
    assert profile.density.fill_row_spacing_mm == 0.48


def test_an_explicit_directory_beats_the_environment(tmp_path, monkeypatch):
    shop = tmp_path / "shop"
    other = tmp_path / "other"
    shop.mkdir()
    other.mkdir()
    _write_override(shop, "pique@1", **{"density.fill_row_spacing_mm": 0.48})
    _write_override(other, "pique@1", **{"density.fill_row_spacing_mm": 0.50})
    monkeypatch.setenv("V2S_PROFILE_DIR", str(shop))
    profile, _ = effective_profile("pique@1", other)
    assert profile.density.fill_row_spacing_mm == 0.50


def test_available_overrides_lists_what_would_load(tmp_path):
    _write_override(tmp_path, "pique@1", **{"density.fill_row_spacing_mm": 0.48})
    _write_override(tmp_path, "twill@1", **{"density.fill_row_spacing_mm": 0.42})
    assert [ref for ref, _ in available_overrides(tmp_path)] == ["pique@1", "twill@1"]


# --- the template -----------------------------------------------------------


def test_the_template_lists_every_adjustable_field():
    """A shop should see what is adjustable next to our value, rather than
    guess at field names from an error message."""
    text = override_template(load_profile("pique@1"), "Acme")
    assert "density.fill_row_spacing_mm" in text
    assert "compensation.pull_comp_mm_per_side" in text
    assert "satin.short_stitch_depth" in text
    assert "0.45" in text


def test_the_template_starts_as_a_valid_empty_override():
    """Written out and loaded straight back, it changes nothing."""
    text = override_template(load_profile("pique@1"), "Acme")
    override = ProfileOverride.model_validate(yaml.safe_load(text))
    assert override.overrides == {}
    profile, applied = apply_override(load_profile("pique@1"), override)
    assert applied == []
    assert profile == load_profile("pique@1")


def test_the_template_does_not_offer_to_override_calibration_status():
    """calibrated is our claim about our own testing, not a shop's to set."""
    text = override_template(load_profile("pique@1"), "Acme")
    assert "calibrated:" not in text.split("overrides:")[1]


# --- effect on stitches -----------------------------------------------------


def test_an_override_changes_the_stitches(tmp_path):
    _write_override(tmp_path, "pique@1", **{"density.fill_row_spacing_mm": 0.60})
    shipped = generate(design([_fill_object("pique@1")], "pique@1"), load_profile("pique@1"))
    profile, applied = effective_profile("pique@1", tmp_path)
    adjusted = generate(
        design([_fill_object("pique@1")], "pique@1"), profile, [a.path for a in applied]
    )
    assert adjusted.stitch_count() < shipped.stitch_count()


def test_the_plan_records_which_fields_were_overridden(tmp_path):
    """"pique@1" is not reproducible if the shop quietly runs a different
    pull compensation."""
    _write_override(tmp_path, "pique@1", **{"compensation.pull_comp_mm_per_side": 0.30})
    profile, applied = effective_profile("pique@1", tmp_path)
    plan = generate(
        design([run_object("obj_001", [(0, 0), (20, 0)])], "pique@1"),
        profile,
        [a.path for a in applied],
    )
    assert plan.profile_overrides == ["compensation.pull_comp_mm_per_side"]
    assert plan.profile_ref == "pique@1"


def test_a_plan_without_overrides_records_none():
    plan = generate(design([run_object("obj_001", [(0, 0), (20, 0)])]))
    assert plan.profile_overrides == []


def test_the_worksheet_prints_the_overrides_and_the_reasons(tmp_path):
    _write_override(tmp_path, "pique@1", **{"compensation.pull_comp_mm_per_side": 0.30})
    profile, applied = effective_profile("pique@1", tmp_path)
    doc = design([run_object("obj_001", [(0, 0), (20, 0)])], "pique@1")
    plan = generate(doc, profile, [a.path for a in applied])
    sheet = worksheet(doc, plan, profile, None, applied)
    assert "SHOP OVERRIDES" in sheet
    assert "compensation.pull_comp_mm_per_side: 0.35 -> 0.3" in sheet
    assert "why:" in sheet


# --- the CLI ----------------------------------------------------------------


def test_override_init_scaffolds_a_file(tmp_path, capsys):
    argv = ["override", "init", "pique@1", "--shop", "Acme", "--out", str(tmp_path)]
    assert main(argv) == EXIT_OK
    path = tmp_path / "pique@1.override.yaml"
    assert path.exists()
    assert "Acme" in path.read_text()
    assert "V2S_PROFILE_DIR" in capsys.readouterr().out


def test_override_init_will_not_quietly_replace_a_shops_work(tmp_path, capsys):
    main(["override", "init", "pique@1", "--shop", "Acme", "--out", str(tmp_path)])
    assert main(["override", "init", "pique@1", "--shop", "Acme", "--out", str(tmp_path)]) == (
        EXIT_ERROR
    )
    assert "--force" in capsys.readouterr().err


def test_override_show_prints_each_change_with_its_reason(tmp_path, capsys):
    _write_override(tmp_path, "pique@1", **{"density.fill_row_spacing_mm": 0.48})
    assert main(["override", "show", "--profile-dir", str(tmp_path)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "0.45 -> 0.48" in out
    assert "why:" in out


def test_override_show_says_when_there_is_no_measurement_behind_a_change(tmp_path, capsys):
    _write_override(tmp_path, "pique@1", **{"density.fill_row_spacing_mm": 0.48})
    main(["override", "show", "--profile-dir", str(tmp_path)])
    assert "experience, not measurement" in capsys.readouterr().out


def test_override_show_with_nothing_to_show(tmp_path, capsys):
    assert main(["override", "show", "--profile-dir", str(tmp_path)]) == EXIT_ERROR
    assert "no override files" in capsys.readouterr().err


def test_digitize_applies_and_announces_overrides(tmp_path, capsys):
    shop = tmp_path / "shop"
    shop.mkdir()
    _write_override(shop, "pique@1", **{"compensation.pull_comp_mm_per_side": 0.30})
    examples = Path(__file__).resolve().parents[1] / "examples"
    code = main(
        [
            "digitize",
            str(examples / "m0_two_color_run.ir.json"),
            "--out",
            str(tmp_path / "out"),
            "--formats",
            "dst",
            "--profile-dir",
            str(shop),
        ]
    )
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "override: compensation.pull_comp_mm_per_side: 0.35 -> 0.3" in out
    assert "SHOP OVERRIDES" in (tmp_path / "out" / "m0_two_color_run.worksheet.txt").read_text()


def test_a_broken_override_stops_the_job_rather_than_guessing(tmp_path, capsys):
    shop = tmp_path / "shop"
    shop.mkdir()
    _write_override(shop, "pique@1", **{"density.nonsense": 1.0})
    examples = Path(__file__).resolve().parents[1] / "examples"
    code = main(
        [
            "digitize",
            str(examples / "m0_two_color_run.ir.json"),
            "--out",
            str(tmp_path / "out"),
            "--profile-dir",
            str(shop),
        ]
    )
    assert code == EXIT_ERROR
    assert "no field" in capsys.readouterr().err


def test_profiles_listing_shows_a_shops_overrides(tmp_path, capsys):
    _write_override(tmp_path, "pique@1", **{"density.fill_row_spacing_mm": 0.48})
    assert main(["profiles", "--profile-dir", str(tmp_path)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "override  density.fill_row_spacing_mm: 0.45 -> 0.48" in out


def test_recorded_on_is_a_real_date():
    override = ProfileOverride(
        profile="pique@1", shop="Acme", recorded_on=date(2026, 1, 5), overrides={}
    )
    assert override.recorded_on.year == 2026
