"""Shop overrides on fabric profiles.

A fabric profile's numbers are ours: industry-derived defaults, the same for
everyone, changed by release. A shop's own experience is not ours, and it
arrives long before we can sew anything ourselves -- a decorator who has run
pique on their stabiliser for ten years knows something we do not.

This layer lets them say so, without forking the profile. An override file
names specific fields, a value for each, and *why* -- and the why is the point.
Three things fall out of it:

* The shop gets output that matches their floor, today.
* Every delivered file records which fields were overridden, so a complaint is
  still reproducible.
* The reasons aggregate. When forty shops move pique's fill spacing the same
  direction, that is calibration, bought with other people's machines.

What this is not: a way to avoid measuring. An override with no evidence
behind it is one shop's guess, and it is recorded as exactly that.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from engine.profiles.loader import FabricProfile, load_profile, parse_ref

_ENV_DIR = "V2S_PROFILE_DIR"
"""A shop's own override directory."""

_FILE = re.compile(r"^(?P<name>[a-z0-9_]+)@(?P<version>\d+)\.override\.yaml$")

LARGE_CHANGE_FACTOR = 2.0
"""An override this far from the shipped value is reported, not rejected.

Not a stitch parameter -- a fat-finger guard. A shop moving pull compensation
from 0.175 to 0.22 is experience; moving it to 1.75 is a misplaced decimal
point, and it should be said out loud before it reaches a garment.
"""


class OverrideError(ValueError):
    """The override file names a field that does not exist, or a bad value."""


class OverrideEntry(BaseModel):
    """One changed value, and the reason for it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float | int | bool | str | list[str]
    reason: str = Field(min_length=1)
    """Required. An override without a reason cannot be aggregated, cannot be
    reviewed, and cannot be told apart from a typo a year from now."""
    evidence: str = ""
    """A sew-out, a date, a job number -- whatever backs the reason up. Empty
    means this is experience rather than measurement, which is worth knowing."""


class ProfileOverride(BaseModel):
    """One shop's changes to one fabric profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: str
    """The profile reference this applies to, e.g. "pique@1". Pinned: a shop's
    reasons were formed against a specific version of our numbers."""
    shop: str
    recorded_on: date
    note: str = ""
    overrides: dict[str, OverrideEntry] = Field(default_factory=dict)
    """Dotted paths into the profile, e.g. "compensation.pull_comp_mm_per_side"."""

    @field_validator("overrides", mode="before")
    @classmethod
    def _empty_section_is_no_overrides(cls, value: Any) -> Any:
        """A scaffolded file whose entries are all still commented out parses
        as `overrides: None`. That is a shop that has not decided anything
        yet, not a broken file."""
        return {} if value is None else value


@dataclass(frozen=True)
class AppliedOverride:
    """What actually changed, for the worksheet and for the record."""

    path: str
    shipped: Any
    value: Any
    reason: str
    evidence: str

    @property
    def is_large(self) -> bool:
        """Whether this looks more like a typo than an adjustment."""
        if not isinstance(self.shipped, int | float) or isinstance(self.shipped, bool):
            return False
        if not isinstance(self.value, int | float) or isinstance(self.value, bool):
            return False
        if self.shipped == 0:
            return self.value != 0
        ratio = self.value / self.shipped
        return ratio >= LARGE_CHANGE_FACTOR or ratio <= 1 / LARGE_CHANGE_FACTOR

    def describe(self) -> str:
        return f"{self.path}: {self.shipped} -> {self.value} ({self.reason})"


def search_path(extra_dir: str | Path | None = None) -> list[Path]:
    """Where override files are looked for, nearest first."""
    path = []
    if extra_dir:
        path.append(Path(extra_dir))
    env_dir = os.environ.get(_ENV_DIR)
    if env_dir:
        path.append(Path(env_dir))
    return [directory for directory in path if directory.is_dir()]


