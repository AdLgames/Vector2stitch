"""Export: the file the machine actually reads.

Round-trip is not a formality. A writer that shifts a penetration or drops a
colour change produces a file that previews perfectly and sews wrong.
"""

from __future__ import annotations

import math

import pyembroidery
import pytest
from conftest import design, run_object

from engine.export import (
    FIXED_FILE_TIMESTAMP,
    FORMATS,
    RoundTripError,
    limits_for,
    split_long_moves,
    verify,
    verify_or_raise,
    write,
    write_all,
)
from engine.export.limits import UnsupportedFormat
from engine.plan import Cmd, PlanStitch, StitchPlan
from engine.stitchgen import generate
from engine.units import mm_to_units, units_to_mm

FORMAT_NAMES = sorted(FORMATS)
_WRITERS = {
    "dst": pyembroidery.DstWriter,
    "pes": pyembroidery.PesWriter,
    "jef": pyembroidery.JefWriter,
    "exp": pyembroidery.ExpWriter,
}


@pytest.mark.parametrize("extension", FORMAT_NAMES)
def test_every_writer_survives_a_round_trip(tmp_path, two_color_design, extension):
    plan = generate(two_color_design)
    path = write(plan, tmp_path / f"design.{extension}")
    report = verify(plan, path)
    assert report.ok, report.problems
    assert report.penetrations_found == plan.stitch_count()


@pytest.mark.parametrize("extension", FORMAT_NAMES)
def test_penetrations_come_back_exactly(tmp_path, single_run_design, extension):
    plan = generate(single_run_design)
    path = write(plan, tmp_path / f"design.{extension}")
    assert verify(plan, path).first_mismatch is None


@pytest.mark.parametrize("extension", FORMAT_NAMES)
def test_colour_changes_survive(tmp_path, two_color_design, extension):
    plan = generate(two_color_design)
    report = verify(plan, write(plan, tmp_path / f"design.{extension}"))
    assert report.color_changes_found == report.color_changes_expected == 1


@pytest.mark.parametrize("extension", FORMAT_NAMES)
def test_no_move_exceeds_the_format_limit(tmp_path, two_color_design, extension):
    """A 60 mm travel has to leave as several legal jumps, not one illegal one."""
    plan = generate(two_color_design)
    report = verify(plan, write(plan, tmp_path / f"design.{extension}"))
    assert report.max_move_mm <= limits_for(extension).max_move_mm


def test_long_moves_are_split_into_legal_steps():
    stitches = [
        PlanStitch(x_mm=0, y_mm=0),
        PlanStitch(x_mm=100, y_mm=0, cmd=Cmd.JUMP),
    ]
    split = split_long_moves(stitches, 12.1)
    pairs = zip(split, split[1:], strict=False)
    spans = [math.dist((a.x_mm, a.y_mm), (b.x_mm, b.y_mm)) for a, b in pairs]
    assert max(spans) <= 12.1 + 1e-9
    assert split[-1].x_mm == 100
    assert all(s.cmd is Cmd.JUMP for s in split[1:])


def test_splitting_preserves_the_owning_object():
    """Checks and the editor point at objects, so the link cannot be lost."""
    stitches = [
        PlanStitch(x_mm=0, y_mm=0, object_id="obj_001"),
        PlanStitch(x_mm=100, y_mm=0, cmd=Cmd.JUMP, object_id="obj_002"),
    ]
    assert {s.object_id for s in split_long_moves(stitches, 12.1)} == {"obj_001", "obj_002"}


def test_splitting_leaves_short_moves_alone():
    stitches = [PlanStitch(x_mm=0, y_mm=0), PlanStitch(x_mm=2, y_mm=0)]
    assert split_long_moves(stitches, 12.1) == stitches


def test_trims_and_colour_changes_do_not_anchor_a_move():
    """A trim carries no travel of its own; the move is measured stitch to stitch."""
    stitches = [
        PlanStitch(x_mm=0, y_mm=0),
        PlanStitch(x_mm=0, y_mm=0, cmd=Cmd.TRIM),
        PlanStitch(x_mm=6, y_mm=0, cmd=Cmd.JUMP),
    ]
    assert len(split_long_moves(stitches, 12.1)) == 3


