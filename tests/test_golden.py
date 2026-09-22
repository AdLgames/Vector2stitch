"""The golden suite, as a test.

CI runs it on every engine change. A difference is not automatically a
failure of the engine -- it may be an improvement -- but it is always a failure
to have changed output without saying so.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.ir.schema import load_ir
from engine.profiles.loader import load_profile
from engine.stitchgen import generate
from lab.golden import compare, metrics, run

ROOT = Path(__file__).resolve().parents[1]
DESIGNS = ROOT / "golden/designs"
APPROVED = ROOT / "golden/approved"


def test_the_suite_has_designs_in_it():
    """An empty golden suite passes everything, which is worse than none."""
    designs = list(DESIGNS.glob("*.ir.json"))
    assert len(designs) >= 20


def test_every_design_has_an_approved_result():
    for path in DESIGNS.glob("*.ir.json"):
        name = path.name.removesuffix(".ir.json")
        assert (APPROVED / f"{name}.json").exists(), name


def test_the_suite_covers_every_shipped_profile():
    """A regression that only shows up on pique is still a regression."""
    refs = {load_ir(path).design.fabric_profile for path in DESIGNS.glob("*.ir.json")}
    assert {"twill@1", "pique@1", "cap@1"} <= refs


def test_engine_output_still_matches_approval():
    """The one that actually guards the engine."""
    failures = [result for result in run(DESIGNS, APPROVED) if not result.ok]
    assert not failures, "\n".join(
        f"{result.design}: {'; '.join(result.differences)}" for result in failures
    )


def test_no_golden_design_is_blocked_by_the_checks():
    """Approved output that our own checks refuse would mean one of the two
    is lying."""
    for path in sorted(DESIGNS.glob("*.ir.json")):
        approved = json.loads((APPROVED / f"{path.name.removesuffix('.ir.json')}.json").read_text())
        assert approved["blocking_findings"] == [], path.name


def test_a_changed_stitch_count_is_caught(tmp_path):
    path = next(iter(sorted(DESIGNS.glob("*.ir.json"))))
    doc = load_ir(path)
    current = metrics(doc, generate(doc, load_profile(doc.design.fabric_profile)))
    approved = dict(current, stitch_count=int(current["stitch_count"] * 1.5))
    result = compare("x", current, approved)
    assert not result.ok
    assert "stitch count" in result.differences[0]


def test_rounding_noise_does_not_trip_the_suite():
    """A tolerance that fails on nothing teaches people to regenerate without
    looking, which is how a regression net becomes a rubber stamp."""
    path = next(iter(sorted(DESIGNS.glob("*.ir.json"))))
    doc = load_ir(path)
    current = metrics(doc, generate(doc, load_profile(doc.design.fabric_profile)))
    approved = dict(current, width_mm=current["width_mm"] + 0.001)
    assert compare("x", current, approved).ok


def test_a_changed_trim_count_is_caught():
    path = next(iter(sorted(DESIGNS.glob("*.ir.json"))))
    doc = load_ir(path)
    current = metrics(doc, generate(doc, load_profile(doc.design.fabric_profile)))
    approved = dict(current, trims=current["trims"] + 1)
    assert "trims" in compare("x", current, approved).differences[0]


def test_a_shifted_length_distribution_is_caught():
    """What a density or compensation change looks like, even when the stitch
    count barely moves."""
    path = next(iter(sorted(DESIGNS.glob("*.ir.json"))))
    doc = load_ir(path)
    current = metrics(doc, generate(doc, load_profile(doc.design.fabric_profile)))
    shifted = dict(current["length_histogram"])
    first = next(iter(shifted))
    shifted[first] = shifted[first] + 40
    approved = dict(current, length_histogram=shifted)
    result = compare("x", current, approved)
    assert not result.ok
    assert "distribution moved" in result.differences[0]


def test_a_design_with_no_approval_fails_rather_than_passing(tmp_path):
    """Silence must not read as approval."""
    designs = tmp_path / "designs"
    designs.mkdir()
    source = next(iter(sorted(DESIGNS.glob("*.ir.json"))))
    (designs / source.name).write_text(source.read_text())
    results = run(designs, tmp_path / "approved")
    assert results and not results[0].ok
    assert results[0].differences == ["never approved"]


def test_approving_records_current_output(tmp_path):
    designs = tmp_path / "designs"
    designs.mkdir()
    source = next(iter(sorted(DESIGNS.glob("*.ir.json"))))
    (designs / source.name).write_text(source.read_text())
    approved = tmp_path / "approved"

    assert not run(designs, approved)[0].ok
    run(designs, approved, approve=True)
    assert run(designs, approved)[0].ok


@pytest.mark.parametrize("key", ["stitch_count", "trims", "jumps", "color_changes", "threads"])
def test_the_metrics_a_regression_hides_in_are_all_recorded(key):
    path = next(iter(sorted(DESIGNS.glob("*.ir.json"))))
    doc = load_ir(path)
    assert key in metrics(doc, generate(doc, load_profile(doc.design.fabric_profile)))
