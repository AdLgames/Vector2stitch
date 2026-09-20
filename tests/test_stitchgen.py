"""Stitch generation: the properties a sewable file has to have."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from conftest import BLACK, RED, design, run_object

from engine.ir.schema import (
    EmbroideryObject,
    ObjectKind,
    ObjectParams,
    ParamSource,
    PolylineShape,
)
from engine.plan import Cmd
from engine.profiles.loader import load_profile
from engine.stitchgen import UnsupportedObject, UnsupportedProfile, generate, resolve
from engine.stitchgen.run import apply_bean, drop_short_stitches, resample, stitch_run, tie_points


def _distances(points):
    return [math.dist(a, b) for a, b in zip(points, points[1:], strict=False)]


def test_resample_keeps_original_vertices_so_corners_stay_sharp():
    points = resample(
        [(0, 0), (10, 0), (10, 10)], closed=False, target_length_mm=3.0, max_length_mm=12.0
    )
    assert (10.0, 0.0) in points
    assert points[0] == (0, 0)
    assert points[-1] == (10.0, 10.0)


def test_resample_never_exceeds_the_target_length():
    points = resample([(0, 0), (37, 0)], closed=False, target_length_mm=3.0, max_length_mm=12.0)
    assert max(_distances(points)) <= 3.0 + 1e-9


def test_resample_divides_evenly_so_no_segment_ends_with_a_stub():
    points = resample([(0, 0), (10, 0)], closed=False, target_length_mm=3.0, max_length_mm=12.0)
    spans = _distances(points)
    assert max(spans) - min(spans) < 1e-9


def test_resample_closes_a_closed_path():
    points = resample(
        [(0, 0), (10, 0), (10, 10)], closed=True, target_length_mm=20.0, max_length_mm=20.0
    )
    assert points[0] == points[-1]


def test_resample_obeys_the_machine_limit_over_a_longer_target():
    points = resample([(0, 0), (30, 0)], closed=False, target_length_mm=20.0, max_length_mm=12.0)
    assert max(_distances(points)) <= 12.0 + 1e-9


def test_short_stitches_are_dropped():
    points = drop_short_stitches([(0, 0), (0.1, 0), (0.2, 0), (5, 0)], 0.5)
    assert points == [(0, 0), (5, 0)]


def test_the_last_point_survives_the_short_stitch_filter():
    """It is where the object ends and where the tie-off goes."""
    points = drop_short_stitches([(0, 0), (5, 0), (5.1, 0)], 0.5)
    assert points[-1] == (5.1, 0)
    assert min(_distances(points)) >= 0.5


def test_bean_returns_to_the_end_of_the_path():
    points = apply_bean([(0, 0), (1, 0), (2, 0)], 3)
    assert points[0] == (0, 0)
    assert points[-1] == (2, 0)
    assert len(points) == 7


def test_even_bean_repeats_are_refused():
    with pytest.raises(ValueError, match="odd"):
        apply_bean([(0, 0), (1, 0)], 2)


def test_ties_run_along_the_path_not_across_it():
    ties = tie_points((0, 0), (10, 0), 0.8, 3)
    assert all(y == 0 for _, y in ties)
    assert ties[-1] == (0, 0)


def test_ties_on_a_degenerate_neighbour_are_skipped():
    assert tie_points((0, 0), (0, 0), 0.8, 3) == []


def test_run_generation_respects_the_stitch_floor():
    points = stitch_run(
        [(0, 0), (0.2, 0), (20, 0)],
        closed=False,
        target_length_mm=2.2,
        min_length_mm=0.5,
        max_length_mm=12.0,
        bean_repeats=1,
    )
    assert min(_distances(points)) >= 0.5


def test_plan_starts_and_ends_the_way_a_machine_expects(single_run_design):
    plan = generate(single_run_design)
    assert plan.stitches[-1].cmd is Cmd.END
    assert plan.stitches[0].cmd is Cmd.STITCH


def test_every_object_is_tied_in_and_tied_off(two_color_design, twill):
    """Without ties the first and last stitches pull straight back out."""
    plan = generate(two_color_design, twill)
    ties = twill.stitch.tie_stitches
    for object_id in ("obj_001", "obj_002"):
        owned = [s for s in plan.stitches if s.object_id == object_id and s.cmd is Cmd.STITCH]
        # tie-in, then the run, then tie-off: more penetrations than the run alone.
        assert len(owned) > ties * 2


def test_distant_objects_get_a_trim_not_a_dragged_thread(two_color_design, twill):
    plan = generate(two_color_design, twill)
    assert any(s.cmd is Cmd.TRIM for s in plan.stitches)
    assert any(s.cmd is Cmd.JUMP for s in plan.stitches)


def test_a_colour_change_is_emitted_once_per_new_thread(two_color_design):
    plan = generate(two_color_design)
    changes = [s for s in plan.stitches if s.cmd is Cmd.COLOR_CHANGE]
    assert len(changes) == 1
    assert [t.code for t in plan.threads] == ["1800", "1147"]


def test_one_colour_used_twice_does_not_change_colour():
    doc = design(
        [
            run_object("obj_001", [(0, 0), (20, 0)]),
            run_object("obj_002", [(0, 10), (20, 10)], z_order=1),
        ]
    )
    plan = generate(doc)
    assert not any(s.cmd is Cmd.COLOR_CHANGE for s in plan.stitches)
    assert len(plan.threads) == 1


def test_text_objects_name_their_own_milestone():
    text = EmbroideryObject(
        id="obj_001",
        kind=ObjectKind.TEXT,
        shape=PolylineShape(points=[(0, 0), (20, 0)]),
        thread=BLACK,
    )
    with pytest.raises(UnsupportedObject, match="M6"):
        generate(design([text]))


def test_parameters_come_from_the_profile_when_the_object_is_silent(twill):
    obj = run_object("obj_001", [(0, 0), (20, 0)])
    params = resolve(obj, twill)
    assert params.stitch_length_mm == twill.stitch.run_length_mm
    assert params.source["stitch_length_mm"] is ParamSource.PROFILE


def test_an_object_override_wins_and_keeps_its_declared_provenance(twill):
    obj = run_object(
        "obj_001",
        [(0, 0), (20, 0)],
        params=ObjectParams(stitch_length_mm=1.5),
        param_source={"stitch_length_mm": ParamSource.ML},
    )
    params = resolve(obj, twill)
    assert params.stitch_length_mm == 1.5
    assert params.source["stitch_length_mm"] is ParamSource.ML


def test_an_override_with_no_declared_source_is_recorded_as_human(twill):
    obj = run_object("obj_001", [(0, 0), (20, 0)], params=ObjectParams(stitch_length_mm=1.5))
    assert resolve(obj, twill).source["stitch_length_mm"] is ParamSource.HUMAN


def test_switching_fabric_profile_changes_the_stitches(single_run_design):
    """Fabric is an input, not an afterthought: the same art sews differently."""
    on_twill = generate(single_run_design, load_profile("twill@1"))
    on_cap = generate(single_run_design, load_profile("cap@1"))
    assert on_twill.stitch_count() != on_cap.stitch_count()


def test_plan_records_the_profile_that_made_it(single_run_design):
    assert generate(single_run_design, load_profile("pique@1")).profile_ref == "pique@1"


def test_thread_order_follows_sew_order(two_color_design):
    plan = generate(two_color_design)
    assert plan.threads[0].code == "1800"
    assert plan.threads[1].rgb == RED.rgb


def test_a_profile_on_another_thread_weight_is_refused(tmp_path, single_run_design):
    """Geometry is sized to what 40 wt covers. Swapping the cone without
    re-deriving density leaves gaps, or over-stitches and snaps thread."""
    import yaml

    source = Path("engine/profiles/data/twill@1.yaml")
    raw = yaml.safe_load(source.read_text())
    raw["name"] = "fine"
    raw["machine"]["thread_weight_wt"] = 60
    (tmp_path / "fine@1.yaml").write_text(yaml.safe_dump(raw))

    with pytest.raises(UnsupportedProfile, match="60 wt"):
        generate(single_run_design, load_profile("fine@1", str(tmp_path)))
