"""Stitch generation: IR objects in, a stitch plan out.

Deterministic by construction. The same IR and the same profile produce the
same plan, on any host, every time -- objects are walked in sew order, never in
dict or set order, and no generator draws on a random source.
"""

from __future__ import annotations

import math

from engine.ir.schema import EmbroideryObject, IRDocument, ObjectKind
from engine.plan import Cmd, PlanStitch, PlanThread, StitchPlan
from engine.profiles.loader import FabricProfile, load_profile
from engine.stitchgen.fill import FillSpec, stitch_fill
from engine.stitchgen.geometry import distance
from engine.stitchgen.offset import offset_ring
from engine.stitchgen.params import ResolvedParams, resolve
from engine.stitchgen.run import stitch_run, tie_points
from engine.stitchgen.satin import SatinSpec, rail_pairs, sample_count, stitch_satin
from engine.stitchgen.underlay import FillUnderlaySpec, UnderlaySpec, fill_underlay, satin_underlay

__all__ = [
    "ResolvedParams",
    "UnsupportedObject",
    "UnsupportedProfile",
    "generate",
    "resolve",
]

CALIBRATED_THREAD_WEIGHT_WT = 40
"""The thread weight the geometry assumes.

Density, underlay and compensation defaults are all sized to what 40 wt
covers. Sewing a file digitized for 40 wt with 60 wt leaves gaps; the reverse
over-stitches and breaks thread. Supporting another weight means recalibrating
those numbers, not just changing the cone.
"""


class UnsupportedProfile(NotImplementedError):
    """The profile asks for something the generators are not calibrated for."""


class UnsupportedObject(NotImplementedError):
    """The engine will not guess at an object kind it cannot do well.

    Refusing loudly is the point: a confident bad file is the worst outcome.
    """


_MILESTONE_FOR_KIND = {
    ObjectKind.TEXT: "M6",
}


def mean_column_width(obj: EmbroideryObject, samples: int = 16) -> float:
    """Average width of a satin column, used to pick its underlay recipe."""
    left, right = obj.shape.rails
    pairs = rail_pairs(list(left), list(right), samples)
    return sum(distance(a, b) for a, b in pairs) / len(pairs)


def _satin_paths(obj: EmbroideryObject, params: ResolvedParams) -> list[list[tuple[float, float]]]:
    """Underlay layers first, then the column itself.

    Each layer is its own path: the plan assembler decides how to travel
    between them, the same way it decides between objects.
    """
    left, right = [list(rail) for rail in obj.shape.rails]

    underlay_spec = UnderlaySpec(
        inset_mm=params.underlay_inset_mm,
        run_length_mm=params.underlay_run_length_mm,
        zigzag_spacing_mm=params.underlay_zigzag_spacing_mm,
        min_length_mm=params.min_stitch_length_mm,
        max_width_mm=params.max_width_mm,
        split_overlap_mm=params.split_overlap_mm,
    )
    underlay_pairs = rail_pairs(
        left, right, sample_count(left, right, underlay_spec.run_length_mm)
    )
    paths = satin_underlay(params.underlay, underlay_pairs, underlay_spec)

    paths.append(
        stitch_satin(
            left,
            right,
            SatinSpec(
                spacing_mm=params.density_mm,
                pull_comp_mm_per_side=params.pull_comp_mm_per_side,
                max_width_mm=params.max_width_mm,
                short_stitch=params.short_stitch,
                short_stitch_min_spacing_mm=params.short_stitch_min_spacing_mm,
                short_stitch_depth=params.short_stitch_depth,
                split_overlap_mm=params.split_overlap_mm,
                min_length_mm=params.min_stitch_length_mm,
            ),
        )
    )
    return paths


