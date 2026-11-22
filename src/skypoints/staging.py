"""Raw -> staging: type the record, derive Age and Stale_Member, attach DQ issues."""

from __future__ import annotations

from datetime import date

from skypoints import validations as dq
from skypoints.countries import normalize_country
from skypoints.layout import STALE_MEMBER_THRESHOLD_DAYS
from skypoints.models import RawMemberRecord, StagedMember


def calculate_age(dob: date | None, as_of: date) -> int | None:
    """Age in completed years on `as_of` (birthday not yet reached this year -> one less)."""
    if dob is None or dob > as_of:
        return None
    had_birthday = (as_of.month, as_of.day) >= (dob.month, dob.day)
    return as_of.year - dob.year - (0 if had_birthday else 1)


def days_since(event: date | None, as_of: date) -> int | None:
    return None if event is None else (as_of - event).days


def is_stale_member(
    last_flight: date | None,
    enrollment: date | None,
    as_of: date,
    threshold_days: int = STALE_MEMBER_THRESHOLD_DAYS,
) -> bool:
    """Stale = more than `threshold_days` since the last flight.

    Assumption (documented in README): a member who has never flown is judged
    on their enrollment date, so a new joiner is not stale on day one but a
    member who enrolled years ago and never flew is.
    """
    reference = last_flight or enrollment
    if reference is None:
        return False
    return (as_of - reference).days > threshold_days


def _upper(value: str | None) -> str | None:
    return value.upper() if value is not None else None


def to_staged_member(rec: RawMemberRecord) -> StagedMember:
    """Type one raw record. Never raises on bad data: problems become DQ issues."""
    values = rec.values
    issues = dq.check_mandatory(rec) + dq.check_lengths(rec) + dq.check_member_id_format(rec)
    issues += dq.check_reference_values(rec)

    enrollment, date_issues = dq.parse_date_field(rec, "enrollment_date")
    issues += date_issues
    last_flight, date_issues = dq.parse_date_field(rec, "last_flight_date")
    issues += date_issues
    dob, date_issues = dq.parse_date_field(rec, "dob")
    issues += date_issues
    post_code, int_issues = dq.parse_int_field(rec, "post_code")
    issues += int_issues

    country = normalize_country(values.get("country"))
    issues += dq.check_country(rec, country)

    as_of = rec.business_date
    member = StagedMember(
        member_id=values.get("member_id"),
        member_name=values.get("member_name"),
        enrollment_date=enrollment,
        last_flight_date=last_flight,
        tier_code=_upper(values.get("tier_code")),
        agent_name=values.get("agent_name"),
        state=_upper(values.get("state")),
        country_code=country,
        source_country_code=values.get("country"),
        post_code=post_code,
        dob=dob,
        is_active=_upper(values.get("is_active")),
        age=calculate_age(dob, as_of),
        days_since_last_flight=days_since(last_flight, as_of),
        is_stale_member=is_stale_member(last_flight, enrollment, as_of),
        source_file=rec.source_file,
        line_number=rec.line_number,
        business_date=rec.business_date,
        extract_ts=rec.extract_ts,
    )
    member.issues = issues + dq.check_date_logic(member, rec)
    return member
