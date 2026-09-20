"""Satin columns.

A satin is a zigzag between two rails: every stitch crosses the column, and
consecutive stitches advance along it by the density spacing. It is what makes
lettering and borders read as solid, and it is where most of the ways a file
can ruin a garment live.

Four of those ways are handled here:

* **Pull.** The thread pulls the fabric in along the stitch direction, so a
  column sews narrower than it was drawn. Compensation widens it per side
  before the stitches are placed.
* **Crowding on curves.** A column following a curve crowds its inner rail.
  Left alone, the penetrations pile into one hole: thread break, then needle
  break. Short stitches relieve it.
* **Columns too wide to hold.** A long unsupported stitch snags and loops.
  Past the profile's maximum width a column is split into lanes.
* **Nothing underneath.** A satin on bare fabric sinks and shifts. Underlay is
  generated separately (engine.stitchgen.underlay) and sewn first.

Rails arrive already paired, left and right, running the same direction.
Deriving them from an outline is the medial-axis work in M3; this module takes
them as given, which is exactly what the IR holds.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.stitchgen.geometry import (
    Point,
    distance,
    extend,
    lerp,
    path_length,
    sample_evenly,
    unit_vector,
)


@dataclass(frozen=True)
class SatinSpec:
    """Everything a satin column needs, all of it resolved from the profile."""

    spacing_mm: float
    """Distance between penetrations on the same side."""
    pull_comp_mm_per_side: float
    max_width_mm: float
    short_stitch: bool
    short_stitch_min_spacing_mm: float
    short_stitch_depth: float
    split_overlap_mm: float
    min_length_mm: float


def rail_pairs(left: list[Point], right: list[Point], count: int) -> list[tuple[Point, Point]]:
    """Pair the two rails at `count` positions, evenly by arc length.

    Sampling by arc length rather than by vertex index is what keeps the
    stitches perpendicular when the two rails have different numbers of
    points, or different lengths -- which is the normal case on any curve.
    """
    return list(
        zip(sample_evenly(left, count), sample_evenly(right, count), strict=True)
    )


def sample_count(left: list[Point], right: list[Point], spacing_mm: float) -> int:
    """How many stitch pairs a column of this length takes.

    Measured on the longer rail: spacing the outer edge correctly leaves the
    inner edge crowded (which short stitches then relieve), while spacing the
    inner edge correctly leaves visible gaps on the outside.
    """
    if spacing_mm <= 0:
        raise ValueError("satin spacing must be positive")
    length = max(path_length(left), path_length(right))
    return max(2, round(length / spacing_mm) + 1)


def compensate(pair: tuple[Point, Point], amount_mm: float) -> tuple[Point, Point]:
    """Widen one stitch by `amount_mm` on each side, along the stitch itself.

    Per side, along stitch direction -- the convention the IR documents. A
    column drawn 2 mm wide with 0.2 mm per side is stitched 2.4 mm wide, and
    sews at roughly 2 mm once the fabric has drawn in.
    """
    left, right = pair
    if amount_mm == 0 or distance(left, right) == 0:
        return pair
    direction = unit_vector(left, right)
    return (
        extend(left, direction, -amount_mm),
        extend(right, direction, amount_mm),
    )


def split_lanes(
    pairs: list[tuple[Point, Point]], max_width_mm: float, overlap_mm: float
) -> list[list[tuple[Point, Point]]]:
    """Divide a column too wide to sew into lanes that are not.

    A single stitch longer than the profile's maximum has nothing holding its
    middle down: it snags on anything the garment touches and pulls into a
    loop. Lanes overlap slightly so the seam between them does not read as a
    line of bare fabric.
    """
    widest = max(distance(left, right) for left, right in pairs)
    if widest <= max_width_mm:
        return [pairs]

    lanes = int(widest / max_width_mm) + 1
    out: list[list[tuple[Point, Point]]] = []
    for index in range(lanes):
        start = index / lanes
        end = (index + 1) / lanes
        lane: list[tuple[Point, Point]] = []
        for left, right in pairs:
            width = distance(left, right)
            margin = (overlap_mm / width) if width else 0.0
            lane_start = max(0.0, start - (margin if index else 0.0))
            lane_end = min(1.0, end + (margin if index < lanes - 1 else 0.0))
            lane.append((lerp(left, right, lane_start), lerp(left, right, lane_end)))
        out.append(lane)
    return out


def _inner_side(pairs: list[tuple[Point, Point]], index: int) -> int | None:
    """Which rail is crowded at this stitch: 0 for left, 1 for right, None if
    neither. The crowded side is the one whose neighbours are closer together."""
    if index == 0 or index >= len(pairs) - 1:
        return None
    left_span = distance(pairs[index - 1][0], pairs[index + 1][0])
    right_span = distance(pairs[index - 1][1], pairs[index + 1][1])
    if left_span == right_span:
        return None
    return 0 if left_span < right_span else 1


def apply_short_stitches(
    pairs: list[tuple[Point, Point]], spec: SatinSpec
) -> list[tuple[Point, Point]]:
    """Shorten every other stitch on a crowded inner rail.

    Only alternate stitches are shortened: shortening all of them would move
    the edge inward and read as a notch. Alternating keeps the edge where it
    was drawn while halving the penetrations going into the crowded spot.
    """
    if not spec.short_stitch:
        return pairs

    out = list(pairs)
    for index in range(1, len(pairs) - 1):
        side = _inner_side(pairs, index)
        if side is None:
            continue
        neighbour_gap = distance(pairs[index - 1][side], pairs[index][side])
        if neighbour_gap >= spec.short_stitch_min_spacing_mm:
            continue
        if index % 2:
            continue
        left, right = out[index]
        if side == 0:
            out[index] = (lerp(right, left, spec.short_stitch_depth), right)
        else:
            out[index] = (left, lerp(left, right, spec.short_stitch_depth))
    return out


def stitch_satin(left: list[Point], right: list[Point], spec: SatinSpec) -> list[Point]:
    """Generate the penetrations for one satin column, in sew order.

    Lanes of a split column are sewn boustrophedon -- the second lane runs back
    the way the first came -- so the machine never travels the length of the
    column with nothing to show for it.
    """
    pairs = rail_pairs(left, right, sample_count(left, right, spec.spacing_mm))
    pairs = [compensate(pair, spec.pull_comp_mm_per_side) for pair in pairs]
    pairs = apply_short_stitches(pairs, spec)

    points: list[Point] = []
    for index, lane in enumerate(split_lanes(pairs, spec.max_width_mm, spec.split_overlap_mm)):
        ordered = lane if index % 2 == 0 else list(reversed(lane))
        for lane_left, lane_right in ordered:
            # Every stitch crosses the column: left, right, next left, next
            # right. Alternating the pair order instead would put a stitch
            # along a rail, which sews as a visible line down the edge.
            points += [lane_left, lane_right]

    return _drop_repeats(points, spec.min_length_mm)


def _drop_repeats(points: list[Point], min_length_mm: float) -> list[Point]:
    """Remove penetrations that land on top of the previous one.

    A zero-width point on a rail that pinches, or two samples that round to the
    same place, would otherwise put two stitches in one hole.
    """
    if not points:
        return points
    kept = [points[0]]
    for point in points[1:]:
        if distance(kept[-1], point) >= min_length_mm:
            kept.append(point)
    return kept
