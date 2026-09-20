"""The CLI: one entry point for the lab, the golden suite and a developer."""

from __future__ import annotations

from pathlib import Path

from engine.cli.main import EXIT_ERROR, EXIT_NOT_YET_BUILT, EXIT_OK, main
from engine.ir.schema import (
    Design,
    EmbroideryObject,
    IRDocument,
    ObjectKind,
    Placement,
    PolylineShape,
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
    """Text is all that is left: it needs embroidery fonts, which are M6."""
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
                kind=ObjectKind.TEXT,
                shape=PolylineShape(points=[(0, 0), (20, 0)]),
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


def test_unbuilt_commands_say_so_distinctly(capsys):
    """Exit 3 is "not built yet", not "broken": scripts can tell them apart."""
    assert main(["check"]) == EXIT_NOT_YET_BUILT
    assert "M2" in capsys.readouterr().err


def test_calibrate_lists_what_is_ready_and_what_is_waiting(capsys):
    assert main(["calibrate", "--list"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "dimension_grid" in out and "ready" in out
    assert "text_ladder" in out and "needs M6" in out


def test_calibrate_writes_files_to_sew_and_a_sheet_to_measure_on(tmp_path, capsys):
    code = main(
        [
            "calibrate",
            "--profile",
            "twill@1",
            "--out",
            str(tmp_path),
            "--patterns",
            "dimension_grid",
            "--formats",
            "dst",
        ]
    )
    assert code == EXIT_OK
    out_dir = tmp_path / "twill_at_1"
    for suffix in (".ir.json", ".dst", ".worksheet.txt", ".measure.txt", ".targets.json"):
        assert (out_dir / f"dimension_grid{suffix}").exists()
    sheet = (out_dir / "dimension_grid.measure.txt").read_text()
    assert "square_01_x" in sheet and "designed" in sheet
    assert "Stabilizer" in sheet
    assert "is calibration until it has been sewn" in capsys.readouterr().out


def test_calibrate_skips_a_pattern_that_needs_generators_we_lack(tmp_path, capsys):
    """Only text is left, and it needs licensed embroidery fonts (M6)."""
    code = main(
        [
            "calibrate",
            "--profile",
            "twill@1",
            "--out",
            str(tmp_path),
            "--patterns",
            "text_ladder",
        ]
    )
    assert code == EXIT_OK
    assert "needs generators that land in M6" in capsys.readouterr().err


def test_cap_calibration_fits_the_cap_field(tmp_path, capsys):
    """A cap front is about 70 mm tall. A pattern that cannot be hooped
    measures nothing, so the cap set is built to fit it."""
    code = main(
        [
            "calibrate",
            "--profile",
            "cap@1",
            "--out",
            str(tmp_path),
            "--machine",
            "multineedle_6head@1",
            "--formats",
            "dst",
        ]
    )
    assert code == EXIT_OK
    assert "skipped" not in capsys.readouterr().err
    assert (tmp_path / "cap_at_1" / "dimension_grid.dst").exists()


def test_worksheet_carries_the_machine_setup(tmp_path):
    """Thread, needle, speed and tension, so the operator is not guessing."""
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
    assert "MACHINE SETUP" in sheet
    assert "40 wt polyester" in sheet
    assert "75/11" in sheet
    assert "Bobbin tension" in sheet and "gf (generic)" in sheet


def test_machines_lists_the_templates(capsys):
    assert main(["machines"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "multineedle_6head@1" in out
    assert "single_head@1" in out


def test_digitize_against_a_machine_notes_what_the_operator_must_know(tmp_path, capsys):
    code = main(
        [
            "digitize",
            str(EXAMPLES / "m0_two_color_run.ir.json"),
            "--out",
            str(tmp_path),
            "--formats",
            "dst",
            "--machine",
            "single_head@1",
        ]
    )
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "no auto trimmer" in out
    assert "single_head@1" in (tmp_path / "m0_two_color_run.worksheet.txt").read_text()


def test_digitize_writes_nothing_when_the_design_cannot_sew_there(tmp_path, capsys):
    """A cap on a machine with no cap driver: refused, and no half-delivery
    left in the output directory for someone to pick up by mistake."""
    raw = (EXAMPLES / "m0_single_run.ir.json").read_text()
    raw = raw.replace('"left_chest"', '"cap_front"').replace("twill@1", "cap@1")
    path = tmp_path / "cap.ir.json"
    path.write_text(raw)

    code = main(
        ["digitize", str(path), "--out", str(tmp_path / "out"), "--machine", "single_head@1"]
    )
    assert code == EXIT_ERROR
    assert "cap driver" in capsys.readouterr().err
    assert not list((tmp_path / "out").glob("*.dst")) if (tmp_path / "out").exists() else True


def test_an_unknown_machine_is_an_error_not_a_silent_default(tmp_path, capsys):
    code = main(
        [
            "digitize",
            str(EXAMPLES / "m0_single_run.ir.json"),
            "--out",
            str(tmp_path),
            "--machine",
            "not_a_machine",
        ]
    )
    assert code == EXIT_ERROR
    assert "no machine profile" in capsys.readouterr().err
