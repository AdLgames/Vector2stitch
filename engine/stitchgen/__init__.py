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
from engine.stitchgen.params import ResolvedParams, resolve
from engine.stitchgen.run import stitch_run, tie_points

__all__ = ["UnsupportedObject", "generate", "resolve", "ResolvedParams"]


class UnsupportedObject(NotImplementedError):
    """The engine will not guess at an object kind it cannot do well.

    Refusing loudly is the point: a confident bad file is the worst outcome.
    """


_MILESTONE_FOR_KIND = {
    ObjectKind.SATIN: "M1",
    ObjectKind.FILL: "M1",
    ObjectKind.TEXT: "M6",
}


def _object_points(obj: EmbroideryObject, params: ResolvedParams) -> list[tuple[float, float]]:
    """Penetrations for one object, in order, before travel and ties."""
    if obj.kind is not ObjectKind.RUN:
        milestone = _MILESTONE_FOR_KIND[obj.kind]
        raise UnsupportedObject(
            f"object {obj.id!r}: {obj.kind.value} stitching lands in {milestone}; "
            "this engine build generates run objects only"
        )
    return stitch_run(
        list(obj.shape.points),
        closed=obj.shape.closed,
        target_length_mm=params.stitch_length_mm,
        min_length_mm=params.min_stitch_length_mm,
        max_length_mm=params.max_stitch_length_mm,
        bean_repeats=params.bean_repeats,
    )


def generate(doc: IRDocument, profile: FabricProfile | None = None) -> StitchPlan:
    """Turn a design into a stitch plan.

    Travel between objects becomes a trim when it is longer than the profile's
    threshold, and a jump otherwise. Hiding travel under later objects is the
    sequencer's job (M4); until then every gap is an honest jump or trim.
    """
    profile = profile or load_profile(doc.design.fabric_profile)
    plan = StitchPlan(profile_ref=profile.ref, engine_version=doc.engine_version)

    threads: list[PlanThread] = []
    current_thread: str | None = None
    last_point: tuple[float, float] | None = None

    for obj in doc.ordered_objects():
        params = resolve(obj, profile)
        points = _object_points(obj, params)
        if not points:
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

        start = points[0]
        if last_point is not None:
            travel = math.hypot(start[0] - last_point[0], start[1] - last_point[1])
            if travel > profile.routing.trim_threshold_mm:
                plan.stitches.append(
                    PlanStitch(
                        x_mm=last_point[0], y_mm=last_point[1], cmd=Cmd.TRIM, object_id=obj.id
                    )
                )
            if travel > 0:
                plan.stitches.append(
                    PlanStitch(x_mm=start[0], y_mm=start[1], cmd=Cmd.JUMP, object_id=obj.id)
                )

        tie_in = tie_points(start, points[1], params.tie_length_mm, params.tie_stitches)
        for point in tie_in:
            plan.stitches.append(
                PlanStitch(x_mm=point[0], y_mm=point[1], object_id=obj.id)
            )

        for point in points:
            plan.stitches.append(
                PlanStitch(x_mm=point[0], y_mm=point[1], object_id=obj.id)
            )

        tie_off = tie_points(points[-1], points[-2], params.tie_length_mm, params.tie_stitches)
        for point in tie_off:
            plan.stitches.append(
                PlanStitch(x_mm=point[0], y_mm=point[1], object_id=obj.id)
            )

        last_point = points[-1]

    if last_point is not None:
        plan.stitches.append(PlanStitch(x_mm=last_point[0], y_mm=last_point[1], cmd=Cmd.END))
    plan.threads = threads
    return plan
