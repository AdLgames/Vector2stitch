"""Shared fixtures.

The engine version is pinned for the whole test session: it is stamped into
every IR document and stitch plan, and the determinism tests compare bytes.
"""

from __future__ import annotations

import os

os.environ.setdefault("V2S_ENGINE_VERSION", "test")

import pytest  # noqa: E402

from engine.ir.schema import (  # noqa: E402
    Design,
    EmbroideryObject,
    IRDocument,
    ObjectKind,
    Placement,
    PolylineShape,
    Thread,
)
from engine.profiles.loader import load_profile  # noqa: E402

BLACK = Thread(chart="madeira_polyneon_40", code="1800", rgb="#1a1a1a", description="Black")
RED = Thread(chart="madeira_polyneon_40", code="1147", rgb="#c8102e", description="Scarlet")


def run_object(object_id: str, points: list[tuple[float, float]], **kwargs) -> EmbroideryObject:
    """A run object with sane defaults, for tests that care about one thing."""
    return EmbroideryObject(
        id=object_id,
        kind=ObjectKind.RUN,
        shape=PolylineShape(points=points, closed=kwargs.pop("closed", False)),
        thread=kwargs.pop("thread", BLACK),
        **kwargs,
    )


def design(objects: list[EmbroideryObject], profile_ref: str = "twill@1") -> IRDocument:
    return IRDocument(
        design=Design(
            width_mm=90.0,
            height_mm=40.0,
            placement=Placement.LEFT_CHEST,
            fabric_profile=profile_ref,
            thread_brand="madeira_polyneon_40",
        ),
        objects=objects,
    )


@pytest.fixture
def twill():
    return load_profile("twill@1")


@pytest.fixture
def single_run_design() -> IRDocument:
    """The M0 acceptance shape: one run object, two corners."""
    return design([run_object("obj_001", [(0, 0), (20, 0), (30, 15), (40, 0), (60, 0)])])


@pytest.fixture
def two_color_design() -> IRDocument:
    """Two objects far apart in two colours: exercises trim, jump, colour change."""
    return design(
        [
            run_object("obj_001", [(0, 0), (20, 0)]),
            run_object("obj_002", [(60, 30), (80, 30)], thread=RED, z_order=1),
        ]
    )
