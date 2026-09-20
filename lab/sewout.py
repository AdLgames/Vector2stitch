"""The sew-out log.

A sew-out that is not written down is a sew-out that did not happen. Each
record ties a measured result to the exact versions that produced it -- engine,
fabric profile, machine profile -- plus the consumables, because an
uncontrolled variable makes the measurement worse than useless: it moves a
parameter for the wrong reason.

Storage is a JSONL file. Append-only, diffable, and readable without this
tool, which matters more than query speed for a log that grows by a few rows a
week.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from engine.lab.targets import MeasurementTarget
from lab.defects import Defect

_MEASUREMENT_DECIMALS = 2
"""Calipers read to hundredths of a millimetre; comparisons round to match."""


class Consumables(BaseModel):
    """Held constant across a calibration run, and recorded every time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    thread: str
    needle: str
    stabilizer: str
    topping: str = "none"
    speed_spm: int = Field(gt=0)


class SewOut(BaseModel):
    """One pattern, sewn once, measured."""

    model_config = ConfigDict(extra="forbid")

    sewn_on: date
    operator: str
    pattern: str
    fabric_profile: str
    engine_version: str
    machine_profile: str | None = None
    consumables: Consumables
    measurements: dict[str, float] = Field(default_factory=dict)
    """Target id -> measured millimetres."""
    defects: list[Defect] = Field(default_factory=list)
    photo: str | None = None
    notes: str = ""


@dataclass(frozen=True)
class Deviation:
    """One measurement against what it was designed at."""

    target: MeasurementTarget
    measured_mm: float

    @property
    def error_mm(self) -> float:
        """Signed: negative means the sewn feature came out small (draw-in)."""
        return self.measured_mm - self.target.designed_mm

    @property
    def within_tolerance(self) -> bool:
        """Inclusive of the tolerance itself.

        Rounded first: measurements are read to hundredths of a millimetre,
        and binary float noise on a subtraction (19.7 - 20.0 is not exactly
        -0.3) would otherwise fail a measurement that landed exactly on the
        limit. A caliper reading does not carry sixteen digits.
        """
        return round(abs(self.error_mm), _MEASUREMENT_DECIMALS) <= self.target.tolerance_mm


@dataclass
class Evaluation:
    """A scored sew-out."""

    sewout: SewOut
    deviations: list[Deviation]
    unmeasured: list[str]

    @property
    def worst(self) -> Deviation | None:
        return max(self.deviations, key=lambda d: abs(d.error_mm), default=None)

    @property
    def passed(self) -> bool:
        """Every measured target inside tolerance, nothing left unmeasured.

        An unmeasured target fails rather than passes by omission: a
        calibration run that skipped half the calipers is not a pass.
        """
        return (
            bool(self.deviations)
            and not self.unmeasured
            and all(d.within_tolerance for d in self.deviations)
        )

    def mean_error_mm(self) -> float:
        """Signed mean. Consistently negative means the profile under-compensates."""
        if not self.deviations:
            return 0.0
        return sum(d.error_mm for d in self.deviations) / len(self.deviations)


def evaluate(sewout: SewOut, targets: list[MeasurementTarget]) -> Evaluation:
    """Score a sew-out against the pattern's measurement targets."""
    by_id = {target.id: target for target in targets}
    unknown = sorted(set(sewout.measurements) - set(by_id))
    if unknown:
        raise KeyError(f"measurements for targets not in this pattern: {unknown}")

    deviations = [
        Deviation(target=by_id[target_id], measured_mm=value)
        for target_id, value in sorted(sewout.measurements.items())
    ]
    unmeasured = sorted(set(by_id) - set(sewout.measurements))
    return Evaluation(sewout=sewout, deviations=deviations, unmeasured=unmeasured)


def append(sewout: SewOut, log_path: str | Path) -> Path:
    """Append one record to the log, creating it if needed."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(sewout.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return path


def read_log(log_path: str | Path) -> list[SewOut]:
    """Read every record. Order is the order they were sewn in."""
    path = Path(log_path)
    if not path.exists():
        return []
    return [
        SewOut.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_targets(targets_path: str | Path) -> list[MeasurementTarget]:
    """Read the targets file written beside a calibration pattern."""
    raw = json.loads(Path(targets_path).read_text(encoding="utf-8"))
    return [MeasurementTarget.model_validate(entry) for entry in raw["targets"]]
