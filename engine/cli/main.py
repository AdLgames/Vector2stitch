"""The engine CLI.

One entry point for the lab, the golden suite and a developer at a terminal.
The service calls the same library functions, never this module.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engine.checks import run_checks
from engine.cli.worksheet import worksheet
from engine.export import verify, write
from engine.ir.schema import load_ir, save_ir
from engine.lab import PATTERNS, PatternNotAvailable, build_pattern, measurement_sheet
from engine.machines import MachineNotFound, available_machines, load_machine, resolve_setup
from engine.profiles.loader import ProfileNotFound, available_profiles, load_profile
from engine.profiles.overrides import (
    OverrideError,
    available_overrides,
    effective_profile,
    override_template,
)
from engine.simulate import render_file
from engine.stitchgen import UnsupportedObject, UnsupportedProfile, generate
from engine.version import SCHEMA_VERSION, engine_version

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOT_YET_BUILT = 3
"""A command that exists in the plan but not yet in the code. Distinct from a
real failure so scripts and CI can tell "broken" from "not built yet"."""
EXIT_BLOCKED = 5
"""The checks refused the file. Not a tool failure -- a verdict, and the one
that means this must not go on a machine."""

DEFAULT_FORMATS = ["dst", "pes"]


def _cmd_digitize(args: argparse.Namespace) -> int:
    """IR in, machine files out, every one of them round-trip verified."""
    doc = load_ir(args.ir)
    try:
        profile, overrides = effective_profile(doc.design.fabric_profile, args.profile_dir)
    except (ProfileNotFound, OverrideError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    for applied in overrides:
        flag = "  !! large change -- check this is not a typo" if applied.is_large else ""
        print(f"override: {applied.describe()}{flag}")

    machine = None
    if args.machine:
        try:
            machine = load_machine(args.machine, args.machine_dir)
        except MachineNotFound as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ERROR

    try:
        plan = generate(doc, profile, [applied.path for applied in overrides])
    except (UnsupportedObject, UnsupportedProfile) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_NOT_YET_BUILT

    setup = resolve_setup(profile, doc, plan, machine, args.formats)
    for warning in setup.warnings:
        print(f"note: {warning}")
    if not setup.ok:
        for blocker in setup.blockers:
            print(f"refused: {blocker}", file=sys.stderr)
        print(
            "error: this design will not sew on that machine; nothing written",
            file=sys.stderr,
        )
        return EXIT_ERROR

    report = run_checks(doc, plan, profile, setup)
    print(report.format())
    if not report.ok:
        print(
            "error: the checks refused this file; nothing written. "
            "Fix the objects or the profile -- not the stitches.",
            file=sys.stderr,
        )
        return EXIT_BLOCKED

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
    sheet.write_text(worksheet(doc, plan, profile, setup, overrides), encoding="utf-8")
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
        _, overrides = effective_profile(ref, args.profile_dir)
        for applied in overrides:
            print(f"{'':<12} override  {applied.describe()}")
    return EXIT_OK


def _cmd_override_init(args: argparse.Namespace) -> int:
    """Scaffold an override file for a shop to fill in."""
    try:
        profile = load_profile(args.profile)
    except ProfileNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{profile.ref}.override.yaml"
    if path.exists() and not args.force:
        print(f"error: {path} exists; pass --force to replace it", file=sys.stderr)
        return EXIT_ERROR

    path.write_text(override_template(profile, args.shop), encoding="utf-8")
    print(f"{path}: written")
    print("Uncomment what your floor disagrees with, set a value, and say why.")
    print(f"Then point --profile-dir or $V2S_PROFILE_DIR at {out_dir}.")
    return EXIT_OK


def _cmd_override_show(args: argparse.Namespace) -> int:
    """Show every override on the search path, and what it changes."""
    entries = available_overrides(args.profile_dir)
    if not entries:
        print("no override files found", file=sys.stderr)
        return EXIT_ERROR

    for ref, path in entries:
        print(f"{ref}  ({path})")
        try:
            _, overrides = effective_profile(ref, args.profile_dir)
        except (ProfileNotFound, OverrideError) as exc:
            print(f"  error: {exc}", file=sys.stderr)
            return EXIT_ERROR
        for applied in overrides:
            flag = "  !! large change" if applied.is_large else ""
            print(f"  {applied.path}: {applied.shipped} -> {applied.value}{flag}")
            print(f"    why: {applied.reason}")
            if applied.evidence:
                print(f"    evidence: {applied.evidence}")
            else:
                print("    evidence: none recorded -- experience, not measurement")
    return EXIT_OK


def _cmd_machines(args: argparse.Namespace) -> int:
    """List the machine profiles this shop has described."""
    entries = available_machines(args.machine_dir)
    if not entries:
        print("no machine profiles found", file=sys.stderr)
        return EXIT_ERROR
    for ref, path in entries:
        machine = load_machine(ref, args.machine_dir)
        state = "calibrated" if machine.calibrated else "template / not calibrated"
        cap = "cap driver" if machine.capabilities.cap_driver else "flat only"
        print(
            f"{ref:<24} {state:<26} {machine.heads}-head, "
            f"{machine.needles_per_head} needles, {cap}"
        )
        print(f"{'':<24} {path}")
    return EXIT_OK


def _cmd_check(args: argparse.Namespace) -> int:
    """Run the checks on a design without writing anything."""
    doc = load_ir(args.file)
    try:
        profile, overrides = effective_profile(doc.design.fabric_profile, args.profile_dir)
    except (ProfileNotFound, OverrideError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    machine = None
    if args.machine:
        try:
            machine = load_machine(args.machine, args.machine_dir)
        except MachineNotFound as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ERROR

    try:
        plan = generate(doc, profile, [applied.path for applied in overrides])
    except (UnsupportedObject, UnsupportedProfile) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_NOT_YET_BUILT

    setup = resolve_setup(profile, doc, plan, machine)
    report = run_checks(doc, plan, profile, setup)
    print(report.format(show_passes=args.verbose))
    return EXIT_OK if report.ok else EXIT_BLOCKED


def _cmd_calibrate(args: argparse.Namespace) -> int:
    """Generate the calibration set: files to sew, and sheets to measure on."""
    if args.list:
        for name, pattern in PATTERNS.items():
            state = "ready" if pattern.available else f"needs {pattern.requires}"
            print(f"{name:<22} {state:<12} {pattern.purpose}")
        return EXIT_OK

    try:
        profile, overrides = effective_profile(args.profile, args.profile_dir)
    except (ProfileNotFound, OverrideError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    for applied in overrides:
        print(f"override: {applied.describe()}")

    machine = None
    if args.machine:
        try:
            machine = load_machine(args.machine, args.machine_dir)
        except MachineNotFound as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ERROR

    wanted = args.patterns or [name for name, p in PATTERNS.items() if p.available]
    out_dir = Path(args.out) / profile.ref.replace("@", "_at_")
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    for name in wanted:
        try:
            doc, targets = build_pattern(name, profile.ref)
        except PatternNotAvailable as exc:
            print(f"skipped: {exc}", file=sys.stderr)
            skipped += 1
            continue
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ERROR

        plan = generate(doc, profile, [applied.path for applied in overrides])
        setup = resolve_setup(profile, doc, plan, machine, args.formats)
        if not setup.ok:
            for blocker in setup.blockers:
                print(f"skipped {name}: {blocker}", file=sys.stderr)
            skipped += 1
            continue

        save_ir(doc, out_dir / f"{name}.ir.json")
        for fmt in args.formats:
            path = write(plan, out_dir / f"{name}.{fmt}")
            report = verify(plan, path)
            if not report.ok:
                print(f"error: {report.summary()}", file=sys.stderr)
                return EXIT_ERROR

        (out_dir / f"{name}.worksheet.txt").write_text(
            worksheet(doc, plan, profile, setup, overrides), encoding="utf-8"
        )
        (out_dir / f"{name}.measure.txt").write_text(
            measurement_sheet(name, doc, profile, setup, targets), encoding="utf-8"
        )
        (out_dir / f"{name}.targets.json").write_text(
            json.dumps(
                {
                    "pattern": name,
                    "fabric_profile": profile.ref,
                    "engine_version": doc.engine_version,
                    "targets": [target.model_dump(mode="json") for target in targets],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"{name}: {plan.stitch_count()} stitches, {len(targets)} targets to measure")
        written += 1

    print(f"\n{written} pattern(s) in {out_dir}")
    if skipped:
        print(f"{skipped} pattern(s) skipped -- see above", file=sys.stderr)
    print("Nothing here is calibration until it has been sewn and measured.")
    return EXIT_OK


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
    digitize.add_argument(
        "--machine",
        default=None,
        help="machine profile reference, e.g. multineedle_6head@1 (see: v2s machines)",
    )
    digitize.add_argument(
        "--machine-dir",
        default=None,
        help="directory of your own machine profiles (or set V2S_MACHINE_DIR)",
    )
    digitize.add_argument(
        "--profile-dir",
        default=None,
        help="directory of your shop's profile overrides (or set V2S_PROFILE_DIR)",
    )
    digitize.set_defaults(func=_cmd_digitize)

    render = sub.add_parser("render", help="render a machine file to SVG")
    render.add_argument("file", help="path to a written machine file")
    render.add_argument("--out", default=None, help="output SVG path")
    render.set_defaults(func=_cmd_render)

    profiles = sub.add_parser("profiles", help="list available fabric profiles")
    profiles.add_argument(
        "--profile-dir", default=None, help="your shop's profile override directory"
    )
    profiles.set_defaults(func=_cmd_profiles)

    override = sub.add_parser("override", help="your shop's changes to our fabric profiles")
    override_sub = override.add_subparsers(dest="override_command", required=True)

    override_init = override_sub.add_parser("init", help="scaffold an override file")
    override_init.add_argument("profile", help="fabric profile reference, e.g. pique@1")
    override_init.add_argument("--shop", required=True, help="who is recording these")
    override_init.add_argument("--out", default="overrides", help="output directory")
    override_init.add_argument("--force", action="store_true", help="replace an existing file")
    override_init.set_defaults(func=_cmd_override_init)

    override_show = override_sub.add_parser("show", help="show overrides and what they change")
    override_show.add_argument(
        "--profile-dir", default=None, help="your shop's profile override directory"
    )
    override_show.set_defaults(func=_cmd_override_show)

    machines = sub.add_parser("machines", help="list machine profiles on the search path")
    machines.add_argument(
        "--machine-dir",
        default=None,
        help="directory of your own machine profiles (or set V2S_MACHINE_DIR)",
    )
    machines.set_defaults(func=_cmd_machines)

    check = sub.add_parser("check", help="run the automated quality checks on a design")
    check.add_argument("file", help="path to an IR document")
    check.add_argument("--machine", default=None, help="machine profile reference")
    check.add_argument("--machine-dir", default=None, help="your machine profile directory")
    check.add_argument(
        "--profile-dir", default=None, help="your shop's profile override directory"
    )
    check.add_argument(
        "-v", "--verbose", action="store_true", help="also show the rules that passed"
    )
    check.set_defaults(func=_cmd_check)

    calibrate = sub.add_parser("calibrate", help="generate lab calibration patterns")
    calibrate.add_argument("--out", default="out/calibration", help="output directory")
    calibrate.add_argument(
        "--profile", default="twill", help="fabric profile to calibrate (default: twill)"
    )
    calibrate.add_argument(
        "--patterns",
        default=None,
        type=lambda value: [part.strip() for part in value.split(",") if part.strip()],
        help="comma-separated pattern names (default: every available pattern)",
    )
    calibrate.add_argument(
        "--formats",
        default=",".join(DEFAULT_FORMATS),
        type=lambda value: [part.strip().lower() for part in value.split(",") if part.strip()],
        help=f"comma-separated output formats (default: {','.join(DEFAULT_FORMATS)})",
    )
    calibrate.add_argument("--machine", default=None, help="machine profile reference")
    calibrate.add_argument("--machine-dir", default=None, help="your machine profile directory")
    calibrate.add_argument(
        "--profile-dir", default=None, help="your shop's profile override directory"
    )
    calibrate.add_argument(
        "--list", action="store_true", help="list patterns and what each is for"
    )
    calibrate.set_defaults(func=_cmd_calibrate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
