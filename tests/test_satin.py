"""Satin columns: where most of the ways a file can ruin a garment live."""

from __future__ import annotations

import math

import pytest
from conftest import BLACK, design

from engine.ir.schema import EmbroideryObject, ObjectKind, ObjectParams, RailsShape
from engine.plan import Cmd
from engine.profiles.loader import load_profile
from engine.stitchgen import generate, mean_column_width
from engine.stitchgen.geometry import distance
from engine.stitchgen.satin import (
    SatinSpec,
    apply_short_stitches,
    compensate,
    rail_pairs,
    sample_count,
    split_lanes,
    stitch_satin,
)

STRAIGHT_LEFT = [(0.0, 0.0), (40.0, 0.0)]
STRAIGHT_RIGHT = [(0.0, 3.0), (40.0, 3.0)]


def _spec(**overrides) -> SatinSpec:
    base = {
        "spacing_mm": 0.4,
        "pull_comp_mm_per_side": 0.2,
        "max_width_mm": 7.0,
        "short_stitch": True,
        "short_stitch_min_spacing_mm": 0.25,
        "short_stitch_depth": 0.65,
        "split_overlap_mm": 0.3,
        "min_length_mm": 0.5,
    }
    base.update(overrides)
    return SatinSpec(**base)


def _arc(radius: float, step_deg: float = 3.0, sweep_deg: float = 90.0):
    steps = int(sweep_deg / step_deg) + 1
    return [
        (
            radius * math.cos(math.radians(index * step_deg)),
            radius * math.sin(math.radians(index * step_deg)),
        )
        for index in range(steps)
    ]


def _stitch_lengths(points):
    return [distance(a, b) for a, b in zip(points, points[1:], strict=False)]


def _satin_object(left, right, object_id="obj_001", **params):
    return EmbroideryObject(
        id=object_id,
        kind=ObjectKind.SATIN,
        shape=RailsShape(rails=(left, right)),
        thread=BLACK,
        params=ObjectParams(**params),
    )


# --- the zigzag itself ------------------------------------------------------


def test_every_stitch_crosses_the_column():
    """A stitch running along a rail instead of across it sews as a visible
    line down the edge. Every stitch length should be about the column width."""
    points = stitch_satin(STRAIGHT_LEFT, STRAIGHT_RIGHT, _spec())
    width = 3.0 + 2 * 0.2
    assert all(abs(length - width) < 0.05 for length in _stitch_lengths(points))


def test_penetrations_sit_at_the_density_spacing_along_each_rail():
    spec = _spec(pull_comp_mm_per_side=0.0)
    points = stitch_satin(STRAIGHT_LEFT, STRAIGHT_RIGHT, spec)
    one_side = points[::2]
    steps = [distance(a, b) for a, b in zip(one_side, one_side[1:], strict=False)]
    assert all(abs(step - spec.spacing_mm) < 0.02 for step in steps)


def test_a_denser_profile_puts_down_more_stitches():
    open_column = stitch_satin(STRAIGHT_LEFT, STRAIGHT_RIGHT, _spec(spacing_mm=0.6))
    dense_column = stitch_satin(STRAIGHT_LEFT, STRAIGHT_RIGHT, _spec(spacing_mm=0.3))
    assert len(dense_column) > len(open_column)


def test_sample_count_follows_the_longer_rail():
    """Spacing the inner rail correctly leaves visible gaps on the outside."""
    inner, outer = _arc(10.0), _arc(14.0)
    assert sample_count(inner, outer, 0.4) == sample_count(outer, inner, 0.4)
    assert sample_count(inner, outer, 0.4) > 1 + len(_arc(10.0))


def test_rails_with_different_vertex_counts_still_pair_across():
    """Arc-length pairing, not index pairing: the normal case on any curve."""
    left = [(0.0, 0.0), (40.0, 0.0)]
    right = [(0.0, 3.0), (10.0, 3.0), (20.0, 3.0), (30.0, 3.0), (40.0, 3.0)]
    pairs = rail_pairs(left, right, 11)
    for (lx, _), (rx, _) in pairs:
        assert abs(lx - rx) < 1e-9


# --- pull compensation ------------------------------------------------------


def test_compensation_widens_the_column_on_both_sides():
    left, right = compensate(((0.0, 0.0), (0.0, 3.0)), 0.25)
    assert left == pytest.approx((0.0, -0.25))
    assert right == pytest.approx((0.0, 3.25))


