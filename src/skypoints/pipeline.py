"""End-to-end orchestration of the local reference pipeline.

    member files -> parse -> stage + DQ -+-> quarantine (ERROR issues)
                                         +-> latest-record-wins -> MEMBER_CURRENT -> TABLE_<COUNTRY>
    redemption files -> flatten + DQ -> latest txn state -> member summary (joined on member_id)

Each member file is processed as one daily batch, in business-date order.
MEMBER_CURRENT is persisted as JSON between runs. It is the single source of
truth; country tables are regenerated from it, so a member can never appear
in two country tables.
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from pathlib import Path

from skypoints.countries import COUNTRY_TARGET_TABLES
from skypoints.file_naming import parse_file_name
from skypoints.models import DQIssue, Severity, StagedMember
from skypoints.parser import parse_member_lines
from skypoints.redemptions import (
    flatten_redemptions,
    latest_transaction_state,
    load_feed_objects,
    summarise_by_member,
)
from skypoints.routing import CurrentLocation, latest_record_wins, plan_country_routing
from skypoints.staging import to_staged_member
from skypoints.validations import run_batch_rules

log = logging.getLogger(__name__)

# Type aliases keep the signatures short and readable.
Row = dict[str, object]
State = dict[str, Row]  # member_id -> MEMBER_CURRENT row
Members = list[StagedMember]
Paths = Sequence[Path]

MEMBER_COLUMNS = [f.name for f in fields(StagedMember) if f.name != "issues"]
ISSUE_COLUMNS = [f.name for f in fields(DQIssue)]


@dataclass
class RunSummary:
    """Counts for the run report. Every detail row read must end up in exactly one bucket."""

    detail_rows_read: int = 0
    structurally_rejected: int = 0
    quarantined: int = 0
    superseded: int = 0
    ignored_as_older: int = 0
    loaded: int = 0
    moves: list = field(default_factory=list)
    rows_per_table: dict = field(default_factory=dict)
    redemption_rows: int = 0
    redemption_rejects: int = 0
    issues: list = field(default_factory=list)

    @property
    def is_reconciled(self) -> bool:
        """Every row read is accounted for exactly once."""
        accounted = (
            self.structurally_rejected + self.quarantined + self.superseded + self.ignored_as_older + self.loaded
        )
        return accounted == self.detail_rows_read


# ------------------------------------------------------------------ helpers
def _serialise(value: object) -> object:
    return value.isoformat() if isinstance(value, date | datetime) else value


def _member_to_row(member: StagedMember) -> Row:
    return {column: _serialise(getattr(member, column)) for column in MEMBER_COLUMNS}


def _issue_to_row(issue: DQIssue) -> Row:
    return {**asdict(issue), "severity": issue.severity.value}


def _dataclass_to_row(obj: object) -> Row:
    return {key: _serialise(value) for key, value in asdict(obj).items()}


def _write_csv(path: Path, header: Sequence[str], rows: Iterable[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(header))
        writer.writeheader()
        writer.writerows(rows)


def _load_state(path: Path) -> State:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------- stages
def _stage_file(path: Path, summary: RunSummary) -> Members:
    """Parse and type one member file, recording structural rejects and issues."""
    meta = parse_file_name(path, "MEMBERS")
    with path.open(encoding="utf-8") as handle:
        parsed = parse_member_lines(handle, meta)
    summary.detail_rows_read += parsed.detail_rows_read
    summary.structurally_rejected += parsed.detail_rows_read - len(parsed.records)
    summary.issues.extend(parsed.issues)
    log.info("Parsed %s: %d detail rows", meta.file_name, parsed.detail_rows_read)
    return [to_staged_member(record) for record in parsed.records]


def _current_locations(state: State) -> dict:
    return {
        member_id: CurrentLocation(str(row.get("country_code")), date.fromisoformat(str(row.get("business_date"))))
        for member_id, row in state.items()
    }


def _apply_batch(staged: Members, state: State, summary: RunSummary) -> None:
    """Quarantine, de-duplicate and route one daily batch onto MEMBER_CURRENT (`state`)."""
    valid = [member for member in staged if not member.has_errors]
    summary.quarantined += len(staged) - len(valid)
    for member in staged:
        summary.issues.extend(member.issues)
    summary.issues.extend(run_batch_rules(staged))

    winners, superseded = latest_record_wins(valid)
    summary.superseded += len(superseded)

    plan = plan_country_routing(winners, _current_locations(state))
    summary.ignored_as_older += len(plan.ignored_as_older)
    summary.moves.extend(plan.moves)

    for members in plan.upserts.values():
        for member in members:
            state[member.member_id] = _member_to_row(member)  # overwrite = move out of the old country
            summary.loaded += 1


def _run_redemptions(paths: Paths, known_members: set, output_dir: Path, summary: RunSummary) -> None:
    all_rows = []
    for path in sorted(paths):
        meta = parse_file_name(path, "REDEMPTIONS")
        objects = load_feed_objects(path.read_text(encoding="utf-8"))
        rows, issues = flatten_redemptions(objects, meta.file_name)
        all_rows.extend(rows)
        summary.issues.extend(issues)
        summary.redemption_rejects += len(issues)

    current_txns = latest_transaction_state(all_rows)
    summary.redemption_rows = len(current_txns)
    txn_rows = [_dataclass_to_row(row) for row in current_txns]
    header = list(txn_rows[0]) if txn_rows else ["txn_id"]
    _write_csv(output_dir / "redemptions" / "redemptions_flat.csv", header, txn_rows)

    summaries = summarise_by_member(current_txns, known_members)
    for member_summary in summaries:
        if not member_summary.is_known_member:
            message = f"redemptions for member_id {member_summary.member_id} with no member profile"
            summary.issues.append(
                DQIssue(
                    rule="ORPHAN_REDEMPTION",
                    severity=Severity.WARNING,
                    message=message,
                    source_file="redemptions",
                    member_id=member_summary.member_id,
                )
            )
    summary_rows = [_dataclass_to_row(s) for s in summaries]
    header = list(summary_rows[0]) if summary_rows else ["member_id"]
    _write_csv(output_dir / "redemptions" / "member_redemption_summary.csv", header, summary_rows)


def run(member_files: Paths, redemption_files: Paths, output_dir: Path) -> RunSummary:
    """Process each member file as one daily batch, in business-date order (file names embed the date)."""
    summary = RunSummary()
    state_path = output_dir / "state" / "member_current.json"
    state = _load_state(state_path)

    all_staged: Members = []
    for path in sorted(member_files):
        staged = _stage_file(path, summary)
        _apply_batch(staged, state, summary)
        all_staged.extend(staged)

    rejected = [member for member in all_staged if member.has_errors]
    _write_csv(output_dir / "staging" / "member_stg.csv", MEMBER_COLUMNS, map(_member_to_row, all_staged))
    _write_csv(output_dir / "quarantine" / "member_rejects.csv", MEMBER_COLUMNS, map(_member_to_row, rejected))

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    for country, table in COUNTRY_TARGET_TABLES.items():
        rows = [row for row in state.values() if row.get("country_code") == country]
        _write_csv(output_dir / "targets" / f"{table}.csv", MEMBER_COLUMNS, rows)
        summary.rows_per_table[table] = len(rows)

    _run_redemptions(redemption_files, set(state), output_dir, summary)

    _write_csv(output_dir / "dq" / "dq_issues.csv", ISSUE_COLUMNS, map(_issue_to_row, summary.issues))
    (output_dir / "dq" / "run_report.md").write_text(render_report(summary), encoding="utf-8")
    return summary


# ------------------------------------------------------------------- report
def render_report(summary: RunSummary) -> str:
    counts = {}
    for issue in summary.issues:
        key = (issue.severity.value, issue.rule)
        counts[key] = counts.get(key, 0) + 1

    reconciled = "YES" if summary.is_reconciled else "NO"
    moves = [f"- member {m} moved {a} -> {b}" for m, a, b in summary.moves] or ["- none"]
    tables = [f"| {table} | {n} |" for table, n in sorted(summary.rows_per_table.items())]
    dq_rows = [f"| {sev} | {rule} | {n} |" for (sev, rule), n in sorted(counts.items())]

    lines = [
        "# SkyPoints pipeline run report",
        "",
        "## Reconciliation",
        "",
        "| Metric | Rows |",
        "|---|---|",
        f"| Detail rows read | {summary.detail_rows_read} |",
        f"| Structurally rejected (parser) | {summary.structurally_rejected} |",
        f"| Quarantined (DQ errors) | {summary.quarantined} |",
        f"| Superseded (latest record wins) | {summary.superseded} |",
        f"| Ignored (older than loaded data) | {summary.ignored_as_older} |",
        f"| Loaded / upserted | {summary.loaded} |",
        f"| **Reconciled** | **{reconciled}** |",
        "",
        "## Country tables (after this run)",
        "",
        "| Table | Rows |",
        "|---|---|",
        *tables,
        "",
        "## Country moves",
        "",
        *moves,
        "",
        "## Redemptions",
        "",
        f"- current transactions: {summary.redemption_rows}",
        f"- rejected transactions: {summary.redemption_rejects}",
        "",
        "## Data-quality issues",
        "",
        "| Severity | Rule | Count |",
        "|---|---|---|",
        *dq_rows,
    ]
    return "\n".join(lines) + "\n"
