"""Command-line entry point.

python -m skypoints run --input data/input --output data/output
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from skypoints.pipeline import run


def _cmd_run(args: argparse.Namespace) -> int:
    members = sorted(args.input.glob("SKYPOINTS_MEMBERS_*.txt"))
    redemptions = sorted(args.input.glob("SKYPOINTS_REDEMPTIONS_*.json"))
    if not members:
        logging.error("No member files found in %s", args.input)
        return 1
    summary = run(members, redemptions, args.output)
    print((args.output / "dq" / "run_report.md").read_text(encoding="utf-8"))
    return 0 if summary.is_reconciled else 2


def main(argv: list | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    parser = argparse.ArgumentParser(prog="skypoints", description="SkyPoints member pipeline")
    commands = parser.add_subparsers(dest="command", required=True)

    run_parser = commands.add_parser("run", help="process member and redemption feeds")
    run_parser.add_argument("--input", type=Path, default=Path("data/input"))
    run_parser.add_argument("--output", type=Path, default=Path("data/output"))
    run_parser.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