@pytest.mark.parametrize("extension", FORMAT_NAMES)
def test_our_limits_are_no_wider_than_the_writers(extension):
    """Our table is authoritative for the engine, but it must stay inside what
    the writer library will actually emit -- a library change that widened a
    limit should fail here rather than silently change output."""
    limits = limits_for(extension)
    writer_max_units = _WRITERS[extension].MAX_JUMP_DISTANCE
    assert mm_to_units(limits.max_move_mm, limits.unit_mm) <= writer_max_units


def test_unknown_format_is_refused(tmp_path, single_run_design):
    plan = generate(single_run_design)
    with pytest.raises(UnsupportedFormat, match="not a supported output format"):
        write(plan, tmp_path / "design.xyz")


def test_write_all_writes_the_delivery_set(tmp_path, single_run_design):
    plan = generate(single_run_design)
    paths = write_all(plan, tmp_path / "out", "logo", ["dst", "pes"])
    assert [p.name for p in paths] == ["logo.dst", "logo.pes"]
    assert all(p.exists() for p in paths)


def test_verify_or_raise_refuses_a_file_that_does_not_match(tmp_path, single_run_design):
    plan = generate(single_run_design)
    path = write(plan, tmp_path / "design.dst")
    tampered = plan.model_copy(
        update={"stitches": plan.stitches + [PlanStitch(x_mm=5, y_mm=5)]}
    )
    with pytest.raises(RoundTripError, match="penetration count changed"):
        verify_or_raise(tampered, path)


def test_design_geometry_is_preserved_through_the_file(tmp_path, single_run_design):
    """Sewn extents must match the design's, within one machine unit."""
    plan = generate(single_run_design)
    path = write(plan, tmp_path / "design.dst")
    pattern = pyembroidery.read(str(path))
    points = [
        (x, y)
        for x, y, cmd in pattern.stitches
        if (cmd & pyembroidery.COMMAND_MASK) == pyembroidery.STITCH
    ]
    width_mm = units_to_mm(max(p[0] for p in points) - min(p[0] for p in points), 0.1)
    plan_min_x, _, plan_max_x, _ = plan.extents_mm()
    assert width_mm == pytest.approx(plan_max_x - plan_min_x, abs=0.1)


def test_empty_plan_writes_nothing_and_verifies_clean(tmp_path):
    plan = StitchPlan(profile_ref="twill@1")
    path = write(plan, tmp_path / "empty.dst")
    assert verify(plan, path).penetrations_expected == 0


def test_a_design_with_one_run_object_exports_to_dst_and_pes(tmp_path):
    """M0's acceptance criterion, as a test."""
    doc = design([run_object("obj_001", [(0, 0), (20, 0), (30, 15), (40, 0), (60, 0)])])
    plan = generate(doc)
    for path in write_all(plan, tmp_path, "m0", ["dst", "pes"]):
        assert verify_or_raise(plan, path).ok


def test_formats_that_store_a_creation_date_get_a_fixed_one(tmp_path, single_run_design):
    """JEF embeds a creation timestamp. Left to the wall clock it would make
    every write a different file, which breaks reproducibility for no gain."""
    plan = generate(single_run_design)
    data = write(plan, tmp_path / "design.jef").read_bytes()
    assert FIXED_FILE_TIMESTAMP.encode() in data


def test_a_caller_can_still_ask_for_a_real_date(tmp_path, single_run_design):
    plan = generate(single_run_design)
    data = write(plan, tmp_path / "design.jef", created="20260101120000").read_bytes()
    assert b"20260101120000" in data


@pytest.mark.parametrize("extension", FORMAT_NAMES)
def test_a_travel_that_splits_exactly_onto_the_limit_stays_legal(tmp_path, extension):
    """Two endpoints rounding in opposite directions can push a move split to
    exactly the limit one unit over it. Caught in a cap calibration pattern,
    where a 24.2 mm travel became two 12.1 mm jumps and one wrote as 12.2 mm."""
    limits = limits_for(extension)
    span = limits.max_move_mm * 2
    doc = design(
        [
            run_object("obj_001", [(0.0, 0.0), (5.0, 0.0)]),
            run_object("obj_002", [(0.05, span + 0.05), (5.0, span)], z_order=1),
        ]
    )
    plan = generate(doc)
    report = verify(plan, write(plan, tmp_path / f"design.{extension}"))
    assert report.ok, report.problems
    assert report.max_move_mm <= limits.max_move_mm
