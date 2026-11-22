"""'Latest record wins' de-duplication and per-country routing.

A member lives in exactly one country table. When a newer record arrives with
a different country, the member is upserted into the new table AND deleted
from the old one; otherwise the member would be counted twice globally.

Ordering used to decide "latest" (most significant first):
    1. business_date of the file      (a late-arriving old file never overwrites newer data)
    2. extract_ts of the file         (two extracts on the same day)
    3. line_number inside the file    (same member twice in one file: last line wins)
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime

from skypoints.countries import target_table_for
from skypoints.models import StagedMember

# Type aliases keep the signatures short and readable.
Members = list[StagedMember]
WinnersAndSuperseded = tuple[Members, Members]
RecencyKey = tuple[date, datetime, int]


def _recency_key(member: StagedMember) -> RecencyKey:
    return (member.business_date, member.extract_ts, member.line_number)


def latest_record_wins(members: Iterable[StagedMember]) -> WinnersAndSuperseded:
    """Return (winners, superseded). Expects only valid (non-quarantined) members."""
    winners = {}
    superseded = []
    for member in members:
        current = winners.get(member.member_id)
        if current is None:
            winners[member.member_id] = member
        elif _recency_key(member) > _recency_key(current):
            superseded.append(current)
            winners[member.member_id] = member
        else:
            superseded.append(member)
    return list(winners.values()), superseded


@dataclass(frozen=True)
class CurrentLocation:
    """Where a member currently lives in the target layer (MEMBER_CURRENT in Snowflake)."""

    country_code: str
    business_date: date


@dataclass
class RoutingPlan:
    """What to change in the country tables for one batch."""

    upserts: dict = field(default_factory=lambda: defaultdict(list))  # table -> members
    deletes: dict = field(default_factory=lambda: defaultdict(list))  # table -> member_ids
    ignored_as_older: list = field(default_factory=list)
    moves: list = field(default_factory=list)  # (member_id, from_country, to_country)


def plan_country_routing(
    winners: Iterable[StagedMember],
    current: Mapping | None = None,
) -> RoutingPlan:
    """Build the upserts/deletes needed to apply this batch to the country tables.

    `current` maps member_id -> CurrentLocation for members already loaded.
    Incoming records older than what is already loaded are ignored, which makes
    re-processing an old file idempotent.
    """
    current = current or {}
    plan = RoutingPlan()
    for member in winners:
        existing = current.get(member.member_id)
        if existing is not None and member.business_date < existing.business_date:
            plan.ignored_as_older.append(member)
            continue

        new_table = target_table_for(member.country_code)
        plan.upserts[new_table].append(member)

        if existing is not None and existing.country_code != member.country_code:
            old_table = target_table_for(existing.country_code)
            plan.deletes[old_table].append(member.member_id)
            plan.moves.append((member.member_id, existing.country_code, member.country_code))
    return plan
