"""Run stitch generation.

A run is a single line of stitches along a path. It is the simplest generator
and the one M0 needs end to end. Satin and fill arrive in M1; the shape of this
module -- pure functions over millimetre points, every parameter passed in --
is the pattern they follow.

Not yet here, and deliberately: shortening on tight curves (M1). A run through
a tight corner currently keeps its target length, which is visible on a
sew-out as a slightly cut corner.
"""

from __future__ import annotations

import math

Point = tuple[float, float]


def _distance(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _lerp(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def resample(
    points: list[Point],
    *,
    closed: bool,
    target_length_mm: float,
    max_length_mm: float,
) -> list[Point]:
    """Place penetrations along a path at roughly the target length.

    Original vertices are always kept, so corners stay sharp instead of being
    rounded off by an even resampling. Each segment is divided into equal parts
    no longer than the target -- equal parts rather than a running remainder,
    so a segment never ends with one stubby stitch.
    """
    if target_length_mm <= 0:
        raise ValueError("target stitch length must be positive")
    limit = min(target_length_mm, max_length_mm)

    path = list(points)
    if closed and path[0] != path[-1]:
        path.append(path[0])

    out: list[Point] = [path[0]]
    for start, end in zip(path, path[1:], strict=False):
        span = _distance(start, end)
        if span == 0:
            continue
        parts = max(1, math.ceil(round(span / limit, 9)))
        for step in range(1, parts + 1):
            out.append(_lerp(start, end, step / parts))
    return out


def drop_short_stitches(points: list[Point], min_length_mm: float) -> list[Point]:
    """Remove penetrations closer together than the machine floor.

    Stitches under the floor pile thread in one spot: thread breaks, and on a
    dense area a needle break. The last point is always kept -- it is where the
    object ends and where the tie-off goes -- so when the final stitch is too
    short it is the point *before* it that goes.
    """
    if len(points) < 2:
        return list(points)

    kept: list[Point] = [points[0]]
    for point in points[1:-1]:
        if _distance(kept[-1], point) >= min_length_mm:
            kept.append(point)

    last = points[-1]
    while len(kept) > 1 and _distance(kept[-1], last) < min_length_mm:
        kept.pop()
    kept.append(last)
    return kept


def apply_bean(points: list[Point], repeats: int) -> list[Point]:
    """Traverse the path `repeats` times, alternating direction.

    repeats=1 is a plain run; 3 is a bean (triple) run, which is how thin
    detail gets enough weight to read at sewing distance. Even repeat counts
    would end at the start of the path, so they are rejected rather than
    quietly leaving the needle in the wrong place.
    """
    if repeats < 1:
        raise ValueError("bean repeats must be at least 1")
    if repeats == 1:
        return list(points)
    if repeats % 2 == 0:
        raise ValueError(
            f"bean repeats must be odd so the run ends at its end point, got {repeats}"
        )

    out = list(points)
    for pass_index in range(1, repeats):
        leg = list(reversed(points)) if pass_index % 2 else list(points)
        out.extend(leg[1:])
    return out


def tie_points(anchor: Point, heading: Point, length_mm: float, count: int) -> list[Point]:
    """Small alternating stitches that lock the thread at `anchor`.

    Placed on every object start and before every trim; without them the first
    and last stitches pull out the moment the garment is worn or trimmed.
    `heading` is the neighbouring penetration, so the tie runs along the path
    rather than across it, where it would show. Returns `count` alternating
    penetrations plus a final return to the anchor, so the caller can continue
    from (or stop at) the anchor itself.
    """
    if count <= 0 or length_mm <= 0:
        return []
    span = _distance(anchor, heading)
    if span == 0:
        return []
    step = min(length_mm, span) / span
    inner = _lerp(anchor, heading, step)
    out: list[Point] = []
    for index in range(count):
        out.append(inner if index % 2 == 0 else anchor)
    if out and out[-1] != anchor:
        out.append(anchor)
    return out


def stitch_run(
    points: list[Point],
    *,
    closed: bool,
    target_length_mm: float,
    min_length_mm: float,
    max_length_mm: float,
    bean_repeats: int,
) -> list[Point]:
    """Full run generation: resample, filter the floor, then bean if asked."""
    sampled = resample(
        points,
        closed=closed,
        target_length_mm=target_length_mm,
        max_length_mm=max_length_mm,
    )
    filtered = drop_short_stitches(sampled, min_length_mm)
    return apply_bean(filtered, bean_repeats)