def _fill_paths(obj: EmbroideryObject, params: ResolvedParams) -> list[list[tuple[float, float]]]:
    """Underlay layers first, then the fill itself."""
    outer = list(obj.shape.outer)
    holes = [list(hole) for hole in obj.shape.holes]

    # Grow the holes before anything is generated. Scanline sampling can clip
    # a hole's corner by up to half a row spacing, and a window that is
    # supposed to be bare fabric is not the place to spend that tolerance.
    stitched_holes = [
        grown
        for hole in holes
        for grown in offset_ring(hole, params.hole_clearance_mm)
    ] if params.hole_clearance_mm > 0 else holes

    paths = fill_underlay(
        params.underlay,
        outer,
        stitched_holes,
        FillUnderlaySpec(
            inset_mm=params.underlay_inset_mm,
            run_length_mm=params.underlay_run_length_mm,
            tatami_spacing_mm=params.underlay_tatami_spacing_mm,
            tatami_angle_deg=params.underlay_tatami_angle_deg,
            stagger_steps=params.stagger_steps,
            min_length_mm=params.min_stitch_length_mm,
            min_span_mm=params.min_span_mm,
        ),
    )

    paths += stitch_fill(
        outer,
        stitched_holes,
        FillSpec(
            row_spacing_mm=params.density_mm,
            stitch_length_mm=params.stitch_length_mm,
            min_length_mm=params.min_stitch_length_mm,
            angle_deg=params.angle_deg,
            stagger_steps=params.stagger_steps,
            pull_comp_mm_per_side=params.pull_comp_mm_per_side,
            push_comp_mm=params.push_comp_mm,
            min_span_mm=params.min_span_mm,
        ),
    )
    return paths


def _object_paths(
    obj: EmbroideryObject, params: ResolvedParams
) -> list[list[tuple[float, float]]]:
    """Every path one object sews, in order, before travel and ties."""
    if obj.kind is ObjectKind.RUN:
        return [
            stitch_run(
                list(obj.shape.points),
                closed=obj.shape.closed,
                target_length_mm=params.stitch_length_mm,
                min_length_mm=params.min_stitch_length_mm,
                max_length_mm=params.max_stitch_length_mm,
                bean_repeats=params.bean_repeats,
            )
        ]
    if obj.kind is ObjectKind.SATIN:
        return _satin_paths(obj, params)
    if obj.kind is ObjectKind.FILL:
        return _fill_paths(obj, params)

    milestone = _MILESTONE_FOR_KIND[obj.kind]
    raise UnsupportedObject(
        f"object {obj.id!r}: {obj.kind.value} stitching lands in {milestone}; "
        f"this engine build generates run, satin and fill objects"
    )


