"""Underlay.

The layer nobody sees and every good sew-out has. It stops the fabric moving
against the needle, flattens the nap so the top stitches sit on the surface
instead of sinking into it, and gives the satin something to hold onto.

Its second job is economic: a column on good underlay can be sewn more open
than one on bare fabric and still cover. Fewer stitches, less machine time, a
softer hand on the garment. Underlay is the reason a density number is a
choice rather than a floor.

Every recipe here is inset from the finished edge, so underlay can never peek
out past the top layer -- which reads as a shadow along the edge and is worse
than no underlay at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.stitchgen.geometry import (
    Point,
    distance,
    lerp,
    path_length,
    point_at,
    sample_evenly,
)
from engine.stitchgen.satin import split_lanes

CENTER_RUN = "center_run"
EDGE_RUN = "edge_run"
ZIGZAG = "zigzag"
TATAMI_LOW = "tatami_low"

SATIN_RECIPES = (CENTER_RUN, EDGE_RUN, ZIGZAG)


class UnknownUnderlay(NotImplementedError):
    """A recipe named in a profile that no generator implements."""


@dataclass(frozen=True)
class UnderlaySpec:
    """Underlay parameters, all resolved from the fabric profile."""

    inset_mm: float
    run_length_mm: float
    zigzag_spacing_mm: float
    min_length_mm: float
    max_width_mm: float = 0.0
    """The same column-width limit the top layer obeys. Being underneath does
    not make a floating stitch safe: it still has nothing holding its middle
    down, and it still ends up in the stitch count."""
    split_overlap_mm: float = 0.0


def _inset_pairs(
    pairs: list[tuple[Point, Point]], inset_mm: float
) -> list[tuple[Point, Point]]:
    """Pull both rails toward the centre by inset_mm.

    A column narrower than twice the inset collapses to its centreline rather
    than inverting, which would put the left rail on the right.
    """
    out = []
    for left, right in pairs:
        width = distance(left, right)
        if width == 0:
            out.append((left, right))
            continue
        fraction = min(inset_mm / width, 0.5)
        out.append((lerp(left, right, fraction), lerp(right, left, fraction)))
    return out


def _trim_ends(points: list[Point], inset_mm: float) -> list[Point]:
    """Shorten a path by inset_mm at each end, so it stays under the top layer."""
    total = path_length(points)
    if total <= 2 * inset_mm:
        return [point_at(points, total / 2)]
    inner = [point_at(points, inset_mm), point_at(points, total - inset_mm)]
    middle = [
        point
        for point, length in zip(points, _cumulative(points), strict=True)
        if inset_mm < length < total - inset_mm
    ]
    return [inner[0], *middle, inner[1]]


def _cumulative(points: list[Point]) -> list[float]:
    from engine.stitchgen.geometry import cumulative_lengths

    return cumulative_lengths(points)


def _resample(points: list[Point], step_mm: float) -> list[Point]:
    """Resample a path, keeping its corners.

    Spacing purely by arc length would drop the original vertices, and the
    path would cut across every corner. On a ring around a hole that chord
    goes straight through the hole, which is how an underlay ends up stitching
    a window shut.
    """
    from engine.stitchgen.run import resample as corner_preserving

    total = path_length(points)
    if total == 0 or step_mm <= 0:
        return points
    return corner_preserving(
        points, closed=False, target_length_mm=step_mm, max_length_mm=step_mm
    )


def center_run(pairs: list[tuple[Point, Point]], spec: UnderlaySpec) -> list[list[Point]]:
    """A single line down the middle.

    All a narrow column needs: anything heavier under a 1.5 mm satin shows
    through it as a ridge.
    """
    centre = [lerp(left, right, 0.5) for left, right in pairs]
    return [_resample(_trim_ends(centre, spec.inset_mm), spec.run_length_mm)]


def edge_run(pairs: list[tuple[Point, Point]], spec: UnderlaySpec) -> list[list[Point]]:
    """A line inside each rail, sewn down one side and back up the other.

    This is what holds a satin edge straight. Without it the first and last
    penetrations of each stitch sit on unsupported fabric and the edge wanders.

    The two rails are separate paths, not one path with a stitch across the
    turn. On a wide column that crossing stitch would span the whole width
    with nothing holding it down -- the exact thing the width limit exists to
    prevent. Left as two paths, the plan travels between them like any other
    gap, which is also how a digitizer sews it.
    """
    inset = _inset_pairs(pairs, spec.inset_mm)
    left = _resample(_trim_ends([pair[0] for pair in inset], spec.inset_mm), spec.run_length_mm)
    right = _resample(_trim_ends([pair[1] for pair in inset], spec.inset_mm), spec.run_length_mm)
    return [left, list(reversed(right))]


def zigzag(pairs: list[tuple[Point, Point]], spec: UnderlaySpec) -> list[list[Point]]:
    """An open zigzag across the column.

    For wide columns and for fabrics whose weave the top layer would otherwise
    sink into. Open on purpose: it supports, it does not cover.
    """
    inset = _inset_pairs(pairs, spec.inset_mm)
    trimmed_left = _trim_ends([pair[0] for pair in inset], spec.inset_mm)
    trimmed_right = _trim_ends([pair[1] for pair in inset], spec.inset_mm)

    length = max(path_length(trimmed_left), path_length(trimmed_right))
    count = max(2, round(length / spec.zigzag_spacing_mm) + 1)
    zigzag_pairs = list(
        zip(sample_evenly(trimmed_left, count), sample_evenly(trimmed_right, count), strict=True)
    )

    lanes = (
        split_lanes(zigzag_pairs, spec.max_width_mm, spec.split_overlap_mm)
        if spec.max_width_mm > 0
        else [zigzag_pairs]
    )

    points: list[Point] = []
    for lane_index, lane in enumerate(lanes):
        ordered = lane if lane_index % 2 == 0 else list(reversed(lane))
        for index, (rail_left, rail_right) in enumerate(ordered):
            points += [rail_left, rail_right] if index % 2 == 0 else [rail_right, rail_left]
    return [points]


def satin_underlay(
    recipe: list[str], pairs: list[tuple[Point, Point]], spec: UnderlaySpec
) -> list[list[Point]]:
    """Build every layer in a recipe, in the order the profile lists them."""
    layers: list[list[Point]] = []
    for name in recipe:
        if name == CENTER_RUN:
            layers += center_run(pairs, spec)
        elif name == EDGE_RUN:
            layers += edge_run(pairs, spec)
        elif name == ZIGZAG:
            layers += zigzag(pairs, spec)
        elif name == TATAMI_LOW:
            raise UnknownUnderlay(
                "tatami_low underlay is for fills, which land with the fill generator (M1)"
            )
        else:
            raise UnknownUnderlay(
                f"no generator for underlay {name!r}; satin recipes are {list(SATIN_RECIPES)}"
            )
    return [layer for layer in layers if len(layer) >= 2]


@dataclass(frozen=True)
class FillUnderlaySpec:
    """Underlay parameters for an area fill."""

    inset_mm: float
    run_length_mm: float
    tatami_spacing_mm: float
    tatami_angle_deg: float
    stagger_steps: int
    min_length_mm: float
    min_span_mm: float


def fill_edge_run(
    outer: list[Point], holes: list[list[Point]], spec: FillUnderlaySpec
) -> list[list[Point]]:
    """A run just inside the outline, and just outside every hole.

    It is what holds the fill's edge where it was drawn. Each ring is its own
    path: a fill with holes has boundaries that are genuinely separate, and
    joining them would drag thread across the middle of the shape.
    """
    from engine.stitchgen.offset import inset_shape

    inset_outer, grown_holes = inset_shape(outer, holes, spec.inset_mm)
    paths = []
    for ring in [*inset_outer, *grown_holes]:
        closed = ring if ring[0] == ring[-1] else [*ring, ring[0]]
        paths.append(_resample(closed, spec.run_length_mm))
    return paths


def fill_tatami_low(
    outer: list[Point], holes: list[list[Point]], spec: FillUnderlaySpec
) -> list[list[Point]]:
    """A very open fill, crossing the top layer's angle.

    Crossing is what makes it support rather than add: rows at the same angle
    as the layer above would sit in the same valleys and do nothing. This is
    the layer that lets the top fill be sewn more open and still cover.
    """
    from engine.stitchgen.fill import FillSpec, stitch_fill
    from engine.stitchgen.offset import inset_shape

    inset_outer, grown_holes = inset_shape(outer, holes, spec.inset_mm)
    if not inset_outer:
        return []

    fill_spec = FillSpec(
        row_spacing_mm=spec.tatami_spacing_mm,
        stitch_length_mm=spec.run_length_mm,
        min_length_mm=spec.min_length_mm,
        angle_deg=spec.tatami_angle_deg,
        stagger_steps=spec.stagger_steps,
        pull_comp_mm_per_side=0.0,
        push_comp_mm=0.0,
        min_span_mm=spec.min_span_mm,
    )
    paths = []
    for ring in inset_outer:
        paths += stitch_fill(ring, grown_holes, fill_spec)
    return paths


def fill_underlay(
    recipe: list[str],
    outer: list[Point],
    holes: list[list[Point]],
    spec: FillUnderlaySpec,
) -> list[list[Point]]:
    """Build every layer in a fill's recipe, in the order the profile lists it."""
    layers: list[list[Point]] = []
    for name in recipe:
        if name == EDGE_RUN:
            layers += fill_edge_run(outer, holes, spec)
        elif name == TATAMI_LOW:
            layers += fill_tatami_low(outer, holes, spec)
        elif name in (CENTER_RUN, ZIGZAG):
            raise UnknownUnderlay(
                f"{name!r} is a satin underlay; a fill takes {EDGE_RUN} and {TATAMI_LOW}"
            )
        else:
            raise UnknownUnderlay(f"no generator for underlay {name!r}")
    return [layer for layer in layers if len(layer) >= 2]
