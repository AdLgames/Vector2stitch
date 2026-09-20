"""Parameter resolution: object overrides first, fabric profile underneath.

Engine logic never substitutes its own constant. If an object leaves a
parameter unset, the value comes from the profile, and the resolution is
recorded so an edit log can say where a number came from.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.ir.schema import EmbroideryObject, ObjectKind, ParamSource
from engine.profiles.loader import FabricProfile


@dataclass(frozen=True)
class ResolvedParams:
    """The parameters a generator actually used, with their provenance."""

    stitch_length_mm: float
    min_stitch_length_mm: float
    max_stitch_length_mm: float
    density_mm: float
    pull_comp_mm_per_side: float
    bean_repeats: int
    tie_length_mm: float
    tie_stitches: int
    underlay: list[str]
    source: dict[str, ParamSource]


def resolve(obj: EmbroideryObject, profile: FabricProfile) -> ResolvedParams:
    """Resolve one object's parameters against a fabric profile."""
    source: dict[str, ParamSource] = {}

    def pick(field: str, override: object, fallback: object) -> object:
        """Object override wins; its declared provenance wins over a guess."""
        if override is not None:
            source[field] = obj.param_source.get(field, ParamSource.HUMAN)
            return override
        source[field] = ParamSource.PROFILE
        return fallback

    default_length = (
        profile.stitch.run_length_mm
        if obj.kind is ObjectKind.RUN
        else profile.stitch.fill_length_mm
    )
    default_density = (
        profile.density.satin_spacing_mm
        if obj.kind is ObjectKind.SATIN
        else profile.density.fill_row_spacing_mm
    )

    return ResolvedParams(
        stitch_length_mm=float(
            pick("stitch_length_mm", obj.params.stitch_length_mm, default_length)
        ),
        min_stitch_length_mm=float(
            pick(
                "min_stitch_length_mm",
                obj.params.min_stitch_length_mm,
                profile.stitch.min_length_mm,
            )
        ),
        max_stitch_length_mm=profile.stitch.max_length_mm,
        density_mm=float(pick("density_mm", obj.params.density_mm, default_density)),
        pull_comp_mm_per_side=float(
            pick(
                "pull_comp_mm_per_side",
                obj.params.pull_comp_mm_per_side,
                profile.compensation.pull_comp_mm_per_side,
            )
        ),
        bean_repeats=int(
            pick("bean_repeats", obj.params.bean_repeats, profile.stitch.bean_repeats)
        ),
        tie_length_mm=profile.stitch.tie_length_mm,
        tie_stitches=profile.stitch.tie_stitches,
        underlay=list(pick("underlay", obj.params.underlay, [])),
        source=source,
    )
