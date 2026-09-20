"""Fabric profile loading.

No fabric profile, no file. A profile bundles the thresholds, densities,
underlay recipes and compensation for one material, and is referenced by a
pinned string like "pique@3" so a delivered file can always be reproduced.

Changing a profile is a release, not an edit: bump `version`, keep the old
file, and re-run the calibration sew-outs.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

_DATA_DIR = Path(__file__).parent / "data"
_REF = re.compile(r"^(?P<name>[a-z0-9_]+)(?:@(?P<version>\d+))?$")


class ProfileNotFound(LookupError):
    """No profile file for that name, or the pinned version does not match."""


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_max_width_mm: float = Field(gt=0)
    satin_max_width_mm: float = Field(gt=0)
    min_text_height_mm: float = Field(gt=0)


class StitchLengths(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_length_mm: float = Field(gt=0)
    fill_length_mm: float = Field(gt=0)
    min_length_mm: float = Field(gt=0)
    max_length_mm: float = Field(gt=0)
    bean_repeats: int = Field(ge=1)
    tie_length_mm: float = Field(gt=0)
    tie_stitches: int = Field(ge=0)


class Density(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fill_row_spacing_mm: float = Field(gt=0)
    satin_spacing_mm: float = Field(gt=0)
    overlap_scale: float = Field(gt=0, le=1)


class Compensation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pull_comp_mm_per_side: float = Field(ge=0)
    push_comp_mm: float = Field(ge=0)


class Underlay(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    satin_narrow: list[str]
    satin_medium: list[str]
    satin_wide: list[str]
    fill: list[str]
    satin_narrow_max_width_mm: float = Field(gt=0)
    satin_medium_max_width_mm: float = Field(gt=0)
    inset_mm: float = Field(ge=0)

    def for_satin(self, width_mm: float) -> list[str]:
        """The underlay recipe for a satin column of this width."""
        if width_mm < self.satin_narrow_max_width_mm:
            return list(self.satin_narrow)
        if width_mm < self.satin_medium_max_width_mm:
            return list(self.satin_medium)
        return list(self.satin_wide)


class Routing(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trim_threshold_mm: float = Field(gt=0)
    overlap_margin_mm: float = Field(ge=0)
    sequencing: str


class Materials(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stabilizer: str
    topping: bool


class FabricProfile(BaseModel):
    """One calibrated (or not yet calibrated) material recipe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    version: int = Field(ge=1)
    description: str
    calibrated: bool
    """False until physical sew-outs on our own machines have moved these
    numbers. Checks warn on uncalibrated profiles; the quality doc is explicit
    that screen output proves nothing."""

    classification: Classification
    stitch: StitchLengths
    density: Density
    compensation: Compensation
    underlay: Underlay
    routing: Routing
    materials: Materials

    @property
    def ref(self) -> str:
        """The pinned reference recorded on every design and delivered file."""
        return f"{self.name}@{self.version}"


def parse_ref(ref: str) -> tuple[str, int | None]:
    """Split "pique@3" into ("pique", 3); "pique" into ("pique", None)."""
    match = _REF.match(ref.strip())
    if not match:
        raise ProfileNotFound(f"malformed profile reference: {ref!r}")
    version = match.group("version")
    return match.group("name"), int(version) if version else None


@cache
def load_profile(ref: str, data_dir: str | None = None) -> FabricProfile:
    """Load a profile by reference, e.g. "twill@1" or "twill".

    An unpinned name loads whatever version ships today, which is fine for the
    lab and never fine for a delivery: the service pins the version onto the
    design so the file can be reproduced later.
    """
    name, want_version = parse_ref(ref)
    directory = Path(data_dir) if data_dir else _DATA_DIR
    path = directory / f"{name}.yaml"
    if not path.exists():
        raise ProfileNotFound(f"no profile file for {name!r} in {directory}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    profile = FabricProfile.model_validate(raw)

    if profile.name != name:
        raise ProfileNotFound(f"{path.name} declares name {profile.name!r}, expected {name!r}")
    if want_version is not None and profile.version != want_version:
        raise ProfileNotFound(
            f"profile {name!r} is at version {profile.version}, design pins @{want_version}"
        )
    return profile


def available_profiles(data_dir: str | None = None) -> list[str]:
    """Every shipped profile reference, sorted."""
    directory = Path(data_dir) if data_dir else _DATA_DIR
    refs = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        refs.append(f"{raw['name']}@{raw['version']}")
    return refs
