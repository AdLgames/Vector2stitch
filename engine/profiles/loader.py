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
from pydantic import BaseModel, ConfigDict, Field, model_validator

_DATA_DIR = Path(__file__).parent / "data"
_REF = re.compile(r"^(?P<name>[a-z0-9_]+)(?:@(?P<version>\d+))?$")
_FILE = re.compile(r"^(?P<name>[a-z0-9_]+)@(?P<version>\d+)\.yaml$")


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


class Satin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    short_stitch_min_spacing_mm: float = Field(gt=0)
    short_stitch_depth: float = Field(gt=0, lt=1)
    split_overlap_mm: float = Field(ge=0)


class Fill(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    default_angle_deg: float
    stagger_steps: int = Field(ge=1)
    min_span_mm: float = Field(gt=0)
    hole_clearance_mm: float = Field(ge=0)
    min_turn_fraction: float = Field(gt=0, le=1)


class Checks(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_penetrations_per_mm2: float = Field(gt=0)
    penetration_bin_mm: float = Field(gt=0)
    trim_budget_per_1000: float = Field(ge=0)
    jump_budget_per_1000: float = Field(ge=0)
    color_change_budget: int = Field(ge=0)
    budget_min_stitches: int = Field(ge=0)
    """Below this, per-thousand ratios say more about the design's size than
    about its quality, so the budgets are not judged."""


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
    zigzag_spacing_multiplier: float = Field(gt=1)
    tatami_spacing_multiplier: float = Field(gt=1)
    tatami_angle_offset_deg: float

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


class Machine(BaseModel):
    """What the operator sets up at the machine.

    These change nothing the engine computes -- they are carried so the
    worksheet can tell the operator what to hang, what needle to fit, how fast
    to run and what to set the tension to. A fabric profile that specifies
    stitches but leaves those to memory is half a recipe.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    thread_weight_wt: int = Field(gt=0)
    """Indirect weight: higher is finer. Engine geometry assumes 40 wt."""
    thread_type: str
    needle_size: str
    max_spm: int = Field(gt=0)
    """Recommended ceiling, not the machine's nameplate. Running above it buys
    thread breaks and needle heat, which cost more time than the speed saves."""
    bobbin_tension_gf_min: float = Field(gt=0)
    bobbin_tension_gf_max: float = Field(gt=0)
    top_to_bobbin_tension_ratio: float = Field(gt=0)
    """Top tension is set as a multiple of a gauge-measured bobbin baseline,
    rather than by feel."""

    @model_validator(mode="after")
    def _tension_range_is_a_range(self) -> Machine:
        if self.bobbin_tension_gf_min > self.bobbin_tension_gf_max:
            raise ValueError("bobbin tension min exceeds max")
        return self


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
    satin: Satin
    fill: Fill
    checks: Checks
    compensation: Compensation
    underlay: Underlay
    routing: Routing
    materials: Materials
    machine: Machine

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

    versions = _versions_of(name, directory)
    if not versions:
        raise ProfileNotFound(f"no profile file for {name!r} in {directory}")

    if want_version is None:
        want_version = max(versions)
    elif want_version not in versions:
        raise ProfileNotFound(
            f"profile {name!r} has versions {sorted(versions)}, design pins @{want_version}. "
            "Old versions are kept precisely so old designs reopen; this one is missing."
        )

    path = directory / f"{name}@{want_version}.yaml"
    profile = FabricProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    if (profile.name, profile.version) != (name, want_version):
        raise ProfileNotFound(
            f"{path.name} declares {profile.name}@{profile.version}, expected {name}@{want_version}"
        )
    return profile


def _versions_of(name: str, directory: Path) -> set[int]:
    """Every version of one profile on disk."""
    found = set()
    for path in directory.glob(f"{name}@*.yaml"):
        match = _FILE.match(path.name)
        if match and match.group("name") == name:
            found.add(int(match.group("version")))
    return found


def available_profiles(data_dir: str | None = None) -> list[str]:
    """Every shipped profile reference, including superseded versions.

    Superseded versions stay on disk and stay loadable: a design delivered
    against pique@1 must still reproduce byte for byte after pique@2 ships.
    """
    directory = Path(data_dir) if data_dir else _DATA_DIR
    refs = []
    for path in directory.glob("*.yaml"):
        match = _FILE.match(path.name)
        if match:
            refs.append((match.group("name"), int(match.group("version"))))
    return [f"{name}@{version}" for name, version in sorted(refs)]


def current_profiles(data_dir: str | None = None) -> list[str]:
    """The newest version of each profile -- what a new order gets pinned to."""
    latest: dict[str, int] = {}
    for ref in available_profiles(data_dir):
        name, version = parse_ref(ref)
        latest[name] = max(latest.get(name, 0), version or 0)
    return [f"{name}@{version}" for name, version in sorted(latest.items())]