def test_compensation_is_applied_along_the_stitch_not_the_axes():
    """A diagonal column is widened along its own direction."""
    left, right = compensate(((0.0, 0.0), (3.0, 4.0)), 0.5)
    assert distance(left, right) == pytest.approx(5.0 + 1.0)


def test_zero_compensation_leaves_the_pair_alone():
    pair = ((0.0, 0.0), (0.0, 3.0))
    assert compensate(pair, 0.0) == pair


def test_a_compensated_column_sews_wider_than_it_was_drawn():
    plain = stitch_satin(STRAIGHT_LEFT, STRAIGHT_RIGHT, _spec(pull_comp_mm_per_side=0.0))
    compensated = stitch_satin(STRAIGHT_LEFT, STRAIGHT_RIGHT, _spec(pull_comp_mm_per_side=0.3))
    plain_width = max(y for _, y in plain) - min(y for _, y in plain)
    wide = max(y for _, y in compensated) - min(y for _, y in compensated)
    assert wide == pytest.approx(plain_width + 0.6, abs=1e-6)


# --- splitting wide columns -------------------------------------------------


def test_a_column_within_the_limit_is_one_lane():
    pairs = rail_pairs(STRAIGHT_LEFT, STRAIGHT_RIGHT, 20)
    assert len(split_lanes(pairs, 7.0, 0.3)) == 1


def test_a_wide_column_is_split_into_lanes():
    """A stitch longer than the limit has nothing holding its middle down: it
    snags on whatever the garment touches and pulls into a loop."""
    wide_right = [(0.0, 18.0), (40.0, 18.0)]
    lanes = split_lanes(rail_pairs(STRAIGHT_LEFT, wide_right, 20), 7.0, 0.3)
    assert len(lanes) == 3


def test_no_stitch_in_a_split_column_exceeds_the_limit():
    wide_right = [(0.0, 18.0), (40.0, 18.0)]
    spec = _spec(max_width_mm=7.0)
    points = stitch_satin(STRAIGHT_LEFT, wide_right, spec)
    assert max(_stitch_lengths(points)) <= spec.max_width_mm + 2 * spec.split_overlap_mm + 0.1


def test_split_lanes_overlap_so_no_fabric_shows_between_them():
    wide_right = [(0.0, 18.0), (40.0, 18.0)]
    lanes = split_lanes(rail_pairs(STRAIGHT_LEFT, wide_right, 20), 7.0, 0.3)
    first_lane_end = lanes[0][0][1][1]
    second_lane_start = lanes[1][0][0][1]
    assert second_lane_start < first_lane_end


def test_a_split_column_covers_the_whole_width():
    wide_right = [(0.0, 18.0), (40.0, 18.0)]
    points = stitch_satin(STRAIGHT_LEFT, wide_right, _spec(pull_comp_mm_per_side=0.0))
    assert min(y for _, y in points) == pytest.approx(0.0, abs=0.01)
    assert max(y for _, y in points) == pytest.approx(18.0, abs=0.01)


# --- short stitches on curves ----------------------------------------------


def test_a_tight_curve_crowds_its_inner_rail_and_short_stitches_relieve_it():
    """Penetrations piling into one hole is a thread break, then a needle break."""
    inner, outer = _arc(4.0), _arc(11.0)
    spec = _spec(short_stitch_min_spacing_mm=1.0)
    pairs = rail_pairs(inner, outer, sample_count(inner, outer, spec.spacing_mm))
    shortened = apply_short_stitches(pairs, spec)
    changed = [i for i, (a, b) in enumerate(zip(pairs, shortened, strict=True)) if a != b]
    assert changed
    for index in changed:
        assert distance(*shortened[index]) < distance(*pairs[index])


def test_only_alternate_stitches_are_shortened():
    """Shortening all of them would move the edge inward and read as a notch."""
    inner, outer = _arc(4.0), _arc(11.0)
    spec = _spec(short_stitch_min_spacing_mm=1.0)
    pairs = rail_pairs(inner, outer, sample_count(inner, outer, spec.spacing_mm))
    shortened = apply_short_stitches(pairs, spec)
    changed = [i for i, (a, b) in enumerate(zip(pairs, shortened, strict=True)) if a != b]
    assert all(index % 2 == 0 for index in changed)


