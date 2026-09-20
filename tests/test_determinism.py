"""Determinism.

The same input and settings always produce the same stitches. Without this,
the golden suite cannot regress-test anything, a customer complaint cannot be
reproduced, and "we changed nothing" is unprovable.

Two levels:

* Same process, twice -- catches dict/set iteration order and unseeded randomness.
* Against committed fingerprints -- catches host, OS and library differences,
  which is why CI runs this job on more than one OS image.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from engine.export import write
from engine.ir.schema import load_ir, save_ir
from engine.stitchgen import generate

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
FINGERPRINTS = json.loads((Path(__file__).parent / "fingerprints.json").read_text())
FORMATS = ["dst", "pes", "jef", "exp"]
DESIGNS = sorted(FINGERPRINTS)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("name", DESIGNS)
def test_generation_is_repeatable_in_one_process(name):
    doc = load_ir(EXAMPLES / f"{name}.ir.json")
    assert generate(doc).model_dump_json() == generate(doc).model_dump_json()


@pytest.mark.parametrize("name", DESIGNS)
@pytest.mark.parametrize("extension", FORMATS)
def test_written_files_are_byte_identical_across_writes(tmp_path, name, extension):
    plan = generate(load_ir(EXAMPLES / f"{name}.ir.json"))
    first = write(plan, tmp_path / f"a.{extension}").read_bytes()
    second = write(plan, tmp_path / f"b.{extension}").read_bytes()
    assert _sha(first) == _sha(second)


@pytest.mark.parametrize("name", DESIGNS)
def test_plan_matches_its_committed_fingerprint(name):
    """A changed fingerprint means engine output moved.

    That is allowed -- it is how the engine improves -- but it is never
    incidental: regenerate `tests/fingerprints.json`, and say in the PR what
    moved and why, with digitizer sign-off once the golden suite exists (M2).
    """
    plan = generate(load_ir(EXAMPLES / f"{name}.ir.json"))
    assert _sha(plan.model_dump_json().encode()) == FINGERPRINTS[name]["plan_json"]


@pytest.mark.parametrize("name", DESIGNS)
@pytest.mark.parametrize("extension", FORMATS)
def test_written_file_matches_its_committed_fingerprint(tmp_path, name, extension):
    plan = generate(load_ir(EXAMPLES / f"{name}.ir.json"))
    data = write(plan, tmp_path / f"{name}.{extension}").read_bytes()
    assert _sha(data) == FINGERPRINTS[name][extension], (
        f"{extension} output changed for {name}: regenerate tests/fingerprints.json "
        "deliberately, or find out which change moved the stitches"
    )


@pytest.mark.parametrize("name", DESIGNS)
def test_ir_survives_a_save_load_cycle_unchanged(tmp_path, name):
    doc = load_ir(EXAMPLES / f"{name}.ir.json")
    reloaded = load_ir(save_ir(doc, tmp_path / "again.json"))
    assert reloaded == doc
    assert generate(reloaded).model_dump_json() == generate(doc).model_dump_json()
