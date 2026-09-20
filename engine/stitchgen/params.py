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
    max_width_mm: float = 0.0
    short_stitch: bool = True
    short_stitch_min_spacing_mm: float = 0.0
    short_stitch_depth: float = 0.0
    split_overlap_mm: float = 0.0
    underlay_inset_mm: float = 0.0
    underlay_run_length_mm: float = 0.0
    underlay_zigzag_spacing_mm: float = 0.0


def resolve(
    obj: EmbroideryObject, profile: FabricProfile, width_mm: float | None = None
) -> ResolvedParams:
    """Resolve one object's parameters against a fabric profile.

    `width_mm` is the object's measured column width, which the profile needs
    in order to pick an underlay recipe: a 1.5 mm satin and a 6 mm satin want
    different things underneath. Geometry is measured by the caller, because
    this module deliberately knows nothing about shapes.
    """
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

    default_underlay: list[str] = []
    if obj.kind is ObjectKind.SATIN and width_mm is not None:
        default_underlay = profile.underlay.for_satin(width_mm)

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
        underlay=list(pick("underlay", obj.params.underlay, default_underlay)),
        source=source,
        max_width_mm=float(
            pick("max_width_mm", obj.params.max_width_mm, profile.classification.satin_max_width_mm)
        ),
        short_stitch=bool(pick("short_stitch", obj.params.short_stitch, True)),
        short_stitch_min_spacing_mm=profile.satin.short_stitch_min_spacing_mm,
        short_stitch_depth=profile.satin.short_stitch_depth,
        split_overlap_mm=profile.satin.split_overlap_mm,
        underlay_inset_mm=profile.underlay.inset_mm,
        # Underlay runs are runs, whatever the object on top of them is. A
        # satin's own stitch_length_mm defaults to the fill length, which would
        # put 3.5 mm steps under a 2 mm column.
        underlay_run_length_mm=profile.stitch.run_length_mm,
        underlay_zigzag_spacing_mm=(
            profile.density.satin_spacing_mm * profile.underlay.zigzag_spacing_multiplier
        ),
    )