def generate(
    doc: IRDocument,
    profile: FabricProfile | None = None,
    overrides: list[str] | None = None,
) -> StitchPlan:
    """Turn a design into a stitch plan.

    Travel between objects becomes a trim when it is longer than the profile's
    threshold, and a jump otherwise. Hiding travel under later objects is the
    sequencer's job (M4); until then every gap is an honest jump or trim.

    `overrides` names the profile fields a shop changed, so the plan -- and the
    delivered file -- record that they ran something other than our defaults.
    Passing an already-overridden profile without them produces stitches that
    cannot be explained later, so the CLI always passes both together.
    """
    profile = profile or load_profile(doc.design.fabric_profile)
    if profile.machine.thread_weight_wt != CALIBRATED_THREAD_WEIGHT_WT:
        raise UnsupportedProfile(
            f"{profile.ref} specifies {profile.machine.thread_weight_wt} wt thread, but the "
            f"generators are calibrated for {CALIBRATED_THREAD_WEIGHT_WT} wt. Densities, "
            "underlay and compensation all have to be re-derived for another weight -- "
            "fine lettering on 60 wt is M6."
        )
    plan = StitchPlan(
        profile_ref=profile.ref,
        profile_overrides=sorted(overrides or []),
        engine_version=doc.engine_version,
    )

    threads: list[PlanThread] = []
    current_thread: str | None = None
    last_point: tuple[float, float] | None = None
    last_tail: tuple[tuple[float, float], tuple[float, float]] | None = None
    """The last path's final penetration and the one before it -- the anchor
    and heading a tie-off needs."""
    tied_off = False
    """Whether the thread is already tied where it currently sits. An object
    ends with a tie-off, and the next object's trim must not add a second one
    on top of it: two ties in one place is a stiff lump and a density
    hotspot, not twice the security."""

    for obj in doc.ordered_objects():
        width_mm = mean_column_width(obj) if obj.kind is ObjectKind.SATIN else None
        params = resolve(obj, profile, width_mm)
        paths = [path for path in _object_paths(obj, params) if len(path) >= 2]
        if not paths:
            continue

        thread_key = f"{obj.thread.chart}:{obj.thread.code}"
        if thread_key != current_thread:
            if current_thread is not None:
                plan.stitches.append(
                    PlanStitch(
                        x_mm=last_point[0],
                        y_mm=last_point[1],
                        cmd=Cmd.COLOR_CHANGE,
                        object_id=obj.id,
                    )
                )
            threads.append(
                PlanThread(
                    chart=obj.thread.chart,
                    code=obj.thread.code,
                    rgb=obj.thread.rgb,
                    description=obj.thread.description,
                )
            )
            current_thread = thread_key

        for path_index, points in enumerate(paths):
            start = points[0]
            trimmed = False
            if last_point is not None:
                travel = math.hypot(start[0] - last_point[0], start[1] - last_point[1])
                if travel > profile.routing.trim_threshold_mm:
                    needs_tie = not tied_off
                    # Tie off before the trim, not just at the object's end.
                    # Thread cut without a tie pulls straight back out, and an
                    # object with underlay trims several times before it ends.
                    for point in (
                        tie_points(
                            last_tail[0], last_tail[1], params.tie_length_mm, params.tie_stitches
                        )
                        if needs_tie
                        else []
                    ):
                        plan.stitches.append(
                            PlanStitch(x_mm=point[0], y_mm=point[1], object_id=obj.id)
                        )
                    plan.stitches.append(
                        PlanStitch(
                            x_mm=last_tail[0][0],
                            y_mm=last_tail[0][1],
                            cmd=Cmd.TRIM,
                            object_id=obj.id,
                        )
                    )
                    trimmed = True
                if travel > 0:
                    plan.stitches.append(
                        PlanStitch(x_mm=start[0], y_mm=start[1], cmd=Cmd.JUMP, object_id=obj.id)
                    )

            emit = points
            # A tie-in belongs wherever thread starts: at the object's first
            # path, and again after any trim that cut it.
            if path_index == 0 or trimmed:
                tie_in = tie_points(
                    start, points[1], params.tie_length_mm, params.tie_stitches
                )
                for point in tie_in:
                    plan.stitches.append(
                        PlanStitch(x_mm=point[0], y_mm=point[1], object_id=obj.id)
                    )
                # The tie ends on the anchor, which is also the path's first
                # point. Emitting both puts two stitches in one hole.
                if tie_in and tie_in[-1] == points[0]:
                    emit = points[1:]

            for point in emit:
                plan.stitches.append(
                    PlanStitch(x_mm=point[0], y_mm=point[1], object_id=obj.id)
                )
            tied_off = False

            if path_index == len(paths) - 1:
                for point in tie_points(
                    points[-1], points[-2], params.tie_length_mm, params.tie_stitches
                ):
                    plan.stitches.append(
                        PlanStitch(x_mm=point[0], y_mm=point[1], object_id=obj.id)
                    )

                tied_off = True

            last_point = points[-1]
            last_tail = (points[-1], points[-2])

    if last_point is not None:
        plan.stitches.append(PlanStitch(x_mm=last_point[0], y_mm=last_point[1], cmd=Cmd.END))
    plan.threads = threads
    return plan