def load_override(ref: str, extra_dir: str | Path | None = None) -> ProfileOverride | None:
    """Find a shop's override file for a profile, if there is one.

    Nothing ships with the engine: an override is by definition local. Absent
    is the normal case and is not an error.
    """
    name, version = parse_ref(ref)
    if version is None:
        version = load_profile(name).version

    for directory in search_path(extra_dir):
        path = directory / f"{name}@{version}.override.yaml"
        if not path.exists():
            continue
        override = ProfileOverride.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
        if override.profile != f"{name}@{version}":
            raise OverrideError(
                f"{path.name} declares profile {override.profile!r}, "
                f"expected {name}@{version}"
            )
        return override
    return None


def _read_path(data: dict[str, Any], path: str) -> Any:
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise OverrideError(f"profile has no field {path!r}")
        node = node[part]
    return node


def _write_path(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node = data
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value


def apply_override(
    profile: FabricProfile, override: ProfileOverride
) -> tuple[FabricProfile, list[AppliedOverride]]:
    """Return the profile as this shop runs it, plus what changed.

    The result is re-validated through the same model as a shipped profile, so
    an override cannot produce a profile the engine would have rejected on
    disk -- a negative density is refused here exactly as it would be there.
    """
    data = profile.model_dump(mode="json")
    applied: list[AppliedOverride] = []

    for path, entry in sorted(override.overrides.items()):
        shipped = _read_path(data, path)
        if isinstance(shipped, dict):
            raise OverrideError(f"{path!r} is a section, not a value")
        _write_path(data, path, entry.value)
        applied.append(
            AppliedOverride(
                path=path,
                shipped=shipped,
                value=entry.value,
                reason=entry.reason,
                evidence=entry.evidence,
            )
        )

    try:
        adjusted = FabricProfile.model_validate(data)
    except Exception as exc:  # pydantic's own message names the field
        raise OverrideError(f"override produces an invalid profile: {exc}") from None
    return adjusted, applied


def effective_profile(
    ref: str, override_dir: str | Path | None = None
) -> tuple[FabricProfile, list[AppliedOverride]]:
    """Load a profile as this shop runs it.

    With no override file this is exactly the shipped profile and an empty
    list, which is what every call site handles by default.
    """
    profile = load_profile(ref)
    override = load_override(ref, override_dir)
    if override is None:
        return profile, []
    return apply_override(profile, override)


def override_template(profile: FabricProfile, shop: str) -> str:
    """A starting override file for a shop: every field, commented out.

    Listing every field rather than a chosen few is deliberate. A shop should
    see what is adjustable, and see the shipped value next to it, rather than
    guess at field names from an error message.
    """
    lines = [
        f"# Shop overrides for {profile.ref} -- {profile.description}",
        "#",
        "# Uncomment a field, set a value, and say why. The reason is required:",
        "# an override without one cannot be reviewed, cannot be aggregated, and",
        "# cannot be told from a typo a year from now.",
        "#",
        "# These are OUR defaults, not measurements. If your floor disagrees with",
        "# one, your floor is the better evidence -- record it here and say what it",
        "# is based on.",
        "",
        f"profile: {profile.ref}",
        f"shop: {shop!r}",
        f"recorded_on: {date.today().isoformat()}",
        'note: ""',
        "",
        "# Replace the {} below with your own entries as you uncomment them.",
        "overrides: {}",
        "",
    ]

    data = profile.model_dump(mode="json")
    skip = {"name", "version", "description", "calibrated"}
    for section, values in data.items():
        if section in skip or not isinstance(values, dict):
            continue
        lines.append(f"  # --- {section} ---")
        for field, value in values.items():
            lines += [
                f"  # {section}.{field}:",
                f"  #   value: {value!r}       # shipped default",
                '  #   reason: ""',
                '  #   evidence: ""',
            ]
        lines.append("")
    return "\n".join(lines) + "\n"


def available_overrides(extra_dir: str | Path | None = None) -> list[tuple[str, Path]]:
    """Every override file on the search path, nearest first."""
    seen: dict[str, Path] = {}
    for directory in search_path(extra_dir):
        for path in sorted(directory.glob("*.override.yaml")):
            match = _FILE.match(path.name)
            if match:
                seen.setdefault(f"{match.group('name')}@{match.group('version')}", path)
    return sorted(seen.items())
