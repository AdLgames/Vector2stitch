"""Machine profiles: the shop's own hardware, described by the shop.

A fabric profile says how to sew a material. A machine profile says what the
hardware in *this* room can actually do -- how fast it holds without breaking
thread, how big its field is, whether it has a cap driver and an auto trimmer,
what the bobbin gauge reads after a local calibration.

The split matters because the two have different owners and different
lifetimes. Fabric profiles are ours, versioned with the engine, changed by
release. Machine profiles belong to the designer: they are measured on the
floor, they differ between two machines of the same model, and they are
expected to be edited. Shipped files are templates to copy, not values to
trust -- point V2S_MACHINE_DIR at your own directory and edit freely.

What a machine profile can and cannot do:

* It CAN change the worksheet, the speed ceiling, the tension targets, and
  whether the engine agrees to produce a file at all.
* It CANNOT change a stitch coordinate. Hardware differences are handled by
  refusing or warning, never by quietly re-generating a design differently --
  otherwise the same design on two machines stops being the same design.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

_SHIPPED_DIR = Path(__file__).parent / "data"
_FILE = re.compile(r"^(?P<name>[a-z0-9_]+)@(?P<version>\d+)\.yaml$")
_ENV_DIR = "V2S_MACHINE_DIR"
"""A shop's own machine directory. Searched before the shipped templates."""


class MachineNotFound(LookupError):
    """No machine profile by that reference on the search path."""


class Speed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_spm_flat: int = Field(gt=0)
    max_spm_cap: int = Field(gt=0)
    """Caps run slower than flat goods on every machine; how much slower is a
    property of the hardware, so it is measured here rather than assumed."""


class SewField(BaseModel):
    """The usable field, in millimetres. Not the hoop -- the machine's reach."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    flat_width_mm: float = Field(gt=0)
    flat_height_mm: float = Field(gt=0)
    cap_width_mm: float | None = Field(default=None, gt=0)
    cap_height_mm: float | None = Field(default=None, gt=0)


class Capabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    auto_trim: bool
    cap_driver: bool
    formats: list[str]
    """Formats this machine's controller reads. Lower-case extensions."""

    @model_validator(mode="after")
    def _formats_are_lowercase(self) -> Capabilities:
        if any(fmt != fmt.lower().lstrip(".") for fmt in self.formats):
            raise ValueError("formats are bare lower-case extensions, e.g. dst")
        return self


class LocalTension(BaseModel):
    """Gauge readings taken on this machine.

    Present once someone has actually measured; absent until then, in which
    case the fabric profile's generic values are used and the worksheet says so.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    bobbin_gf_min: float = Field(gt=0)
    bobbin_gf_max: float = Field(gt=0)
    top_to_bobbin_ratio: float = Field(gt=0)

    @model_validator(mode="after")
    def _range_is_a_range(self) -> LocalTension:
        if self.bobbin_gf_min > self.bobbin_gf_max:
            raise ValueError("bobbin tension min exceeds max")
        return self


class MachineProfile(BaseModel):
    """One machine on one floor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    version: int = Field(ge=1)
    description: str
    vendor: str = ""
    model: str = ""
    calibrated: bool = False
    """Set true once these numbers came off this machine rather than a spec
    sheet. The worksheet says which."""

    heads: int = Field(ge=1)
    needles_per_head: int = Field(ge=1)
    speed: Speed
    fields: SewField
    capabilities: Capabilities
    tension: LocalTension | None = None

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"

    @model_validator(mode="after")
    def _cap_driver_has_a_cap_field(self) -> MachineProfile:
        if self.capabilities.cap_driver and (
            self.fields.cap_width_mm is None or self.fields.cap_height_mm is None
        ):
            raise ValueError("a machine with a cap driver needs a cap field size")
        return self


def search_path(extra_dir: str | Path | None = None) -> list[Path]:
    """Where machine profiles are looked for, nearest first.

    An explicit directory beats the shop's V2S_MACHINE_DIR, which beats the
    templates shipped with the engine. A shop overrides a shipped name simply
    by putting its own file earlier on the path.
    """
    path = []
    if extra_dir:
        path.append(Path(extra_dir))
    env_dir = os.environ.get(_ENV_DIR)
    if env_dir:
        path.append(Path(env_dir))
    path.append(_SHIPPED_DIR)
    return [directory for directory in path if directory.is_dir()]


def _parse_ref(ref: str) -> tuple[str, int | None]:
    match = re.match(r"^(?P<name>[a-z0-9_]+)(?:@(?P<version>\d+))?$", ref.strip())
    if not match:
        raise MachineNotFound(f"malformed machine reference: {ref!r}")
    version = match.group("version")
    return match.group("name"), int(version) if version else None


def load_machine(ref: str, extra_dir: str | Path | None = None) -> MachineProfile:
    """Load a machine profile by reference, e.g. "multineedle_6head@1".

    An unpinned name takes the newest version in the first directory on the
    search path that has the machine at all -- a shop's own file shadows a
    shipped template completely, rather than merging with it.
    """
    name, want_version = _parse_ref(ref)
    directories = search_path(extra_dir)

    for directory in directories:
        versions = _versions_of(name, directory)
        if not versions:
            continue
        version = want_version if want_version is not None else max(versions)
        if version not in versions:
            raise MachineNotFound(
                f"machine {name!r} in {directory} has versions {sorted(versions)}, "
                f"pinned @{version}"
            )
        path = directory / f"{name}@{version}.yaml"
        machine = MachineProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if (machine.name, machine.version) != (name, version):
            raise MachineNotFound(
                f"{path} declares {machine.name}@{machine.version}, expected {name}@{version}"
            )
        return machine

    searched = ", ".join(str(directory) for directory in directories)
    raise MachineNotFound(
        f"no machine profile for {name!r} on the search path ({searched}). "
        f"Copy a shipped template, edit it for your machine, and set {_ENV_DIR}."
    )


def _versions_of(name: str, directory: Path) -> set[int]:
    found = set()
    for path in directory.glob(f"{name}@*.yaml"):
        match = _FILE.match(path.name)
        if match and match.group("name") == name:
            found.add(int(match.group("version")))
    return found


def available_machines(extra_dir: str | Path | None = None) -> list[tuple[str, Path]]:
    """Every machine reference on the search path, with the file behind it.

    Nearer directories shadow further ones, so what comes back is what would
    actually load.
    """
    seen: dict[str, Path] = {}
    for directory in search_path(extra_dir):
        for path in sorted(directory.glob("*.yaml")):
            match = _FILE.match(path.name)
            if not match:
                continue
            ref = f"{match.group('name')}@{match.group('version')}"
            seen.setdefault(ref, path)
    return sorted(seen.items())
