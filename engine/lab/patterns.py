"""Calibration patterns.

The fixed set the lab sews to decide what the fabric profiles should say.
Every number in every profile is an inherited default until one of these comes
back off a machine with a measurement attached.

Two rules hold here:

* A pattern is built from the same IR and the same generators as a customer
  design. A calibration path that bypassed the engine would calibrate the
  wrong thing.
* A pattern the engine cannot yet sew well is declared, not quietly omitted,
  and says which milestone brings it. Half the set is waiting on satin and
  fill (M1) and text (M6); pretending otherwise would hide exactly the gap the
  lab is meant to close.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from engine.ir.schema import (
    Design,
    EmbroideryObject,
    IRDocument,
    ObjectKind,
    ObjectParams,
    ParamSource,
    Placement,
    PolylineShape,
    Thread,
)
from engine.lab.targets import Axis, MeasurementTarget
from engine.profiles.loader import load_profile

BLACK = Thread(chart="madeira_polyneon_40", code="1800", rgb="#1a1a1a", description="Black")
RED = Thread(chart="madeira_polyneon_40", code="1147", rgb="#c8102e", description="Scarlet")

_CIRCLE_SEGMENTS = 72
"""Points per circle. Enough that the polygon is not what the calipers
measure; the resample in the run generator decides the actual stitches."""


@dataclass(frozen=True)
class CalibrationPattern:
    """A pattern, what it is for, and what to measure on it."""

    name: str
    purpose: str
    build: Callable[[str], tuple[IRDocument, list[MeasurementTarget]]] | None
    requires: str | None = None
    """The milestone that has to land first, or None if it builds today."""

    @property
    def available(self) -> bool:
        return self.build is not None


class PatternNotAvailable(NotImplementedError):
    """A declared pattern whose generators do not exist yet."""


def _is_cap(profile_ref: str) -> bool:
    """Whether this profile describes a cap.

    A cap pattern has to declare a cap placement, or it is checked against a
    flat sew field it will never be hooped in -- and a calibration pattern
    that cannot be hooped calibrates nothing.
    """
    return load_profile(profile_ref).routing.sequencing == "center_out"


def _document(profile_ref: str, objects: list[EmbroideryObject]) -> IRDocument:
    """Wrap objects in a design sized to what they actually occupy.

    Declared size is measured from the geometry rather than written by hand,
    so a pattern can never claim dimensions it does not have -- which would
    quietly defeat the sew-field check it is about to go through.
    """
    points = [point for obj in objects for point in obj.shape.points]
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    return IRDocument(
        design=Design(
            width_mm=max_x - min_x,
            height_mm=max_y - min_y,
            placement=Placement.CAP_FRONT if _is_cap(profile_ref) else Placement.LEFT_CHEST,
            fabric_profile=profile_ref,
            thread_brand="madeira_polyneon_40",
        ),
        objects=objects,
    )


def _run(
    object_id: str,
    points: list[tuple[float, float]],
    *,
    closed: bool = False,
    thread: Thread = BLACK,
    z_order: int = 0,
    params: ObjectParams | None = None,
    param_source: dict[str, ParamSource] | None = None,
) -> EmbroideryObject:
    return EmbroideryObject(
        id=object_id,
        kind=ObjectKind.RUN,
        shape=PolylineShape(points=points, closed=closed),
        thread=thread,
        z_order=z_order,
        params=params or ObjectParams(),
        param_source=param_source or {},
    )


def _square(origin: tuple[float, float], side: float) -> list[tuple[float, float]]:
    x, y = origin
    return [(x, y), (x + side, y), (x + side, y + side), (x, y + side)]


def _circle(center: tuple[float, float], diameter: float) -> list[tuple[float, float]]:
    cx, cy = center
    radius = diameter / 2
    return [
        (
            cx + radius * math.cos(2 * math.pi * i / _CIRCLE_SEGMENTS),
            cy + radius * math.sin(2 * math.pi * i / _CIRCLE_SEGMENTS),
        )
        for i in range(_CIRCLE_SEGMENTS)
    ]


def dimension_grid(profile_ref: str) -> tuple[IRDocument, list[MeasurementTarget]]:
    """Squares and circles at known sizes: the primary caliper target.

    Squares read pull and push separately, because the two axes are not
    equivalent under a directional stitch. Circles read both at once and show
    up as an oval when compensation is wrong on one axis only. Three sizes,
    because draw-in does not scale linearly with the shape.
    """
    objects: list[EmbroideryObject] = []
    targets: list[MeasurementTarget] = []

    # A cap front is about 70 mm tall. The flat sizes do not fit it, and a
    # pattern that cannot be hooped measures nothing -- so the cap set trades
    # the 60 mm square for a shorter ladder in a single band.
    cap = _is_cap(profile_ref)
    sides = (15.0, 25.0, 35.0) if cap else (20.0, 40.0, 60.0)
    diameters = (15.0, 25.0) if cap else (20.0, 40.0)
    circle_row_y = 45.0 if cap else 80.0

    x = 5.0
    for index, side in enumerate(sides, start=1):
        objects.append(_run(f"square_{index:02d}", _square((x, 5.0), side), closed=True))
        targets += [
            MeasurementTarget(
                id=f"square_{index:02d}_x",
                description=f"{side:.0f} mm square, width across",
                designed_mm=side,
                axis=Axis.X,
            ),
            MeasurementTarget(
                id=f"square_{index:02d}_y",
                description=f"{side:.0f} mm square, height up",
                designed_mm=side,
                axis=Axis.Y,
            ),
        ]
        x += side + 8.0

    x = 5.0
    for index, diameter in enumerate(diameters, start=1):
        center = (x + diameter / 2, circle_row_y + diameter / 2)
        objects.append(
            _run(f"circle_{index:02d}", _circle(center, diameter), closed=True, thread=RED)
        )
        targets += [
            MeasurementTarget(
                id=f"circle_{index:02d}_x",
                description=f"{diameter:.0f} mm circle, across",
                designed_mm=diameter,
                axis=Axis.X,
            ),
            MeasurementTarget(
                id=f"circle_{index:02d}_y",
                description=f"{diameter:.0f} mm circle, up -- unequal to across means "
                "compensation is wrong on one axis",
                designed_mm=diameter,
                axis=Axis.Y,
            ),
        ]
        x += diameter + 10.0

    return _document(profile_ref, objects), targets


def registration_target(profile_ref: str) -> tuple[IRDocument, list[MeasurementTarget]]:
    """Two-colour crosshairs: how far the second colour lands from the first.

    Registration error is what gapping looks like before it is visible as a
    gap. Sewing the same crosshair twice in two colours makes the offset
    directly measurable instead of inferred from a ruined logo.
    """
    objects: list[EmbroideryObject] = []
    targets: list[MeasurementTarget] = []

    for index, (cx, cy) in enumerate(((25.0, 25.0), (75.0, 25.0), (50.0, 70.0)), start=1):
        arm = 10.0
        objects.append(
            _run(
                f"cross_black_{index:02d}",
                [(cx - arm, cy), (cx + arm, cy)],
                z_order=0,
            )
        )
        objects.append(
            _run(
                f"cross_red_{index:02d}",
                [(cx, cy - arm), (cx, cy + arm)],
                thread=RED,
                z_order=1,
            )
        )
        targets.append(
            MeasurementTarget(
                id=f"cross_{index:02d}_offset",
                description=(
                    f"crosshair {index}: distance from the red vertical to the centre of "
                    "the black horizontal. Designed to intersect exactly."
                ),
                designed_mm=arm,
                axis=Axis.X,
                tolerance_mm=0.3,
            )
        )

    return _document(profile_ref, objects), targets


def stitch_length_ladder(profile_ref: str) -> tuple[IRDocument, list[MeasurementTarget]]:
    """Straight runs at rising stitch lengths.

    Finds where a run stops looking like a line and starts looking like a row
    of dashes on this fabric, which is the number `run_length_mm` should be.
    """
    objects: list[EmbroideryObject] = []
    targets: list[MeasurementTarget] = []
    lengths = (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0)

    for index, length in enumerate(lengths, start=1):
        y = 5.0 + index * 8.0
        objects.append(
            _run(
                f"ladder_{index:02d}",
                [(5.0, y), (65.0, y)],
                params=ObjectParams(stitch_length_mm=length),
                param_source={"stitch_length_mm": ParamSource.RULE},
            )
        )
        targets.append(
            MeasurementTarget(
                id=f"ladder_{index:02d}_length",
                description=f"run at {length:.1f} mm stitch length, 60 mm long",
                designed_mm=60.0,
                axis=Axis.X,
            )
        )

    return _document(profile_ref, objects), targets


def travel_and_trim(profile_ref: str) -> tuple[IRDocument, list[MeasurementTarget]]:
    """Pairs of segments at rising gaps.

    Shows where an untrimmed travel starts being visible on this fabric, which
    is what `trim_threshold_mm` should be set from. Too low wastes machine
    time on trims; too high drags thread across the design.
    """
    objects: list[EmbroideryObject] = []
    targets: list[MeasurementTarget] = []
    gaps = (2.0, 4.0, 6.0, 8.0, 12.0, 20.0)

    for index, gap in enumerate(gaps, start=1):
        y = 5.0 + index * 10.0
        objects.append(_run(f"pair_{index:02d}_a", [(5.0, y), (25.0, y)], z_order=index * 2))
        objects.append(
            _run(
                f"pair_{index:02d}_b",
                [(25.0 + gap, y), (45.0 + gap, y)],
                z_order=index * 2 + 1,
            )
        )
        targets.append(
            MeasurementTarget(
                id=f"pair_{index:02d}_gap",
                description=f"{gap:.0f} mm gap: is the travel trimmed, hidden, or showing?",
                designed_mm=gap,
                axis=Axis.GAP,
            )
        )

    return _document(profile_ref, objects), targets


def corner_set(profile_ref: str) -> tuple[IRDocument, list[MeasurementTarget]]:
    """Angles from sharp to shallow.

    The engine does not yet shorten stitches through a tight corner (M1), so
    these will cut their corners. Sewing them now measures how much, on which
    angles, so the fix has a number to beat rather than an opinion.
    """
    objects: list[EmbroideryObject] = []
    targets: list[MeasurementTarget] = []
    angles = (15.0, 30.0, 45.0, 60.0, 90.0, 120.0)
    arm = 18.0

    for index, angle in enumerate(angles, start=1):
        column, row = (index - 1) % 3, (index - 1) // 3
        origin_x = 10.0 + column * 40.0
        origin_y = 10.0 + row * 45.0
        radians = math.radians(angle)
        points = [
            (origin_x + arm, origin_y),
            (origin_x, origin_y),
            (origin_x + arm * math.cos(radians), origin_y + arm * math.sin(radians)),
        ]
        objects.append(_run(f"corner_{index:02d}", points))
        targets.append(
            MeasurementTarget(
                id=f"corner_{index:02d}_angle",
                description=f"{angle:.0f} degree corner: how far the point falls short",
                designed_mm=angle,
                axis=Axis.ANGLE,
                tolerance_mm=2.0,
            )
        )

    return _document(profile_ref, objects), targets


PATTERNS: dict[str, CalibrationPattern] = {
    pattern.name: pattern
    for pattern in (
        CalibrationPattern(
            name="dimension_grid",
            purpose="Pull and push compensation, from squares and circles at three sizes",
            build=dimension_grid,
        ),
        CalibrationPattern(
            name="registration_target",
            purpose="Colour-to-colour registration offset",
            build=registration_target,
        ),
        CalibrationPattern(
            name="stitch_length_ladder",
            purpose="Where a run stops reading as a line on this fabric",
            build=stitch_length_ladder,
        ),
        CalibrationPattern(
            name="travel_and_trim",
            purpose="Where an untrimmed travel becomes visible",
            build=travel_and_trim,
        ),
        CalibrationPattern(
            name="corner_set",
            purpose="Corner cutting at angles from 15 to 120 degrees",
            build=corner_set,
        ),
        CalibrationPattern(
            name="column_ladder",
            purpose="Satin column widths from 1 to 8 mm: split point, edge quality, underlay",
            build=None,
            requires="M1",
        ),
        CalibrationPattern(
            name="density_wedge",
            purpose="Tatami fill at rising densities: puckering, coverage, thread breaks",
            build=None,
            requires="M1",
        ),
        CalibrationPattern(
            name="text_ladder",
            purpose="Lettering from 3 to 10 mm: the legibility floor per thread weight",
            build=None,
            requires="M6",
        ),
    )
}

AVAILABLE = [name for name, pattern in PATTERNS.items() if pattern.available]
PENDING = [name for name, pattern in PATTERNS.items() if not pattern.available]


def build_pattern(name: str, profile_ref: str) -> tuple[IRDocument, list[MeasurementTarget]]:
    """Build one calibration pattern for one fabric profile."""
    pattern = PATTERNS.get(name)
    if pattern is None:
        raise KeyError(f"unknown calibration pattern {name!r}; have {sorted(PATTERNS)}")
    if pattern.build is None:
        raise PatternNotAvailable(
            f"{name} needs generators that land in {pattern.requires}: {pattern.purpose}"
        )
    return pattern.build(profile_ref)