def test_short_stitching_can_be_turned_off_per_object():
    inner, outer = _arc(4.0), _arc(11.0)
    spec = _spec(short_stitch=False, short_stitch_min_spacing_mm=1.0)
    pairs = rail_pairs(inner, outer, sample_count(inner, outer, spec.spacing_mm))
    assert apply_short_stitches(pairs, spec) == pairs


def test_a_straight_column_needs_no_short_stitches():
    spec = _spec(short_stitch_min_spacing_mm=0.25)
    pairs = rail_pairs(STRAIGHT_LEFT, STRAIGHT_RIGHT, 40)
    assert apply_short_stitches(pairs, spec) == pairs


# --- underlay ---------------------------------------------------------------


def _first_crossing_stitch(plan, column_width_mm: float) -> int:
    """Index of the first stitch that crosses the column rather than running
    along it -- i.e. where the underlay stops and the satin starts."""
    for index, (a, b) in enumerate(zip(plan.stitches, plan.stitches[1:], strict=False)):
        if a.cmd is Cmd.STITCH and b.cmd is Cmd.STITCH:
            if distance((a.x_mm, a.y_mm), (b.x_mm, b.y_mm)) > column_width_mm * 0.9:
                return index
    raise AssertionError("no stitch crosses the column")


def test_underlay_is_sewn_before_the_column():
    """Underlay first, top layer second. The other way round is decoration."""
    profile = load_profile("twill@1")
    plan = generate(design([_satin_object(STRAIGHT_LEFT, STRAIGHT_RIGHT)]), profile)
    boundary = _first_crossing_stitch(plan, 3.0)
    assert boundary > 10  # a whole edge-run layer precedes the column


def test_the_underlay_recipe_comes_from_the_column_width():
    """A 1.5 mm satin and a 6 mm satin want different things underneath."""
    profile = load_profile("twill@1")
    narrow = _satin_object([(0.0, 0.0), (40.0, 0.0)], [(0.0, 1.5), (40.0, 1.5)])
    wide = _satin_object([(0.0, 0.0), (40.0, 0.0)], [(0.0, 6.0), (40.0, 6.0)])
    assert profile.underlay.for_satin(mean_column_width(narrow)) == ["center_run"]
    assert profile.underlay.for_satin(mean_column_width(wide)) == ["edge_run", "zigzag"]


def test_underlay_stays_inside_the_finished_edge():
    """Underlay peeking out past the top layer reads as a shadow along the
    edge, which is worse than no underlay at all."""
    profile = load_profile("twill@1")
    plan = generate(design([_satin_object(STRAIGHT_LEFT, STRAIGHT_RIGHT)]), profile)
    boundary = _first_crossing_stitch(plan, 3.0)

    underlay = [s for s in plan.stitches[:boundary] if s.cmd is Cmd.STITCH]
    assert underlay
    inset = profile.underlay.inset_mm
    assert all(inset - 0.01 <= s.y_mm <= 3.0 - inset + 0.01 for s in underlay)

    column = [s for s in plan.stitches[boundary:] if s.cmd is Cmd.STITCH]
    comp = profile.compensation.pull_comp_mm_per_side
    assert min(s.y_mm for s in column) == pytest.approx(-comp, abs=0.01)


def test_an_object_can_override_its_underlay():
    doc = design([_satin_object(STRAIGHT_LEFT, STRAIGHT_RIGHT, underlay=[])])
    bare = generate(doc, load_profile("twill@1"))
    with_underlay = generate(
        design([_satin_object(STRAIGHT_LEFT, STRAIGHT_RIGHT)]), load_profile("twill@1")
    )
    assert bare.stitch_count() < with_underlay.stitch_count()


# --- as part of a design ----------------------------------------------------


def test_a_satin_object_generates_a_sewable_plan():
    plan = generate(design([_satin_object(STRAIGHT_LEFT, STRAIGHT_RIGHT)]))
    assert plan.stitch_count() > 100
    assert plan.stitches[-1].cmd is Cmd.END


def test_ties_go_round_the_object_not_round_every_layer():
    """An underlay layer is covered by what follows it; tying each one would
    leave knots under the top stitches."""
    profile = load_profile("twill@1")
    doc = design([_satin_object([(0.0, 0.0), (40.0, 0.0)], [(0.0, 6.0), (40.0, 6.0)])])
    plan = generate(doc, profile)
    owned = [s for s in plan.stitches if s.object_id == "obj_001"]
    ties = profile.stitch.tie_stitches
    # Two underlay layers plus the column: three paths, but only one tie pair.
    assert sum(1 for s in owned if s.cmd is Cmd.JUMP) >= 1
    assert plan.stitch_count() > ties * 2


