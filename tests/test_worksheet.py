"""The worksheet: what the operator needs that the machine file cannot carry."""

from __future__ import annotations

from engine.cli.worksheet import estimate_runtime_minutes, worksheet
from engine.machines import load_machine, resolve_setup
from engine.profiles.loader import load_profile
from engine.stitchgen import generate


def test_top_tension_is_derived_from_the_bobbin_baseline(single_run_design):
    """Set by ratio off a gauge reading, not by feel."""
    profile = load_profile("twill@1")
    setup = resolve_setup(profile, single_run_design)
    assert setup.top_gf == 20 * profile.machine.top_to_bobbin_tension_ratio


def test_runtime_estimate_uses_the_speed_the_machine_will_hold(single_run_design):
    profile = load_profile("twill@1")
    plan = generate(single_run_design, profile)
    setup = resolve_setup(profile, single_run_design, plan, load_machine("single_head@1"))
    assert estimate_runtime_minutes(plan, setup) == plan.stitch_count() / setup.max_spm
    assert setup.max_spm == 800  # the machine's ceiling, below the fabric's 1000


def test_a_slower_machine_makes_the_same_design_take_longer(single_run_design):
    profile = load_profile("twill@1")
    plan = generate(single_run_design, profile)
    fast = resolve_setup(profile, single_run_design, plan, load_machine("multineedle_6head@1"))
    slow = resolve_setup(profile, single_run_design, plan, load_machine("single_head@1"))
    assert estimate_runtime_minutes(plan, slow) > estimate_runtime_minutes(plan, fast)


def test_worksheet_names_the_machine_and_where_the_numbers_came_from(single_run_design):
    profile = load_profile("twill@1")
    plan = generate(single_run_design, profile)
    setup = resolve_setup(profile, single_run_design, plan, load_machine("single_head@1"))
    sheet = worksheet(single_run_design, plan, profile, setup)
    assert "single_head@1" in sheet
    assert "from the machine profile" in sheet
    assert "Sew field" in sheet


def test_worksheet_without_a_machine_says_the_numbers_are_generic(single_run_design):
    profile = load_profile("twill@1")
    sheet = worksheet(single_run_design, generate(single_run_design, profile), profile)
    assert "not specified" in sheet
    assert "No machine profile" in sheet


def test_worksheet_warns_while_the_profile_is_uncalibrated(single_run_design):
    profile = load_profile("twill@1")
    sheet = worksheet(single_run_design, generate(single_run_design, profile), profile)
    assert "NOT calibrated" in sheet
    assert "Test sew on scrap" in sheet


def test_worksheet_records_all_three_versions(single_run_design):
    profile = load_profile("twill@1")
    sheet = worksheet(single_run_design, generate(single_run_design, profile), profile)
    assert "Engine" in sheet and "Schema" in sheet and "twill@1" in sheet
