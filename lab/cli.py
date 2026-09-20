"""The lab CLI: record a sew-out, and read back what the sew-outs say.

Deliberately separate from `v2s`. The engine is a pure library and its CLI
generates files; this one writes a log of what happened on a machine. Keeping
them apart is what stops measurement data leaking into the engine's
dependencies.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date

from engine.lab.targets import MeasurementTarget
from lab.defects import USUAL_CAUSE, Defect
from lab.sewout import Consumables, SewOut, append, evaluate, load_targets, read_log

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_OUT_OF_TOLERANCE = 2
"""A recorded sew-out that missed tolerance. Not a tool failure -- a result,
and the one that means a parameter has to move."""


def _parse_measurement(raw: str) -> tuple[str, float]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError(f"expected target=value, got {raw!r}")
    target_id, _, value = raw.partition("=")
    try:
        return target_id.strip(), float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a measurement in mm") from None


def _print_evaluation(evaluation, targets: list[MeasurementTarget]) -> None:
    sewout = evaluation.sewout
    print(f"{sewout.pattern} on {sewout.fabric_profile} ({sewout.sewn_on}, {sewout.operator})")
    print(f"{'target':<22}{'designed':>10}{'measured':>10}{'error':>9}")
    for deviation in evaluation.deviations:
        flag = "" if deviation.within_tolerance else "  <-- out of tolerance"
        print(
            f"{deviation.target.id:<22}{deviation.target.designed_mm:>10.2f}"
            f"{deviation.measured_mm:>10.2f}{deviation.error_mm:>+9.2f}{flag}"
        )
    if evaluation.unmeasured:
        print(f"unmeasured: {', '.join(evaluation.unmeasured)}")
    print(f"mean error: {evaluation.mean_error_mm():+.2f} mm")
    if sewout.defects:
        print("defects:")
        for defect in sewout.defects:
            print(f"  {defect.value}: usually {USUAL_CAUSE[defect]}")
    print("PASS" if evaluation.passed else "FAIL")


def _cmd_record(args: argparse.Namespace) -> int:
    targets = load_targets(args.targets)
    sewout = SewOut(
        sewn_on=args.date,
        operator=args.operator,
        pattern=args.pattern or _pattern_from(args.targets),
        fabric_profile=args.profile,
        engine_version=args.engine_version,
        machine_profile=args.machine,
        consumables=Consumables(
            thread=args.thread,
            needle=args.needle,
            stabilizer=args.stabilizer,
            topping=args.topping,
            speed_spm=args.speed,
        ),
        measurements=dict(args.measure or []),
        defects=args.defect or [],
        photo=args.photo,
        notes=args.notes,
    )
    try:
        evaluation = evaluate(sewout, targets)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    append(sewout, args.log)
    _print_evaluation(evaluation, targets)
    print(f"recorded in {args.log}")
    return EXIT_OK if evaluation.passed else EXIT_OUT_OF_TOLERANCE


def _pattern_from(targets_path: str) -> str:
    import json
    from pathlib import Path

    return json.loads(Path(targets_path).read_text(encoding="utf-8"))["pattern"]


def _cmd_report(args: argparse.Namespace) -> int:
    """What the log says, grouped by what would have to change."""
    records = read_log(args.log)
    if not records:
        print(f"no sew-outs recorded in {args.log}", file=sys.stderr)
        return EXIT_ERROR

    grouped: dict[tuple[str, str], list[SewOut]] = defaultdict(list)
    for record in records:
        grouped[(record.fabric_profile, record.pattern)].append(record)

    print(f"{len(records)} sew-out(s) in {args.log}\n")
    for (profile_ref, pattern), group in sorted(grouped.items()):
        errors = []
        for record in group:
            targets = load_targets(args.targets) if args.targets else None
            if targets is None:
                continue
            evaluation = evaluate(record, targets)
            errors += [d.error_mm for d in evaluation.deviations]
        print(f"{profile_ref}  {pattern}: {len(group)} sew-out(s)")
        if errors:
            mean = sum(errors) / len(errors)
            print(f"  mean dimensional error {mean:+.2f} mm over {len(errors)} measurements")
            if mean < -0.1:
                print("  features come out small: the profile is under-compensating for pull")
            elif mean > 0.1:
                print("  features come out large: the profile is over-compensating")
        defects: dict[Defect, int] = defaultdict(int)
        for record in group:
            for defect in record.defects:
                defects[defect] += 1
        for defect, count in sorted(defects.items(), key=lambda item: -item[1]):
            print(f"  {count}x {defect.value} -- usually {USUAL_CAUSE[defect]}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="v2s-lab", description="Record and read sew-out results."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="record one measured sew-out")
    record.add_argument("targets", help="the pattern's .targets.json")
    record.add_argument("--log", default="lab/sewouts.jsonl", help="log file to append to")
    record.add_argument("--operator", required=True)
    record.add_argument("--profile", required=True, help="fabric profile reference sewn")
    record.add_argument("--engine-version", required=True, help="engine that made the file")
    record.add_argument("--machine", default=None, help="machine profile reference")
    record.add_argument("--pattern", default=None, help="defaults to the targets file's pattern")
    record.add_argument("--date", type=date.fromisoformat, default=date.today())
    record.add_argument("--thread", required=True)
    record.add_argument("--needle", required=True)
    record.add_argument("--stabilizer", required=True)
    record.add_argument("--topping", default="none")
    record.add_argument("--speed", type=int, required=True, help="actual spm run")
    record.add_argument(
        "--measure",
        action="append",
        type=_parse_measurement,
        metavar="TARGET=MM",
        help="repeatable: one measurement per target",
    )
    record.add_argument(
        "--defect",
        action="append",
        type=Defect,
        choices=list(Defect),
        help="repeatable: defects seen, from the taxonomy",
    )
    record.add_argument("--photo", default=None)
    record.add_argument("--notes", default="")
    record.set_defaults(func=_cmd_record)

    report = sub.add_parser("report", help="summarise recorded sew-outs")
    report.add_argument("--log", default="lab/sewouts.jsonl")
    report.add_argument(
        "--targets", default=None, help="targets file, to score measurements against"
    )
    report.set_defaults(func=_cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
