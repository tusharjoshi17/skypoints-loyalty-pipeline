"""Command-line entry point.

python -m skypoints run --input data/input --output data/output
python -m skypoints profile-extracts data/input/extracts/*.xlsx --as-of 2026-11-21
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from dataclasses import asdict, fields
from datetime import date
from pathlib import Path

from skypoints.models import DQIssue
from skypoints.pipeline import run
from skypoints.sources.country_extracts import read_country_extract
from skypoints.staging import to_staged_member
from skypoints.validations import run_batch_rules


def _cmd_run(args: argparse.Namespace) -> int:
    members = sorted(args.input.glob("SKYPOINTS_MEMBERS_*.txt"))
    redemptions = sorted(args.input.glob("SKYPOINTS_REDEMPTIONS_*.json"))
    if not members:
        logging.error("No member files found in %s", args.input)
        return 1
    summary = run(members, redemptions, args.output)
    print((args.output / "dq" / "run_report.md").read_text(encoding="utf-8"))
    return 0 if summary.is_reconciled else 2


def _cmd_profile_extracts(args: argparse.Namespace) -> int:
    """Run the shared staging and DQ rules over the per-country extracts and print every issue as CSV."""
    staged = []
    issues = []
    for path in args.files:
        records, adapter_issues = read_country_extract(path, args.as_of)
        issues.extend(adapter_issues)
        staged.extend(to_staged_member(record) for record in records)
    for member in staged:
        issues.extend(member.issues)
    issues.extend(run_batch_rules(staged))

    writer = csv.DictWriter(sys.stdout, fieldnames=[f.name for f in fields(DQIssue)])
    writer.writeheader()
    writer.writerows({**asdict(issue), "severity": issue.severity.value} for issue in issues)
    return 0


def main(argv: list | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    parser = argparse.ArgumentParser(prog="skypoints", description="SkyPoints member pipeline")
    commands = parser.add_subparsers(dest="command", required=True)

    run_parser = commands.add_parser("run", help="process member and redemption feeds")
    run_parser.add_argument("--input", type=Path, default=Path("data/input"))
    run_parser.add_argument("--output", type=Path, default=Path("data/output"))
    run_parser.set_defaults(func=_cmd_run)

    profile_parser = commands.add_parser("profile-extracts", help="DQ-profile the per-country extracts")
    profile_parser.add_argument("files", type=Path, nargs="+")
    profile_parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    profile_parser.set_defaults(func=_cmd_profile_extracts)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
