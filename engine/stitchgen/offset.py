"""Polygon offsetting.

Insetting a shape is how underlay stays under the top layer and how hidden
stitches get removed later. Doing it correctly on concave shapes and shapes
with holes is not something to hand-roll: this wraps Clipper, which works in
integer coordinates, so millimetres are scaled on the way in and back on the
way out.
"""

from __future__ import annotations

import pyclipper

from engine.stitchgen.geometry import Point

Ring = list[Point]

SCALE = 1000
"""Integer units per millimetre. At 1/1000 mm the rounding is two orders of
magnitude below the machine's own 0.1 mm grid, so it cannot move a stitch."""


def _to_clipper(ring: Ring) -> list[tuple[int, int]]:
    return [(round(x * SCALE), round(y * SCALE)) for x, y in ring]


def _from_clipper(path: list[tuple[int, int]]) -> Ring:
    return [(x / SCALE, y / SCALE) for x, y in path]


def offset_ring(ring: Ring, amount_mm: float) -> list[Ring]:
    """Offset one closed ring. Negative insets, positive grows.

    Returns a list because insetting can split a shape into several -- a
    dumbbell narrow enough in the middle becomes two. Returns empty when the
    shape disappears entirely, which is the honest answer for a shape too thin
    to inset.
    """
    if amount_mm == 0:
        return [list(ring)]
    offsetter = pyclipper.PyclipperOffset()
    offsetter.AddPath(_to_clipper(ring), pyclipper.JT_MITER, pyclipper.ET_CLOSEDPOLYGON)
    return [_from_clipper(path) for path in offsetter.Execute(amount_mm * SCALE)]


def inset_shape(outer: Ring, holes: list[Ring], amount_mm: float) -> tuple[list[Ring], list[Ring]]:
    """Shrink a shape by `amount_mm` all round: outline in, holes out.

    A hole grows as the shape shrinks, because the fabric between the two has
    to keep its distance from both.
    """
    if amount_mm <= 0:
        return [list(outer)], [list(hole) for hole in holes]
    return (
        offset_ring(outer, -amount_mm),
        [grown for hole in holes for grown in offset_ring(hole, amount_mm)],
    )