def test_satin_generation_is_deterministic():
    doc = design([_satin_object(_arc(10.0), _arc(13.0))])
    assert generate(doc).model_dump_json() == generate(doc).model_dump_json()


def test_the_fabric_profile_changes_the_column():
    doc_twill = design([_satin_object(STRAIGHT_LEFT, STRAIGHT_RIGHT)], profile_ref="twill@1")
    doc_cap = design([_satin_object(STRAIGHT_LEFT, STRAIGHT_RIGHT)], profile_ref="cap@1")
    on_twill = generate(doc_twill, load_profile("twill@1"))
    on_cap = generate(doc_cap, load_profile("cap@1"))
    assert on_twill.stitch_count() != on_cap.stitch_count()


def test_underlay_runs_use_the_run_length_not_the_fill_length():
    """A satin's own stitch_length_mm defaults to the fill length, which would
    put 3.5 mm steps under a 2 mm column."""
    profile = load_profile("twill@1")
    plan = generate(design([_satin_object(STRAIGHT_LEFT, STRAIGHT_RIGHT)]), profile)
    boundary = _first_crossing_stitch(plan, 3.0)
    underlay_steps = [
        distance((a.x_mm, a.y_mm), (b.x_mm, b.y_mm))
        for a, b in zip(plan.stitches[:boundary], plan.stitches[1:boundary], strict=False)
        if a.cmd is Cmd.STITCH and b.cmd is Cmd.STITCH
    ]
    limit = profile.stitch.run_length_mm + 0.05
    over = [step for step in underlay_steps if step > limit]
    # One step is over: the edge run's turn from one rail across to the other.
    assert len(over) <= 1
    assert limit < profile.stitch.fill_length_mm


@pytest.mark.parametrize("profile_ref", ["twill@1", "pique@1", "cap@1"])
def test_nothing_a_satin_object_sews_exceeds_the_width_limit(profile_ref):
    """Underlay included. Being underneath does not make a floating stitch
    safe: it still has nothing holding its middle down. This caught the
    edge run's turn across a wide column, and the unsplit underlay zigzag."""
    profile = load_profile(profile_ref)
    doc = design(
        [_satin_object([(0.0, 0.0), (45.0, 0.0)], [(0.0, 8.0), (45.0, 8.0)])],
        profile_ref=profile_ref,
    )
    plan = generate(doc, profile)
    longest = max(
        distance((a.x_mm, a.y_mm), (b.x_mm, b.y_mm))
        for a, b in zip(plan.stitches, plan.stitches[1:], strict=False)
        if a.cmd is Cmd.STITCH and b.cmd is Cmd.STITCH
    )
    limit = profile.classification.satin_max_width_mm + 2 * profile.satin.split_overlap_mm
    assert longest <= limit


def test_an_edge_run_is_two_paths_not_one_crossing_stitch():
    """One path would put a stitch across the full column at the turn."""
    from engine.stitchgen.underlay import UnderlaySpec, edge_run

    spec = UnderlaySpec(
        inset_mm=0.3, run_length_mm=2.2, zigzag_spacing_mm=1.2, min_length_mm=0.5
    )
    paths = edge_run(rail_pairs([(0.0, 0.0), (40.0, 0.0)], [(0.0, 8.0), (40.0, 8.0)], 20), spec)
    assert len(paths) == 2
    assert all(abs(y - 0.3) < 0.01 for _, y in paths[0])
    assert all(abs(y - 7.7) < 0.01 for _, y in paths[1])


def test_a_wide_underlay_zigzag_is_split_like_the_column_above_it():
    from engine.stitchgen.underlay import UnderlaySpec, zigzag

    spec = UnderlaySpec(
        inset_mm=0.3,
        run_length_mm=2.2,
        zigzag_spacing_mm=1.2,
        min_length_mm=0.5,
        max_width_mm=7.0,
        split_overlap_mm=0.3,
    )
    pairs = rail_pairs([(0.0, 0.0), (40.0, 0.0)], [(0.0, 12.0), (40.0, 12.0)], 30)
    points = zigzag(pairs, spec)[0]
    assert max(_stitch_lengths(points)) <= 7.0 + 0.6
