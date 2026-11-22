"""Data structures shared by every pipeline stage.

Mirrors the three Snowflake layers:
    RawMemberRecord  -> RAW.MEMBER_LANDING   (everything is text, nothing is lost)
    StagedMember     -> STAGING.MEMBER_STG   (typed, cleaned, derived columns)
    DQIssue          -> AUDIT.DQ_ISSUES      (one row per rule violation)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class Severity(str, Enum):
    ERROR = "ERROR"  # record is quarantined, never reaches a country table
    WARNING = "WARNING"  # record is loaded, issue is reported


@dataclass(frozen=True)
class FileMetadata:
    file_name: str
    business_date: date
    extract_ts: datetime


@dataclass(frozen=True)
class RawMemberRecord:
    """A detail record exactly as received. Values stay as strings on purpose:
    typing a DOB like 03051985 as a number is how the leading zero was lost
    in the intermediate table of the brief."""

    values: dict[str, str | None]
    source_file: str
    line_number: int
    business_date: date
    extract_ts: datetime


@dataclass(frozen=True)
class DQIssue:
    rule: str
    severity: Severity
    message: str
    source_file: str
    line_number: int | None = None
    member_id: str | None = None
    column: str | None = None


@dataclass
class StagedMember:
    # Mandatory fields are Optional here only so that rejected records can
    # still be represented and quarantined with their issues attached.
    member_id: str | None
    member_name: str | None
    enrollment_date: date | None
    last_flight_date: date | None
    tier_code: str | None
    agent_name: str | None
    state: str | None
    country_code: str | None  # normalised ISO alpha-3
    source_country_code: str | None  # as received, kept for lineage
    post_code: int | None
    dob: date | None
    is_active: str | None
    age: int | None
    days_since_last_flight: int | None
    is_stale_member: bool
    source_file: str
    line_number: int
    business_date: date
    extract_ts: datetime
    issues: list[DQIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity is Severity.ERROR for i in self.issues)