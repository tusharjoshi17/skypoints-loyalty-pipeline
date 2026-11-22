"""Flatten the partner-airline JSON redemption feed into one row per transaction.

Accepted shapes (the brief shows a single object; at billions of rows a real
feed would be newline-delimited JSON, so both are supported):
    * one member object               {"member_id": ..., "redemptions": [...]}
    * a JSON array of member objects  [{...}, {...}]
    * NDJSON: one member object per line
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from skypoints.models import DQIssue, Severity

VALID_STATUSES = frozenset({"COMPLETED", "PENDING", "CANCELLED", "REVERSED"})


@dataclass(frozen=True)
class RedemptionRow:
    txn_id: str
    member_id: str
    feed_date: date
    txn_date: date
    partner: str
    miles_redeemed: int
    status: str
    source_file: str


@dataclass(frozen=True)
class MemberRedemptionSummary:
    member_id: str
    completed_miles: int
    pending_miles: int
    completed_txn_count: int
    last_redemption_date: date | None
    is_known_member: bool  # False -> orphan: redemption for a member we do not have


# Type aliases keep the signatures short and readable.
Rows = list[RedemptionRow]
Issues = list[DQIssue]
RowsAndIssues = tuple[Rows, Issues]
Summaries = list[MemberRedemptionSummary]
FeedObjects = Iterator[dict]


def load_feed_objects(text: str) -> FeedObjects:
    """Yield member objects from a single object, an array, or NDJSON text."""
    stripped = text.strip()
    if not stripped:
        return
    try:
        document = json.loads(stripped)
    except json.JSONDecodeError:
        # Not one JSON document, so treat it as NDJSON: one object per line.
        for line in stripped.splitlines():
            if line.strip():
                yield json.loads(line)
        return
    if isinstance(document, list):
        yield from document
    else:
        yield document


def _parse_yyyymmdd(value: object) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def _transaction_problem(txn: Mapping, feed_date: date) -> tuple[str, str] | None:
    """Return (rule, message) for the first problem found, or None if the transaction is valid."""
    txn_id = txn.get("txn_id")
    txn_date = _parse_yyyymmdd(txn.get("txn_date"))
    miles = txn.get("miles_redeemed")
    status = str(txn.get("status", "")).upper()

    if not txn_id:
        return "TXN_ID_MISSING", "redemption without txn_id"
    if txn_date is None:
        return "INVALID_DATE", f"txn {txn_id}: txn_date '{txn.get('txn_date')}' is invalid"
    if txn_date > feed_date:
        return "TXN_AFTER_FEED_DATE", f"txn {txn_id}: txn_date is after feed_date"
    # bool is a subclass of int in Python, so True would otherwise count as 1 mile.
    if not isinstance(miles, int) or isinstance(miles, bool) or miles <= 0:
        return "INVALID_MILES", f"txn {txn_id}: miles_redeemed '{miles}' must be a positive integer"
    if status not in VALID_STATUSES:
        return "INVALID_STATUS", f"txn {txn_id}: status '{status}' is unknown"
    return None


def flatten_redemptions(objects: Iterable[Mapping], source_file: str) -> RowsAndIssues:
    """Explode redemptions into rows; invalid transactions become DQ issues, not exceptions."""
    rows: Rows = []
    issues: Issues = []

    for obj in objects:
        member_id = obj.get("member_id")
        feed_date = _parse_yyyymmdd(obj.get("feed_date"))
        if not member_id or feed_date is None:
            message = "missing or invalid member_id / feed_date"
            issues.append(DQIssue("REDEMPTION_HEADER_INVALID", Severity.ERROR, message, source_file, None, member_id))
            continue

        transactions = obj.get("redemptions") or []
        for txn in transactions:
            problem = _transaction_problem(txn, feed_date)
            if problem is not None:
                rule, message = problem
                issues.append(DQIssue(rule, Severity.ERROR, message, source_file, None, str(member_id)))
                continue
            rows.append(
                RedemptionRow(
                    txn_id=str(txn.get("txn_id")),
                    member_id=str(member_id),
                    feed_date=feed_date,
                    txn_date=_parse_yyyymmdd(txn.get("txn_date")),
                    partner=str(txn.get("partner", "")),
                    miles_redeemed=txn.get("miles_redeemed"),
                    status=str(txn.get("status")).upper(),
                    source_file=source_file,
                )
            )
    return rows, issues


def latest_transaction_state(rows: Iterable[RedemptionRow]) -> Rows:
    """A txn can re-appear with a new status (PENDING -> COMPLETED). Keep the latest feed's version."""
    latest = {}
    for row in rows:
        existing = latest.get(row.txn_id)
        if existing is None or row.feed_date >= existing.feed_date:
            latest[row.txn_id] = row
    return list(latest.values())


def summarise_by_member(rows: Iterable[RedemptionRow], known_member_ids: set) -> Summaries:
    """Aggregate to member grain FIRST, so joining to member profiles never fans out rows."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.member_id].append(row)

    summaries: Summaries = []
    for member_id in sorted(grouped):
        txns = grouped.get(member_id)
        completed = [t for t in txns if t.status == "COMPLETED"]
        summaries.append(
            MemberRedemptionSummary(
                member_id=member_id,
                completed_miles=sum(t.miles_redeemed for t in completed),
                pending_miles=sum(t.miles_redeemed for t in txns if t.status == "PENDING"),
                completed_txn_count=len(completed),
                last_redemption_date=max((t.txn_date for t in completed), default=None),
                is_known_member=member_id in known_member_ids,
            )
        )
    return summaries
