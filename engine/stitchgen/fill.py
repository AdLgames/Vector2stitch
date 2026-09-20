"""Tatami fill.

A fill covers an area with rows of stitching. Getting it right is mostly about
what the rows do at their edges and where their penetrations land:

* **Rows must not line up.** Penetrations stacked in a column across rows cut
  the fabric along that line and read as a visible seam through the fill.
  Staggering shifts each row's penetrations along by a fraction of a stitch.
* **The area must be covered in one pass where it can be.** Sewing a shape as
  disconnected rows leaves a jump between every pair. Rows are grouped into
  sections that sew continuously -- down one row, back the next -- and only the
  section boundaries need travel.
* **Holes are holes.** A ring inside the shape is not stitched across, which
  means intersecting every scanline with every ring, not just the outline.
* **Compensation applies along the stitch.** Rows are extended at their ends
  by the pull compensation, and the fill is trimmed across the rows by the
  push compensation, because a fill pushes the fabric out that way.

Angles are in degrees, counter-clockwise, and everything is rotated so the
scanlines are horizontal before any of it happens.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from engine.stitchgen.geometry import Point, distance

Ring = list[Point]
Span = tuple[float, float]


@dataclass(frozen=True)
class FillSpec:
    """Everything a fill needs, all of it resolved from the profile."""

    row_spacing_mm: float
    stitch_length_mm: float
    min_length_mm: float
    angle_deg: float
    stagger_steps: int
    pull_comp_mm_per_side: float
    push_comp_mm: float
    min_span_mm: float
    """A span narrower than this cannot hold a stitch; it is left to the
    outline or the satin that borders it rather than sewn as a stub."""


def rotate(point: Point, radians: float) -> Point:
    cos, sin = math.cos(radians), math.sin(radians)
    return (point[0] * cos - point[1] * sin, point[0] * sin + point[1] * cos)


def rotate_ring(ring: Ring, radians: float) -> Ring:
    return [rotate(point, radians) for point in ring]


def row_positions(rings: list[Ring], spacing_mm: float, push_comp_mm: float) -> list[float]:
    """The y of each scanline, in rotated space.

    Rows start half a spacing inside the shape so the first and last rows sit
    inside the edge rather than on it, and the range is trimmed by the push
    compensation: a fill pushes the fabric outward across the rows, so it is
    drawn slightly short there to come back to size.
    """
    if spacing_mm <= 0:
        raise ValueError("fill row spacing must be positive")
    ys = [point[1] for ring in rings for point in ring]
    low = min(ys) + push_comp_mm
    high = max(ys) - push_comp_mm
    if high <= low:
        return []

    positions = []
    y = low + spacing_mm / 2
    while y < high:
        positions.append(y)
        y += spacing_mm
    return positions


def scanline_spans(rings: list[Ring], y: float) -> list[Span]:
    """Where a horizontal line at `y` is inside the shape.

    Even-odd: crossings are sorted and paired, so a hole's two crossings close
    the span the outline opened. Each edge is treated as half-open in y, which
    is what stops a vertex exactly on the scanline being counted twice.
    """
    crossings: list[float] = []
    for ring in rings:
        closed = ring if ring[0] == ring[-1] else [*ring, ring[0]]
        for (x1, y1), (x2, y2) in zip(closed, closed[1:], strict=False):
            if y1 == y2:
                continue
            if (y1 <= y < y2) or (y2 <= y < y1):
                crossings.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    crossings.sort()
    return [
        (crossings[index], crossings[index + 1]) for index in range(0, len(crossings) - 1, 2)
    ]


def _overlaps(a: Span, b: Span) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def sections(rows: list[tuple[float, list[Span]]]) -> list[list[tuple[float, Span]]]:
    """Group rows into runs that can be sewn without jumping.

    A section continues while each span has exactly one span above it and one
    below. Where the shape splits in two or two parts merge, the affected
    sections close and new ones open -- which is the boustrophedon
    decomposition, and the reason a U-shape sews as three sections rather than
    as one with a jump on every row.
    """
    open_sections: list[list[tuple[float, Span]]] = []
    open_spans: list[Span] = []
    done: list[list[tuple[float, Span]]] = []

    for y, spans in rows:
        matches = {
            index: [span for span in spans if _overlaps(open_span, span)]
            for index, open_span in enumerate(open_spans)
        }
        claimed = {
            id(span): sum(1 for found in matches.values() if any(s is span for s in found))
            for span in spans
        }

        next_sections: list[list[tuple[float, Span]]] = []
        next_spans: list[Span] = []
        continued: set[int] = set()

        for index, section in enumerate(open_sections):
            found = matches[index]
            if len(found) == 1 and claimed[id(found[0])] == 1:
                section.append((y, found[0]))
                next_sections.append(section)
                next_spans.append(found[0])
                continued.add(id(found[0]))
            else:
                done.append(section)

        for span in spans:
            if id(span) not in continued:
                next_sections.append([(y, span)])
                next_spans.append(span)

        open_sections, open_spans = next_sections, next_spans

    done.extend(open_sections)
    return [section for section in done if section]


def row_points(
    span: Span, y: float, row_index: int, spec: FillSpec, reverse: bool
) -> list[Point]:
    """Penetrations along one row, staggered so rows do not line up."""
    start, end = span
    start -= spec.pull_comp_mm_per_side
    end += spec.pull_comp_mm_per_side
    length = end - start
    if length <= 0:
        return []

    offset = 0.0
    if spec.stagger_steps > 1:
        offset = (row_index % spec.stagger_steps) / spec.stagger_steps * spec.stitch_length_mm

    positions = [start]
    position = start + offset
    if position <= start:
        position += spec.stitch_length_mm
    while position < end:
        positions.append(position)
        position += spec.stitch_length_mm
    positions.append(end)

    # A stagger offset can leave a stub against either end of the row. Dropping
    # the offending penetration would merge two stitches into one longer than
    # the target, so the pair is re-spread instead: both halves stay under the
    # target and over the floor.
    if len(positions) > 2 and positions[-1] - positions[-2] < spec.min_length_mm:
        positions[-2:] = _respread(positions[-3], positions[-1], spec)
    if len(positions) > 2 and positions[1] - positions[0] < spec.min_length_mm:
        positions[:2] = _respread(positions[0], positions[2], spec)[:-1] + [positions[0]]
        positions[:2] = sorted(positions[:2])

    points = [(x, y) for x in positions]
    return list(reversed(points)) if reverse else points


def _turn(
    end_of_row: Point,
    start_of_next: Point,
    span: Span,
    next_span: Span,
    spec: FillSpec,
) -> list[Point]:
    """Get from one row to the next without cutting a corner.

    Going straight from the end of one row to the start of the next draws a
    diagonal, and where the shape's boundary turns -- the corner of a hole, the
    point of a wedge -- that diagonal leaves the shape. On a hole it stitches
    across the window.

    Instead the turn moves along the current row first, to an x that is inside
    both rows, and only then crosses to the next one. Sections guarantee the
    two spans overlap, so such an x always exists.
    """
    if abs(end_of_row[0] - start_of_next[0]) < spec.min_length_mm:
        # Below the stitch floor the diagonal is shorter than a stitch, and
        # inserting a point would only put two penetrations in one hole.
        return []

    target = start_of_next[0]
    if not (span[0] - 1e-9 <= target <= span[1] + 1e-9):
        target = end_of_row[0]
        if not (next_span[0] - 1e-9 <= target <= next_span[1] + 1e-9):
            target = max(span[0], next_span[0])

    # The turn travels along the current row, which can be most of its width
    # where two rows overlap only slightly. It lays thread like any other
    # stitching, so it is subdivided at the stitch length rather than left as
    # one long stitch the machine would have to split itself.
    y = end_of_row[1]
    span_mm = target - end_of_row[0]
    steps = max(1, math.ceil(round(abs(span_mm) / spec.stitch_length_mm, 9)))
    return [(end_of_row[0] + span_mm * step / steps, y) for step in range(1, steps + 1)]


def _respread(start: float, end: float, spec: FillSpec) -> list[float]:
    """Replace a too-short final gap with one or two even ones."""
    span = end - start
    if span <= spec.stitch_length_mm:
        return [end]
    return [start + span / 2, end]


def stitch_fill(outer: Ring, holes: list[Ring], spec: FillSpec) -> list[list[Point]]:
    """Generate a fill as a list of paths, one per section.

    Travel between sections is the plan assembler's problem, the same as travel
    between objects -- which keeps the decision about trimming in one place.
    """
    radians = math.radians(spec.angle_deg)
    rings = [rotate_ring(outer, -radians), *(rotate_ring(hole, -radians) for hole in holes)]

    rows = []
    for y in row_positions(rings, spec.row_spacing_mm, spec.push_comp_mm):
        spans = [
            span for span in scanline_spans(rings, y) if span[1] - span[0] >= spec.min_span_mm
        ]
        if spans:
            rows.append((y, spans))

    paths: list[list[Point]] = []
    for section in sections(rows):
        points: list[Point] = []
        previous: tuple[float, Span] | None = None
        for index, (y, span) in enumerate(section):
            row = row_points(span, y, index, spec, reverse=bool(index % 2))
            if not row:
                continue
            if points and previous is not None:
                points += _turn(points[-1], row[0], previous[1], span, spec)
            points += row
            previous = (y, span)
        if len(points) >= 2:
            paths.append([rotate(point, radians) for point in points])

    return [_drop_duplicates(path) for path in paths]


_DUPLICATE_MM = 1e-6


def _drop_duplicates(points: list[Point]) -> list[Point]:
    """Drop penetrations that land exactly on the previous one.

    Only exact duplicates. The minimum stitch length applies *within* a row;
    the turn from one row to the next is one row spacing long by construction,
    which on a dense fill is shorter than that minimum and is still a real,
    necessary stitch. Filtering those would delete one end of every other row
    and leave the fill short of its own edge.
    """
    kept = [points[0]]
    for point in points[1:]:
        if distance(kept[-1], point) > _DUPLICATE_MM:
            kept.append(point)
    return kept
