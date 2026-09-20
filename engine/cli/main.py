"""The engine CLI.

One entry point for the lab, the golden suite and a developer at a terminal.
The service calls the same library functions, never this module.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engine.cli.worksheet import worksheet
from engine.export import verify, write
from engine.ir.schema import load_ir
from engine.profiles.loader import ProfileNotFound, available_profiles, load_profile
from engine.simulate import render_file
from engine.stitchgen import UnsupportedObject, generate
from engine.version import SCHEMA_VERSION, engine_version

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOT_YET_BUILT = 3
"""A command that exists in the plan but not yet in the code. Distinct from a
real failure so scripts and CI can tell "broken" from "not built yet"."""

DEFAULT_FORMATS = ["dst", "pes"]


def _cmd_digitize(args: argparse.Namespace) -> int:
    """IR in, machine files out, every one of them round-trip verified."""
    doc = load_ir(args.ir)
    try:
        profile = load_profile(doc.design.fabric_profile)
    except ProfileNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        plan = generate(doc, profile)
    except UnsupportedObject as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_NOT_YET_BUILT

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.stem or Path(args.ir).stem.removesuffix(".ir")

    failed = False
    for fmt in args.formats:
        path = write(plan, out_dir / f"{stem}.{fmt}")
        report = verify(plan, path)
        print(report.summary())
        for problem in report.problems:
            print(f"  - {problem}", file=sys.stderr)
        failed = failed or not report.ok

    sheet = out_dir / f"{stem}.worksheet.txt"
    sheet.write_text(worksheet(doc, plan, profile), encoding="utf-8")
    print(f"{sheet.name}: written")

    if failed:
        print("error: at least one file did not survive round-trip", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


def _cmd_render(args: argparse.Namespace) -> int:
    """Render a written machine file, which is the only honest thing to render."""
    out = Path(args.out) if args.out else Path(args.file).with_suffix(".svg")
    render_file(args.file, out)
    print(f"{out}: written")
    return EXIT_OK


def _cmd_profiles(args: argparse.Namespace) -> int:
    for ref in available_profiles():
        profile = load_profile(ref)
        state = "calibrated" if profile.calibrated else "NOT calibrated"
        print(f"{ref:<12} {state:<15} {profile.description}")
    return EXIT_OK


def _cmd_check(args: argparse.Namespace) -> int:
    print(
        "check: the validators land in M2 (quality doc section 6.1). "
        "Until then every file goes through human review, without exception.",
        file=sys.stderr,
    )
    return EXIT_NOT_YET_BUILT


def _cmd_calibrate(args: argparse.Namespace) -> int:
    print(
        "calibrate: the calibration pattern generator lands in M1 "
        "(pull-comp targets, column ladders, text ladders, registration marks).",
        file=sys.stderr,
    )
    return EXIT_NOT_YET_BUILT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="v2s",
        description="Vector2stitch engine: artwork objects in, machine files out.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"engine {engine_version()}, IR schema {SCHEMA_VERSION}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    digitize = sub.add_parser("digitize", help="generate machine files from an IR document")
    digitize.add_argument("ir", help="path to an IR JSON document")
    digitize.add_argument("--out", default="out", help="output directory (default: out)")
    digitize.add_argument("--stem", default=None, help="output file stem (default: IR filename)")
    digitize.add_argument(
        "--formats",
        default=",".join(DEFAULT_FORMATS),
        type=lambda value: [part.strip().lower() for part in value.split(",") if part.strip()],
        help=f"comma-separated output formats (default: {','.join(DEFAULT_FORMATS)})",
    )
    digitize.set_defaults(func=_cmd_digitize)

    render = sub.add_parser("render", help="render a machine file to SVG")
    render.add_argument("file", help="path to a written machine file")
    render.add_argument("--out", default=None, help="output SVG path")
    render.set_defaults(func=_cmd_render)

    profiles = sub.add_parser("profiles", help="list available fabric profiles")
    profiles.set_defaults(func=_cmd_profiles)

    check = sub.add_parser("check", help="run the automated quality checks (M2)")
    check.add_argument("file", nargs="?", help="path to a machine file or IR document")
    check.set_defaults(func=_cmd_check)

    calibrate = sub.add_parser("calibrate", help="generate lab calibration patterns (M1)")
    calibrate.add_argument("--out", default="out", help="output directory")
    calibrate.set_defaults(func=_cmd_calibrate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
