"""The CLI: one entry point for the lab, the golden suite and a developer."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.cli.main import EXIT_ERROR, EXIT_NOT_YET_BUILT, EXIT_OK, main
from engine.ir.schema import (
    Design,
    EmbroideryObject,
    IRDocument,
    ObjectKind,
    Placement,
    RailsShape,
    save_ir,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_digitize_writes_files_and_a_worksheet(tmp_path, capsys):
    code = main(
        [
            "digitize",
            str(EXAMPLES / "m0_two_color_run.ir.json"),
            "--out",
            str(tmp_path),
            "--formats",
            "dst,pes",
        ]
    )
    assert code == EXIT_OK
    assert (tmp_path / "m0_two_color_run.dst").exists()
    assert (tmp_path / "m0_two_color_run.pes").exists()
    assert "ok --" in capsys.readouterr().out


def test_worksheet_tells_the_operator_what_to_hang(tmp_path):
    main(
        [
            "digitize",
            str(EXAMPLES / "m0_two_color_run.ir.json"),
            "--out",
            str(tmp_path),
            "--formats",
            "dst",
        ]
    )
    sheet = (tmp_path / "m0_two_color_run.worksheet.txt").read_text()
    assert "COLOUR SEQUENCE" in sheet
    assert "1147" in sheet and "1800" in sheet
    assert "Stabilizer" in sheet
    assert "Test sew on scrap" in sheet


def test_worksheet_says_when_the_profile_is_not_calibrated(tmp_path):
    main(
        [
            "digitize",
            str(EXAMPLES / "m0_single_run.ir.json"),
            "--out",
            str(tmp_path),
            "--formats",
            "dst",
        ]
    )
    sheet = (tmp_path / "m0_single_run.worksheet.txt").read_text()
    assert "NOT calibrated" in sheet


def test_digitize_refuses_an_unbuilt_object_kind(tmp_path, capsys):
    doc = IRDocument(
        design=Design(
            width_mm=40,
            height_mm=20,
            placement=Placement.LEFT_CHEST,
            fabric_profile="twill@1",
            thread_brand="madeira_polyneon_40",
        ),
        objects=[
            EmbroideryObject(
                id="obj_001",
                kind=ObjectKind.SATIN,
                shape=RailsShape(rails=([(0, 0), (20, 0)], [(0, 3), (20, 3)])),
                thread={"chart": "madeira_polyneon_40", "code": "1800", "rgb": "#1a1a1a"},
            )
        ],
    )
    path = save_ir(doc, tmp_path / "satin.ir.json")
    assert main(["digitize", str(path), "--out", str(tmp_path)]) == EXIT_NOT_YET_BUILT
    assert "refused" in capsys.readouterr().err


def test_digitize_refuses_a_design_pinned_to_a_missing_profile(tmp_path, capsys):
    raw = (EXAMPLES / "m0_single_run.ir.json").read_text().replace("twill@1", "twill@99")
    path = tmp_path / "pinned.ir.json"
    path.write_text(raw)
    assert main(["digitize", str(path), "--out", str(tmp_path)]) == EXIT_ERROR
    assert "pins @99" in capsys.readouterr().err


def test_render_writes_an_svg_next_to_the_file(tmp_path):
    main(
        [
            "digitize",
            str(EXAMPLES / "m0_single_run.ir.json"),
            "--out",
            str(tmp_path),
            "--formats",
            "dst",
        ]
    )
    assert main(["render", str(tmp_path / "m0_single_run.dst")]) == EXIT_OK
    assert (tmp_path / "m0_single_run.svg").exists()


def test_profiles_lists_what_v1_supports(capsys):
    assert main(["profiles"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "twill@1" in out and "pique@1" in out and "cap@1" in out


@pytest.mark.parametrize(
    ("argv", "needle"),
    [(["check"], "M2"), (["calibrate"], "M1")],
)
def test_unbuilt_commands_say_so_distinctly(capsys, argv, needle):
    """Exit 3 is "not built yet", not "broken": scripts can tell them apart."""
    assert main(argv) == EXIT_NOT_YET_BUILT
    assert needle in capsys.readouterr().err
