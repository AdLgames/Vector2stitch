"""Measurement targets: what a calibration pattern is asking you to measure.

A pattern that sews but does not say what to put the calipers on is a picture,
not an instrument. Every pattern carries its targets, each with the dimension
it was designed at, so a sew-out produces a number -- measured minus designed
-- rather than an impression.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Axis(StrEnum):
    """Which way the measurement runs.

    Pull draws the fabric in along the stitch direction and pushes it out at
    the ends, so the same shape reads differently on each axis. Recording the
    axis is what lets a sew-out separate pull compensation from push.
    """

    X = "x"
    Y = "y"
    DIAMETER = "diameter"
    GAP = "gap"
    ANGLE = "angle"


class MeasurementTarget(BaseModel):
    """One thing to measure on a sewn calibration pattern."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    description: str
    designed_mm: float = Field(gt=0)
    axis: Axis
    tolerance_mm: float = Field(default=0.3, gt=0)
    """The dimensional error target. Outside it, a parameter needs to move --
    not the measurement repeated until it agrees."""
