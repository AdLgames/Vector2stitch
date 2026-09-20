"""Shared polyline geometry for the stitch generators.

Pure functions over millimetre points. No profile knowledge, no IR knowledge,
no state -- everything a generator needs is passed in, so these can be reasoned
about and tested one at a time.
"""

from __future__ import annotations

import math

Point = tuple[float, float]


def distance(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def lerp(a: Point, b: Point, t: float) -> Point:
    """Point a fraction t of the way from a to b."""
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def path_length(points: list[Point]) -> float:
    return sum(distance(a, b) for a, b in zip(points, points[1:], strict=False))


def cumulative_lengths(points: list[Point]) -> list[float]:
    """Arc length at each vertex, starting at 0."""
    lengths = [0.0]
    for a, b in zip(points, points[1:], strict=False):
        lengths.append(lengths[-1] + distance(a, b))
    return lengths


def point_at(points: list[Point], target: float) -> Point:
    """The point at a given arc length along a polyline.

    Clamped at both ends, so a caller that overshoots by a rounding error gets
    the endpoint rather than an extrapolation off the end of the shape.
    """
    if len(points) == 1:
        return points[0]
    lengths = cumulative_lengths(points)
    total = lengths[-1]
    if total == 0:
        return points[0]
    target = min(max(target, 0.0), total)

    for index, (start, end) in enumerate(zip(lengths, lengths[1:], strict=False)):
        if target <= end:
            span = end - start
            if span == 0:
                return points[index]
            return lerp(points[index], points[index + 1], (target - start) / span)
    return points[-1]


def sample_evenly(points: list[Point], count: int) -> list[Point]:
    """`count` points spaced equally by arc length, ends included."""
    if count < 2:
        raise ValueError("need at least 2 samples")
    total = path_length(points)
    if total == 0:
        return [points[0]] * count
    return [point_at(points, total * index / (count - 1)) for index in range(count)]


def unit_vector(a: Point, b: Point) -> Point:
    """Direction from a to b. Returns (0, 0) when the two coincide."""
    span = distance(a, b)
    if span == 0:
        return (0.0, 0.0)
    return ((b[0] - a[0]) / span, (b[1] - a[1]) / span)


def extend(point: Point, direction: Point, amount: float) -> Point:
    return (point[0] + direction[0] * amount, point[1] + direction[1] * amount)
