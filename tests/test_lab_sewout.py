"""The sew-out log: a sew-out that is not written down did not happen."""

from __future__ import annotations

from datetime import date

import pytest

from engine.lab import build_pattern
from engine.lab.targets import Axis, MeasurementTarget
from lab.cli import EXIT_ERROR, EXIT_OK, EXIT_OUT_OF_TOLERANCE
from lab.cli import main as lab_main
from lab.defects import USUAL_CAUSE, Defect
from lab.sewout import Consumables, SewOut, append, evaluate, load_targets, read_log

TARGETS = [
    MeasurementTarget(id="a", description="20 mm square across", designed_mm=20.0, axis=Axis.X),
    MeasurementTarget(id="b", description="20 mm square up", designed_mm=20.0, axis=Axis.Y),
]


def _sewout(**overrides) -> SewOut:
    base = {
        "sewn_on": date(2026, 1, 5),
        "operator": "kim",
        "pattern": "dimension_grid",
        "fabric_profile": "twill@1",
        "engine_version": "test",
        "machine_profile": "multineedle_6head@1",
        "consumables": Consumables(
            thread="Madeira Polyneon 40",
            needle="75/11",
            stabilizer="cutaway 2.0 oz",
            speed_spm=850,
        ),
        "measurements": {"a": 20.0, "b": 20.0},
    }
    base.update(overrides)
    return SewOut(**base)


def test_a_perfect_sewout_passes():
    assert evaluate(_sewout(), TARGETS).passed


def test_error_is_signed_so_draw_in_is_visible():
    evaluation = evaluate(_sewout(measurements={"a": 19.6, "b": 19.8}), TARGETS)
    assert all(d.error_mm < 0 for d in evaluation.deviations)
    assert evaluation.mean_error_mm() == pytest.approx(-0.3)


def test_a_measurement_exactly_on_tolerance_passes():
    """19.7 - 20.0 is not exactly -0.3 in binary floating point. A caliper
    reading does not carry sixteen digits, and neither should the comparison."""
    evaluation = evaluate(_sewout(measurements={"a": 19.7, "b": 20.3}), TARGETS)
    assert all(d.within_tolerance for d in evaluation.deviations)
    assert evaluation.passed


def test_a_measurement_past_tolerance_fails():
    evaluation = evaluate(_sewout(measurements={"a": 19.5, "b": 20.0}), TARGETS)
    assert not evaluation.passed
    assert evaluation.worst.target.id == "a"


def test_skipping_half_the_calipers_is_not_a_pass():
    evaluation = evaluate(_sewout(measurements={"a": 20.0}), TARGETS)
    assert evaluation.unmeasured == ["b"]
    assert not evaluation.passed


def test_measuring_something_the_pattern_does_not_have_is_refused():
    with pytest.raises(KeyError, match="not in this pattern"):
        evaluate(_sewout(measurements={"z": 20.0}), TARGETS)


def test_the_log_round_trips(tmp_path):
    log = tmp_path / "sewouts.jsonl"
    append(_sewout(), log)
    append(_sewout(operator="sam"), log)
    records = read_log(log)
    assert [r.operator for r in records] == ["kim", "sam"]
    assert records[0].consumables.needle == "75/11"


def test_an_absent_log_reads_as_empty(tmp_path):
    assert read_log(tmp_path / "nothing.jsonl") == []


def test_every_defect_in_the_taxonomy_names_a_cause():
    """The vocabulary exists so a sew-out score points at something in the
    code, not at an adjective."""
    assert set(USUAL_CAUSE) == set(Defect)


# --- the CLI, end to end ----------------------------------------------------


def _write_targets(tmp_path):
    import json

    doc, targets = build_pattern("dimension_grid", "twill@1")
    path = tmp_path / "dimension_grid.targets.json"
    path.write_text(
        json.dumps(
            {
                "pattern": "dimension_grid",
                "fabric_profile": "twill@1",
                "engine_version": doc.engine_version,
                "targets": [t.model_dump(mode="json") for t in targets],
            }
        )
    )
    return path, targets


def _record_args(targets_path, log, measurements):
    args = [
        "record",
        str(targets_path),
        "--log",
        str(log),
        "--operator",
        "kim",
        "--profile",
        "twill@1",
        "--engine-version",
        "test",
        "--thread",
        "Madeira Polyneon 40",
        "--needle",
        "75/11",
        "--stabilizer",
        "cutaway 2.0 oz",
        "--speed",
        "850",
    ]
    for target_id, value in measurements.items():
        args += ["--measure", f"{target_id}={value}"]
    return args


def test_recording_a_good_sewout_exits_clean(tmp_path):
    targets_path, targets = _write_targets(tmp_path)
    log = tmp_path / "sewouts.jsonl"
    perfect = {t.id: t.designed_mm for t in targets}
    assert lab_main(_record_args(targets_path, log, perfect)) == EXIT_OK
    assert len(read_log(log)) == 1


def test_recording_an_out_of_tolerance_sewout_exits_distinctly(tmp_path, capsys):
    """Exit 2 is a result, not a tool failure: it is the one that means a
    parameter has to move."""
    targets_path, targets = _write_targets(tmp_path)
    log = tmp_path / "sewouts.jsonl"
    small = {t.id: t.designed_mm - 0.8 for t in targets}
    assert lab_main(_record_args(targets_path, log, small)) == EXIT_OUT_OF_TOLERANCE
    out = capsys.readouterr().out
    assert "out of tolerance" in out
    assert "FAIL" in out
    assert len(read_log(log)) == 1  # a failing sew-out is still data


def test_a_bad_target_id_is_refused_and_nothing_is_logged(tmp_path):
    targets_path, _ = _write_targets(tmp_path)
    log = tmp_path / "sewouts.jsonl"
    assert lab_main(_record_args(targets_path, log, {"not_a_target": 20.0})) == EXIT_ERROR
    assert read_log(log) == []


def test_report_says_which_way_the_profile_is_wrong(tmp_path, capsys):
    targets_path, targets = _write_targets(tmp_path)
    log = tmp_path / "sewouts.jsonl"
    small = {t.id: t.designed_mm - 0.5 for t in targets}
    lab_main(_record_args(targets_path, log, small))
    capsys.readouterr()

    assert lab_main(["report", "--log", str(log), "--targets", str(targets_path)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "under-compensating" in out
    assert "-0.50 mm" in out


def test_report_on_an_empty_log_says_so(tmp_path, capsys):
    assert lab_main(["report", "--log", str(tmp_path / "none.jsonl")]) == EXIT_ERROR
    assert "no sew-outs recorded" in capsys.readouterr().err


def test_targets_file_written_by_calibrate_loads_back(tmp_path):
    targets_path, targets = _write_targets(tmp_path)
    assert [t.id for t in load_targets(targets_path)] == [t.id for t in targets]
