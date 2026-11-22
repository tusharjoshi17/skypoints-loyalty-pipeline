"""Shared test helpers: build records with sensible defaults so each test states only what matters."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from skypoints.models import FileMetadata, RawMemberRecord

BUSINESS_DATE = date(2024, 1, 15)
EXTRACT_TS = datetime(2024, 1, 15, 1, 30)

VALID_VALUES = {
    "member_name": "Elena",
    "member_id": "223457",
    "enrollment_date": "20101012",
    "last_flight_date": "20121013",
    "tier_code": "GLD",
    "agent_name": "Sam",
    "state": "CA",
    "country": "USA",
    "post_code": None,
    "dob": "03051985",
    "is_active": "A",
}


def make_raw(business_date=BUSINESS_DATE, line_number=2, extract_ts=None, **overrides):
    """A valid raw record; pass keyword overrides to change only the fields a test cares about."""
    return RawMemberRecord(
        values={**VALID_VALUES, **overrides},
        source_file="test.txt",
        line_number=line_number,
        business_date=business_date,
        extract_ts=extract_ts or datetime.combine(business_date, EXTRACT_TS.time()),
    )


def make_member(**kwargs):
    from skypoints.staging import to_staged_member  # local import keeps parser tests independent

    return to_staged_member(make_raw(**kwargs))


@pytest.fixture
def meta() -> FileMetadata:
    return FileMetadata("SKYPOINTS_MEMBERS_20240115_013000.txt", BUSINESS_DATE, EXTRACT_TS)
