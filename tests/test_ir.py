"""IR schema: the contract every other module depends on."""

from __future__ import annotations

import json

import pytest
from conftest import BLACK, design, run_object
from pydantic import ValidationError

from engine.ir.migrate import UnknownSchemaVersion, migrate
from engine.ir.schema import (
    EmbroideryObject,
    FillShape,
    IRDocument,
    ObjectKind,
    ObjectParams,
    ParamSource,
    PolylineShape,
    load_ir,
    save_ir,
)
from engine.version import SCHEMA_VERSION


def test_document_round_trips_through_json(tmp_path, single_run_design):
    path = save_ir(single_run_design, tmp_path / "d.ir.json")
    assert load_ir(path) == single_run_design


def test_saved_ir_is_byte_stable(tmp_path, single_run_design):
    first = save_ir(single_run_design, tmp_path / "a.json").read_bytes()
    second = save_ir(single_run_design, tmp_path / "b.json").read_bytes()
    assert first == second


def test_saved_ir_has_sorted_keys_so_diffs_are_readable(tmp_path, single_run_design):
    raw = save_ir(single_run_design, tmp_path / "d.json").read_text()
    payload = json.loads(raw)
    assert list(payload) == sorted(payload)


def test_shape_must_match_object_kind():
    with pytest.raises(ValidationError, match="takes shape"):
        EmbroideryObject(
            id="obj_001",
            kind=ObjectKind.FILL,
            shape=PolylineShape(points=[(0, 0), (1, 1)]),
            thread=BLACK,
        )


def test_fill_object_accepts_a_polygon():
    obj = EmbroideryObject(
        id="obj_001",
        kind=ObjectKind.FILL,
        shape=FillShape(outer=[(0, 0), (10, 0), (10, 10)]),
        thread=BLACK,
    )
    assert obj.shape.kind == "polygon"


def test_param_source_must_name_real_params():
    with pytest.raises(ValidationError, match="unknown params"):
        EmbroideryObject(
            id="obj_001",
            kind=ObjectKind.RUN,
            shape=PolylineShape(points=[(0, 0), (1, 1)]),
            thread=BLACK,
            param_source={"dentistry_mm": ParamSource.HUMAN},
        )


def test_duplicate_object_ids_are_rejected():
    with pytest.raises(ValidationError, match="duplicate object ids"):
        design([run_object("obj_001", [(0, 0), (1, 0)]), run_object("obj_001", [(2, 0), (3, 0)])])


def test_sequence_must_cover_every_object():
    doc = design([run_object("obj_001", [(0, 0), (1, 0)]), run_object("obj_002", [(2, 0), (3, 0)])])
    with pytest.raises(ValidationError, match="exactly once"):
        IRDocument(
            design=doc.design,
            objects=doc.objects,
            sequence=["obj_001"],
        )


def test_ordered_objects_falls_back_to_z_order_then_id():
    doc = design(
        [
            run_object("obj_b", [(0, 0), (1, 0)], z_order=2),
            run_object("obj_a", [(2, 0), (3, 0)], z_order=2),
            run_object("obj_c", [(4, 0), (5, 0)], z_order=1),
        ]
    )
    assert [o.id for o in doc.ordered_objects()] == ["obj_c", "obj_a", "obj_b"]


def test_explicit_sequence_wins_over_z_order():
    doc = design([run_object("obj_a", [(0, 0), (1, 0)]), run_object("obj_b", [(2, 0), (3, 0)])])
    resequenced = IRDocument(
        design=doc.design, objects=doc.objects, sequence=["obj_b", "obj_a"]
    )
    assert [o.id for o in resequenced.ordered_objects()] == ["obj_b", "obj_a"]


def test_params_reject_unknown_fields():
    with pytest.raises(ValidationError):
        ObjectParams(density_mm=0.4, sparkle=True)


def test_migrate_passes_current_schema_through():
    payload = {"schema_version": SCHEMA_VERSION, "anything": 1}
    assert migrate(payload) == payload


def test_migrate_refuses_an_unknown_schema():
    with pytest.raises(UnknownSchemaVersion, match="no migration path"):
        migrate({"schema_version": "0.9"})


def test_migrate_refuses_a_document_with_no_version():
    with pytest.raises(UnknownSchemaVersion, match="no schema_version"):
        migrate({})
