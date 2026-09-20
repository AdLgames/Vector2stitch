"""The worksheet: what the operator needs that the machine file cannot carry."""

from __future__ import annotations

from engine.cli.worksheet import estimate_runtime_minutes, top_tension_gf, worksheet
from engine.profiles.loader import load_profile
from engine.stitchgen import generate


def test_top_tension_is_derived_from_the_bobbin_baseline():
    """Set by ratio off a gauge reading, not by feel."""
    profile = load_profile("twill@1")
    expected = 20 * profile.machine.top_to_bobbin_tension_ratio
    assert top_tension_gf(profile) == expected


def test_runtime_estimate_uses_the_profile_speed(single_run_design):
    profile = load_profile("cap@1")
    plan = generate(single_run_design, profile)
    assert estimate_runtime_minutes(plan, profile) == plan.stitch_count() / profile.machine.max_spm


def test_a_cap_estimate_is_slower_than_the_same_design_on_twill(single_run_design):
    twill, cap = load_profile("twill@1"), load_profile("cap@1")
    on_twill = generate(single_run_design, twill)
    on_cap = generate(single_run_design, cap)
    assert estimate_runtime_minutes(on_cap, cap) > estimate_runtime_minutes(on_twill, twill)


def test_worksheet_warns_while_the_profile_is_uncalibrated(single_run_design):
    profile = load_profile("twill@1")
    sheet = worksheet(single_run_design, generate(single_run_design, profile), profile)
    assert "NOT calibrated" in sheet
    assert "Test sew on scrap" in sheet


def test_worksheet_records_all_three_versions(single_run_design):
    profile = load_profile("twill@1")
    sheet = worksheet(single_run_design, generate(single_run_design, profile), profile)
    assert "Engine" in sheet and "Schema" in sheet and "twill@1" in sheet
