"""Machine profiles: the shop's hardware, described and tuned by the designer."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from conftest import design, run_object

from engine.ir.schema import Design, IRDocument, Placement
from engine.machines import (
    MachineNotFound,
    available_machines,
    load_machine,
    resolve_setup,
    search_path,
)
from engine.profiles.loader import load_profile
from engine.stitchgen import generate

SHIPPED = Path(__file__).resolve().parents[1] / "engine/machines/data"


def _machine_file(directory: Path, name: str, version: int = 1, **overrides) -> Path:
    """Write a machine profile into a temp directory, as a designer would."""
    raw = yaml.safe_load((SHIPPED / "multineedle_6head@1.yaml").read_text())
    raw["name"] = name
    raw["version"] = version
    raw.update(overrides)
    path = directory / f"{name}@{version}.yaml"
    path.write_text(yaml.safe_dump(raw))
    return path


def _cap_design():
    doc = design([run_object("obj_001", [(0, 0), (40, 0)])], profile_ref="cap@1")
    return IRDocument(
        design=Design(
            width_mm=60,
            height_mm=40,
            placement=Placement.CAP_FRONT,
            fabric_profile="cap@1",
            thread_brand="madeira_polyneon_40",
        ),
        objects=doc.objects,
    )


# --- loading and the search path -------------------------------------------


def test_templates_ship_so_there_is_something_to_copy():
    assert [ref for ref, _ in available_machines()] == [
        "multineedle_6head@1",
        "single_head@1",
    ]


def test_no_shipped_machine_claims_to_be_calibrated():
    """They are spec-sheet templates. Only the shop can make them true."""
    for ref, _ in available_machines():
        assert load_machine(ref).calibrated is False


def test_a_designers_own_file_shadows_a_shipped_one(tmp_path):
    """The whole point: local hardware overrides our template completely."""
    _machine_file(tmp_path, "multineedle_6head", heads=12)
    assert load_machine("multineedle_6head", tmp_path).heads == 12
    assert load_machine("multineedle_6head").heads == 6


def test_the_shop_directory_is_searched_before_the_shipped_one(tmp_path, monkeypatch):
    _machine_file(tmp_path, "multineedle_6head", heads=4)
    monkeypatch.setenv("V2S_MACHINE_DIR", str(tmp_path))
    assert load_machine("multineedle_6head").heads == 4
    assert tmp_path in search_path()


def test_an_explicit_directory_beats_the_environment(tmp_path, monkeypatch):
    shop = tmp_path / "shop"
    other = tmp_path / "other"
    shop.mkdir()
    other.mkdir()
    _machine_file(shop, "press", heads=2)
    _machine_file(other, "press", heads=8)
    monkeypatch.setenv("V2S_MACHINE_DIR", str(shop))
    assert load_machine("press", other).heads == 8


def test_an_unpinned_name_takes_the_newest_version(tmp_path):
    _machine_file(tmp_path, "barudan_left", 1)
    _machine_file(tmp_path, "barudan_left", 4, heads=8)
    assert load_machine("barudan_left", tmp_path).version == 4


def test_a_missing_machine_says_how_to_add_one(tmp_path):
    with pytest.raises(MachineNotFound, match="V2S_MACHINE_DIR"):
        load_machine("nonexistent", tmp_path)


def test_a_cap_driver_without_a_cap_field_is_refused(tmp_path):
    _machine_file(
        tmp_path,
        "broken",
        fields={"flat_width_mm": 300.0, "flat_height_mm": 300.0},
    )
    with pytest.raises(Exception, match="cap field"):
        load_machine("broken", tmp_path)


# --- resolving fabric against machine --------------------------------------


def test_the_slower_ceiling_wins(single_run_design):
    """Fabric says 1000 spm, this machine holds 800. The machine wins."""
    setup = resolve_setup(
        load_profile("twill@1"), single_run_design, machine=load_machine("single_head@1")
    )
    assert setup.max_spm == 800
    assert setup.speed_source == "machine"


def test_the_fabric_ceiling_wins_when_it_is_lower(tmp_path, single_run_design):
    """A fast machine does not license sewing a delicate fabric fast."""
    _machine_file(tmp_path, "fast", speed={"max_spm_flat": 1500, "max_spm_cap": 900})
    setup = resolve_setup(
        load_profile("twill@1"), single_run_design, machine=load_machine("fast", tmp_path)
    )
    assert setup.max_spm == 1000
    assert setup.speed_source == "fabric"


def test_a_cap_placement_uses_the_cap_speed(tmp_path):
    doc = _cap_design()
    _machine_file(tmp_path, "shop", speed={"max_spm_flat": 1200, "max_spm_cap": 550})
    setup = resolve_setup(load_profile("cap@1"), doc, machine=load_machine("shop", tmp_path))
    assert setup.max_spm == 550


def test_gauged_tension_replaces_the_generic_range(tmp_path, single_run_design):
    _machine_file(
        tmp_path,
        "gauged",
        tension={"bobbin_gf_min": 24, "bobbin_gf_max": 26, "top_to_bobbin_ratio": 2.0},
    )
    setup = resolve_setup(
        load_profile("twill@1"), single_run_design, machine=load_machine("gauged", tmp_path)
    )
    assert setup.tension_source == "machine"
    assert setup.bobbin_gf_min == 24
    assert setup.top_gf == 50.0


def test_an_ungauged_machine_falls_back_and_says_so(single_run_design):
    setup = resolve_setup(
        load_profile("twill@1"), single_run_design, machine=load_machine("single_head@1")
    )
    assert setup.tension_source == "fabric"
    assert any("No gauged tension" in w for w in setup.warnings)


def test_no_machine_profile_still_produces_a_setup(single_run_design):
    """A shop that has not described its hardware yet still gets a sheet."""
    setup = resolve_setup(load_profile("twill@1"), single_run_design)
    assert setup.ok
    assert setup.machine_ref is None
    assert any("No machine profile" in w for w in setup.warnings)


# --- blockers: what will not sew -------------------------------------------


def test_a_cap_on_a_machine_with_no_cap_driver_is_refused():
    setup = resolve_setup(
        load_profile("cap@1"), _cap_design(), machine=load_machine("single_head@1")
    )
    assert not setup.ok
    assert any("cap driver" in b for b in setup.blockers)


def test_a_design_larger_than_the_field_is_refused(tmp_path):
    doc = design([run_object("obj_001", [(0, 0), (250, 0)])])
    plan = generate(doc, load_profile("twill@1"))
    _machine_file(tmp_path, "small", fields={"flat_width_mm": 100.0, "flat_height_mm": 100.0},
                  capabilities={"auto_trim": True, "cap_driver": False, "formats": ["dst"]})
    setup = resolve_setup(
        load_profile("twill@1"), doc, plan, load_machine("small", tmp_path)
    )
    assert not setup.ok
    assert any("the field is" in b for b in setup.blockers)


def test_a_design_that_fits_is_not_refused(single_run_design):
    plan = generate(single_run_design, load_profile("twill@1"))
    setup = resolve_setup(
        load_profile("twill@1"), single_run_design, plan, load_machine("single_head@1")
    )
    assert setup.ok


# --- warnings: what the operator needs to know -----------------------------


def test_more_colours_than_needles_warns_about_a_rethread(tmp_path, two_color_design):
    plan = generate(two_color_design, load_profile("twill@1"))
    _machine_file(tmp_path, "onecolour", needles_per_head=1)
    setup = resolve_setup(
        load_profile("twill@1"), two_color_design, plan, load_machine("onecolour", tmp_path)
    )
    assert any("rethread" in w for w in setup.warnings)
    assert setup.ok  # a rethread is work, not a blocker


def test_no_auto_trimmer_warns_about_manual_cuts(two_color_design):
    plan = generate(two_color_design, load_profile("twill@1"))
    setup = resolve_setup(
        load_profile("twill@1"), two_color_design, plan, load_machine("single_head@1")
    )
    assert any("no auto trimmer" in w for w in setup.warnings)


def test_a_format_the_controller_cannot_read_warns(single_run_design):
    plan = generate(single_run_design, load_profile("twill@1"))
    setup = resolve_setup(
        load_profile("twill@1"),
        single_run_design,
        plan,
        load_machine("single_head@1"),
        formats=["exp"],
    )
    assert any("does not read exp" in w for w in setup.warnings)


def test_an_uncalibrated_machine_says_so(single_run_design):
    setup = resolve_setup(
        load_profile("twill@1"), single_run_design, machine=load_machine("single_head@1")
    )
    assert any("not calibrated" in w for w in setup.warnings)


def test_the_machine_never_changes_a_stitch(single_run_design):
    """Hardware differences are refused or flagged, never silently digitized
    around -- otherwise the same design on two machines is two designs."""
    profile = load_profile("twill@1")
    plan = generate(single_run_design, profile)
    for ref in ("single_head@1", "multineedle_6head@1"):
        resolve_setup(profile, single_run_design, plan, load_machine(ref))
    assert generate(single_run_design, profile).model_dump_json() == plan.model_dump_json()
