"""Tatami fill: covering an area without cutting the fabric along a line."""

from __future__ import annotations

import math

import pytest
from conftest import BLACK, design

from engine.ir.schema import EmbroideryObject, FillShape, ObjectKind, ObjectParams
from engine.plan import Cmd
from engine.profiles.loader import load_profile
from engine.stitchgen import generate
from engine.stitchgen.fill import FillSpec, row_positions, scanline_spans, sections, stitch_fill
from engine.stitchgen.geometry import distance

SQUARE = [(0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (0.0, 30.0)]
HOLE = [(10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0)]


def _spec(**overrides) -> FillSpec:
    base = {
        "row_spacing_mm": 0.4,
        "stitch_length_mm": 3.5,
        "min_length_mm": 0.5,
        "angle_deg": 0.0,
        "stagger_steps": 4,
        "pull_comp_mm_per_side": 0.0,
        "push_comp_mm": 0.0,
        "min_span_mm": 1.0,
    }
    base.update(overrides)
    return FillSpec(**base)


def _fill_object(outer=None, holes=None, object_id="obj_001", **params) -> EmbroideryObject:
    return EmbroideryObject(
        id=object_id,
        kind=ObjectKind.FILL,
        shape=FillShape(outer=outer or SQUARE, holes=holes or []),
        thread=BLACK,
        params=ObjectParams(**params),
    )


def _inside(point, ring) -> bool:
    """Even-odd point in polygon, for asserting where stitches are not."""
    x, y = point
    inside = False
    closed = [*ring, ring[0]]
    for (x1, y1), (x2, y2) in zip(closed, closed[1:], strict=False):
        if (y1 > y) != (y2 > y):
            crossing = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < crossing:
                inside = not inside
    return inside


def _stitch_points(plan):
    return [(s.x_mm, s.y_mm) for s in plan.stitches if s.cmd is Cmd.STITCH]


def _stitch_segments(plan):
    """Consecutive pairs that are actually one stitch.

    Filtering to stitches first and then pairing them up would treat the two
    ends of a jump as a stitch, which is how a travel gets mistaken for thread
    on the fabric.
    """
    return [
        ((a.x_mm, a.y_mm), (b.x_mm, b.y_mm))
        for a, b in zip(plan.stitches, plan.stitches[1:], strict=False)
        if a.cmd is Cmd.STITCH and b.cmd is Cmd.STITCH
    ]


# --- the scanline machinery -------------------------------------------------


def test_a_scanline_across_a_square_is_one_span():
    assert scanline_spans([SQUARE], 15.0) == [(0.0, 30.0)]


def test_a_scanline_across_a_hole_is_two_spans():
    """A hole's crossings close the span the outline opened."""
    spans = scanline_spans([SQUARE, HOLE], 15.0)
    assert spans == [(0.0, 10.0), (20.0, 30.0)]


def test_a_scanline_below_the_hole_is_still_one_span():
    assert scanline_spans([SQUARE, HOLE], 5.0) == [(0.0, 30.0)]


def test_a_vertex_exactly_on_the_scanline_is_not_counted_twice():
    """Counted twice, the span inverts and the row sews across bare fabric."""
    diamond = [(0.0, 0.0), (10.0, 10.0), (0.0, 20.0), (-10.0, 10.0)]
    assert len(scanline_spans([diamond], 10.0)) == 1


def test_rows_sit_at_the_spacing():
    positions = row_positions([SQUARE], 0.4, 0.0)
    steps = [b - a for a, b in zip(positions, positions[1:], strict=False)]
    assert all(abs(step - 0.4) < 1e-9 for step in steps)


def test_push_compensation_trims_the_fill_across_the_rows():
    """A fill pushes the fabric out across the rows, so it is drawn short there."""
    plain = row_positions([SQUARE], 0.4, 0.0)
    trimmed = row_positions([SQUARE], 0.4, 0.5)
    assert min(trimmed) > min(plain)
    assert max(trimmed) < max(plain)


def test_a_shape_thinner_than_the_compensation_gets_no_rows():
    sliver = [(0.0, 0.0), (30.0, 0.0), (30.0, 0.2), (0.0, 0.2)]
    assert row_positions([sliver], 0.4, 0.5) == []


# --- sections ---------------------------------------------------------------


def test_a_simple_shape_is_one_section():
    rows = [(float(y), [(0.0, 30.0)]) for y in range(10)]
    assert len(sections(rows)) == 1


def test_a_shape_that_splits_in_two_closes_its_section():
    """Sewing a split shape as one section would jump on every row."""
    rows = [(0.0, [(0.0, 30.0)]), (1.0, [(0.0, 30.0)]), (2.0, [(0.0, 10.0), (20.0, 30.0)])]
    assert len(sections(rows)) == 3


def test_two_parts_that_merge_close_their_sections():
    rows = [(0.0, [(0.0, 10.0), (20.0, 30.0)]), (1.0, [(0.0, 10.0), (20.0, 30.0)]),
            (2.0, [(0.0, 30.0)])]
    assert len(sections(rows)) == 3


def test_every_row_ends_up_in_exactly_one_section():
    rows = [(0.0, [(0.0, 30.0)]), (1.0, [(0.0, 10.0), (20.0, 30.0)]), (2.0, [(0.0, 30.0)])]
    placed = sum(len(section) for section in sections(rows))
    assert placed == sum(len(spans) for _, spans in rows)


# --- the fill itself --------------------------------------------------------


def test_a_square_fills_as_one_path():
    paths = stitch_fill(SQUARE, [], _spec())
    assert len(paths) == 1
    assert len(paths[0]) > 100


def test_the_fill_covers_the_shape():
    points = [point for path in stitch_fill(SQUARE, [], _spec()) for point in path]
    assert min(x for x, _ in points) == pytest.approx(0.0, abs=0.01)
    assert max(x for x, _ in points) == pytest.approx(30.0, abs=0.01)
    assert min(y for _, y in points) == pytest.approx(0.0, abs=0.5)
    assert max(y for _, y in points) == pytest.approx(30.0, abs=0.5)


def test_no_stitch_crosses_a_hole():
    """The failure this catches sews a window shut, and is invisible until the
    garment is in front of you."""
    plan = generate(design([_fill_object(holes=[HOLE])]), load_profile("twill@1"))
    for a, b in _stitch_segments(plan):
        for step in (0.25, 0.5, 0.75):
            midpoint = (a[0] + (b[0] - a[0]) * step, a[1] + (b[1] - a[1]) * step)
            assert not _inside(midpoint, HOLE), f"stitch {a} -> {b} crosses the hole"


def test_rows_do_not_line_up():
    """Penetrations stacked in a column cut the fabric along that line."""
    paths = stitch_fill(SQUARE, [], _spec(stagger_steps=4))
    interior = [point for point in paths[0] if 1.0 < point[0] < 29.0]
    rows: dict[float, list[float]] = {}
    for x, y in interior:
        rows.setdefault(round(y, 4), []).append(x)
    ordered = [rows[key] for key in sorted(rows)][:8]
    offsets = {round(min(row) % 3.5, 3) for row in ordered if row}
    assert len(offsets) > 1


def test_turning_stagger_off_lines_the_rows_up():
    """The control for the test above: without stagger they do line up."""
    paths = stitch_fill(SQUARE, [], _spec(stagger_steps=1))
    interior = [point for point in paths[0] if 1.0 < point[0] < 29.0]
    rows: dict[float, list[float]] = {}
    for x, y in interior:
        rows.setdefault(round(y, 4), []).append(x)
    ordered = [rows[key] for key in sorted(rows)][:8]
    offsets = {round(min(row) % 3.5, 3) for row in ordered if row}
    assert len(offsets) == 1


def test_no_stitch_exceeds_the_target_length():
    paths = stitch_fill(SQUARE, [], _spec(stitch_length_mm=3.5))
    for path in paths:
        lengths = [distance(a, b) for a, b in zip(path, path[1:], strict=False)]
        assert max(lengths) <= 3.5 + 0.01


def test_the_angle_turns_the_rows():
    flat = stitch_fill(SQUARE, [], _spec(angle_deg=0.0))[0]
    angled = stitch_fill(SQUARE, [], _spec(angle_deg=45.0))[0]
    assert flat[0][1] == pytest.approx(flat[1][1], abs=0.01)
    assert angled[0][1] != pytest.approx(angled[1][1], abs=0.01)


def test_a_denser_fill_puts_down_more_stitches():
    open_fill = sum(len(path) for path in stitch_fill(SQUARE, [], _spec(row_spacing_mm=0.6)))
    dense = sum(len(path) for path in stitch_fill(SQUARE, [], _spec(row_spacing_mm=0.3)))
    assert dense > open_fill


def test_pull_compensation_extends_the_rows():
    plain = stitch_fill(SQUARE, [], _spec(pull_comp_mm_per_side=0.0))[0]
    compensated = stitch_fill(SQUARE, [], _spec(pull_comp_mm_per_side=0.3))[0]
    assert min(x for x, _ in compensated) < min(x for x, _ in plain)
    assert max(x for x, _ in compensated) > max(x for x, _ in plain)


def test_a_span_too_narrow_to_hold_a_stitch_is_left_alone():
    """A stub in a 0.5 mm sliver is a thread break, not coverage."""
    wedge = [(0.0, 0.0), (30.0, 0.0), (30.0, 30.0)]
    paths = stitch_fill(wedge, [], _spec(min_span_mm=2.0))
    for path in paths:
        rows: dict[float, list[float]] = {}
        for x, y in path:
            rows.setdefault(round(y, 4), []).append(x)
        for row in rows.values():
            assert max(row) - min(row) >= 2.0 - 0.01


def test_fill_generation_is_deterministic():
    doc = design([_fill_object(holes=[HOLE])])
    assert generate(doc).model_dump_json() == generate(doc).model_dump_json()


# --- as part of a design ----------------------------------------------------


def test_a_fill_object_generates_a_sewable_plan():
    profile = load_profile("twill@1")
    plan = generate(design([_fill_object()]), profile)
    assert plan.stitch_count() > 500
    lengths = [distance(a, b) for a, b in _stitch_segments(plan)]
    assert max(lengths) <= profile.stitch.max_length_mm
    # The floor applies within a row. The turn from one row to the next is
    # about one row spacing long by construction -- shorter where the boundary
    # runs diagonally to the rows -- and is structural, not a stub.
    assert min(lengths) >= profile.density.fill_row_spacing_mm * 0.75


def test_a_fill_gets_underlay_from_the_profile():
    with_underlay = generate(design([_fill_object()]), load_profile("twill@1"))
    bare = generate(design([_fill_object(underlay=[])]), load_profile("twill@1"))
    assert with_underlay.stitch_count() > bare.stitch_count()


def test_the_underlay_crosses_the_top_layer():
    """Rows at the same angle as the layer above sit in the same valleys and
    support nothing."""
    profile = load_profile("twill@1")
    assert profile.underlay.tatami_angle_offset_deg != 0


def test_satin_underlay_recipes_are_refused_for_a_fill():
    from engine.stitchgen.underlay import UnknownUnderlay

    with pytest.raises(UnknownUnderlay, match="satin underlay"):
        generate(design([_fill_object(underlay=["center_run"])]), load_profile("twill@1"))


def test_an_object_can_set_its_own_fill_angle():
    default_angle = generate(design([_fill_object()]), load_profile("twill@1"))
    turned = generate(design([_fill_object(angle_deg=0.0)]), load_profile("twill@1"))
    assert default_angle.model_dump_json() != turned.model_dump_json()


@pytest.mark.parametrize("profile_ref", ["twill@1", "pique@1", "cap@1"])
def test_fill_works_on_every_shipped_profile(profile_ref):
    doc = design([_fill_object(holes=[HOLE])], profile_ref=profile_ref)
    plan = generate(doc, load_profile(profile_ref))
    assert plan.stitch_count() > 400


def test_a_shape_that_splits_sews_as_separate_paths():
    """A U-shape: the two arms cannot be reached without travel."""
    u_shape = [
        (0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (22.0, 30.0),
        (22.0, 10.0), (8.0, 10.0), (8.0, 30.0), (0.0, 30.0),
    ]
    paths = stitch_fill(u_shape, [], _spec(angle_deg=0.0))
    assert len(paths) >= 3


def test_the_fill_angle_default_comes_from_the_profile():
    profile = load_profile("twill@1")
    assert profile.fill.default_angle_deg == 45.0
    plan = generate(design([_fill_object()]), profile)
    # At 45 degrees, a row advances equally in x and y.
    # The longest stitches in the plan are full-length fill rows, and at 45
    # degrees a row advances equally in x and y.
    longest = sorted(_stitch_segments(plan), key=lambda seg: -distance(*seg))[:20]
    angles = {
        round(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180, 0) for a, b in longest
    }
    assert angles == {45.0}


def test_a_row_turn_is_kept_even_though_it_is_shorter_than_the_stitch_floor():
    """The turn from one row to the next is one row spacing long. Filtering it
    as a short stitch deletes one end of every other row, and the fill stops
    reaching its own edge."""
    spec = _spec(row_spacing_mm=0.4, min_length_mm=0.5)
    path = stitch_fill(SQUARE, [], spec)[0]
    rows: dict[float, list[float]] = {}
    for x, y in path:
        rows.setdefault(round(y, 4), []).append(x)
    for row in rows.values():
        assert max(row) == pytest.approx(30.0, abs=0.01)
        assert min(row) == pytest.approx(0.0, abs=0.01)


def test_a_stagger_stub_is_respread_not_merged():
    """Dropping the offending penetration would merge two stitches into one
    longer than the target."""
    for stagger in (1, 2, 3, 4, 5):
        path = stitch_fill(SQUARE, [], _spec(stagger_steps=stagger))[0]
        lengths = [distance(a, b) for a, b in zip(path, path[1:], strict=False)]
        assert max(lengths) <= 3.5 + 0.01, stagger


def test_a_turn_across_a_narrow_overlap_is_subdivided():
    """Where two rows overlap only slightly, the turn travels most of a row's
    width. Left as one stitch it would be far over the machine's limit, and
    the writer would silently split it into penetrations we never planned."""
    stepped = [
        (0.0, 0.0), (40.0, 0.0), (40.0, 8.0), (8.0, 8.0), (8.0, 16.0), (0.0, 16.0),
    ]
    paths = stitch_fill(stepped, [], _spec(angle_deg=0.0, stitch_length_mm=3.5))
    for path in paths:
        lengths = [distance(a, b) for a, b in zip(path, path[1:], strict=False)]
        assert max(lengths) <= 3.5 + 0.01


def test_a_hole_stays_bare():
    """Scanline sampling clips a hole's corner by up to half a row spacing.
    A window is not the place to spend that tolerance, so holes are grown by
    the profile's clearance before anything is generated."""
    plan = generate(design([_fill_object(holes=[HOLE])]), load_profile("twill@1"))
    for a, b in _stitch_segments(plan):
        for step in range(1, 20):
            fraction = step / 20
            point = (a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction)
            assert not _inside(point, HOLE)
