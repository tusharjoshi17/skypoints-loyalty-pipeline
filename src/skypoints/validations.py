"""Data-quality rules.

Two kinds of rules:
* Record-level rules run while a raw record is typed into staging
  (mandatory fields, lengths, formats, date logic, reference values).
* Batch-level rules need the whole batch (uniqueness, ID-length anomalies).

Severity policy:
    ERROR   -> the record cannot be trusted or routed; it goes to quarantine.
    WARNING -> the record is loaded; the issue is reported for follow-up.
Every rule has a stable code so issues can be counted and trended in AUDIT.DQ_ISSUES.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date, datetime

from skypoints.layout import FIELDS_BY_NAME, MEMBER_LAYOUT, VALID_ACTIVE_FLAGS, VALID_TIER_CODES, DataType
from skypoints.models import DQIssue, RawMemberRecord, Severity, StagedMember

# Type aliases keep signatures short and readable.
Issues = list[DQIssue]
Members = list[StagedMember]
DateResult = tuple[date | None, Issues]
IntResult = tuple[int | None, Issues]

MAX_PLAUSIBLE_AGE = 120


def _issue(rule: str, severity: Severity, message: str, rec: RawMemberRecord, column: str | None = None) -> DQIssue:
    return DQIssue(rule, severity, message, rec.source_file, rec.line_number, rec.values.get("member_id"), column)


# ---------------------------------------------------------------- record level
def check_mandatory(rec: RawMemberRecord) -> Issues:
    return [
        _issue("MANDATORY_FIELD_MISSING", Severity.ERROR, f"{spec.name} is mandatory", rec, spec.name)
        for spec in MEMBER_LAYOUT
        if spec.mandatory and rec.values.get(spec.name) is None
    ]


def check_lengths(rec: RawMemberRecord) -> Issues:
    """Length rules from the layout. Dates are skipped: they get a stricter format check."""
    issues = []
    for spec in MEMBER_LAYOUT:
        value = rec.values.get(spec.name)
        if spec.data_type is DataType.DATE or value is None:
            continue
        if len(value) > spec.max_length:
            message = f"{spec.name} length {len(value)} > {spec.max_length}"
            issues.append(_issue("FIELD_LENGTH_EXCEEDED", Severity.ERROR, message, rec, spec.name))
    return issues


def parse_date_field(rec: RawMemberRecord, column: str) -> DateResult:
    """Parse a DATE column using its layout format.

    An invalid mandatory date is an ERROR. An invalid optional date is nulled
    with a WARNING: we keep the member, not the bad date.
    """
    spec = FIELDS_BY_NAME.get(column)
    raw = rec.values.get(column)
    if raw is None:
        return None, []
    try:
        if len(raw) != 8 or not raw.isdigit():
            raise ValueError(raw)
        return datetime.strptime(raw, spec.date_format).date(), []
    except ValueError:
        severity = Severity.ERROR if spec.mandatory else Severity.WARNING
        message = f"{column}='{raw}' is not a valid {spec.date_format} date"
        return None, [_issue("INVALID_DATE", severity, message, rec, column)]


def parse_int_field(rec: RawMemberRecord, column: str) -> IntResult:
    raw = rec.values.get(column)
    if raw is None:
        return None, []
    if raw.isdigit():
        return int(raw), []
    message = f"{column}='{raw}' is not an integer"
    return None, [_issue("INVALID_NUMBER", Severity.WARNING, message, rec, column)]


def check_member_id_format(rec: RawMemberRecord) -> Issues:
    member_id = rec.values.get("member_id")
    if member_id is None or member_id.isdigit():
        return []
    message = f"member_id='{member_id}' contains non-digit characters"
    return [_issue("MEMBER_ID_NOT_NUMERIC", Severity.WARNING, message, rec, "member_id")]


def check_reference_values(rec: RawMemberRecord) -> Issues:
    issues = []
    tier = rec.values.get("tier_code")
    if tier is not None and tier.upper() not in VALID_TIER_CODES:
        message = f"tier_code='{tier}' is not a known tier"
        issues.append(_issue("INVALID_TIER_CODE", Severity.WARNING, message, rec, "tier_code"))
    flag = rec.values.get("is_active")
    if flag is not None and flag.upper() not in VALID_ACTIVE_FLAGS:
        message = f"is_active='{flag}' is not A/I"
        issues.append(_issue("INVALID_ACTIVE_FLAG", Severity.WARNING, message, rec, "is_active"))
    return issues


def check_country(rec: RawMemberRecord, normalised: str | None) -> Issues:
    raw = rec.values.get("country")
    if raw is None:
        message = "country is required to route the member"
        return [_issue("COUNTRY_MISSING", Severity.ERROR, message, rec, "country")]
    if normalised is None:
        message = f"country='{raw}' has no routing rule"
        return [_issue("UNKNOWN_COUNTRY", Severity.ERROR, message, rec, "country")]
    if raw.upper() != normalised:
        message = f"country='{raw}' normalised to ISO alpha-3 '{normalised}'"
        return [_issue("NON_STANDARD_COUNTRY_CODE", Severity.WARNING, message, rec, "country")]
    return []


def check_date_logic(member: StagedMember, rec: RawMemberRecord) -> Issues:
    """Cross-field date rules. Dates are compared to the feed business date, never 'today'."""
    issues = []
    as_of = rec.business_date
    enrolled, flown, dob = member.enrollment_date, member.last_flight_date, member.dob

    if enrolled and enrolled > as_of:
        message = f"enrollment_date {enrolled} is after feed date {as_of}"
        issues.append(_issue("ENROLLMENT_IN_FUTURE", Severity.ERROR, message, rec, "enrollment_date"))
    if flown and flown > as_of:
        message = f"last_flight_date {flown} is after feed date {as_of}"
        issues.append(_issue("FLIGHT_IN_FUTURE", Severity.WARNING, message, rec, "last_flight_date"))
    if flown and enrolled and flown < enrolled:
        message = "last_flight_date is before enrollment_date"
        issues.append(_issue("FLIGHT_BEFORE_ENROLLMENT", Severity.WARNING, message, rec, "last_flight_date"))
    if dob and dob > as_of:
        message = f"dob {dob} is in the future"
        issues.append(_issue("DOB_IN_FUTURE", Severity.ERROR, message, rec, "dob"))
    if dob and enrolled and enrolled < dob:
        message = "enrollment_date is before dob"
        issues.append(_issue("ENROLLED_BEFORE_BIRTH", Severity.ERROR, message, rec, "enrollment_date"))
    if member.age is not None and member.age > MAX_PLAUSIBLE_AGE:
        message = f"age {member.age} > {MAX_PLAUSIBLE_AGE}"
        issues.append(_issue("IMPLAUSIBLE_AGE", Severity.WARNING, message, rec, "dob"))
    return issues


# ----------------------------------------------------------------- batch level
def check_duplicate_member_ids(members: Iterable[StagedMember]) -> Issues:
    """Same member_id more than once in a batch. Not an error: resolved by 'latest record wins'."""
    by_id: dict[str, Members] = defaultdict(list)
    for member in members:
        if member.member_id:
            by_id[member.member_id].append(member)

    issues = []
    for member_id, rows in by_id.items():
        if len(rows) < 2:
            continue
        countries = ", ".join(sorted({row.country_code or "?" for row in rows}))
        message = f"{len(rows)} records for member_id {member_id} (countries: {countries}); latest record wins"
        issues.append(
            DQIssue(
                rule="DUPLICATE_MEMBER_ID",
                severity=Severity.WARNING,
                message=message,
                source_file=rows[-1].source_file,
                member_id=member_id,
                column="member_id",
            )
        )
    return issues


def check_spec_key_uniqueness(members: Iterable[StagedMember]) -> Issues:
    """The design doc flags Member Name as the key column. Names are not unique in
    real life, so we key on member_id instead and report when the documented key breaks."""
    ids_by_name: dict[str, set[str]] = defaultdict(set)
    for member in members:
        if member.member_name and member.member_id:
            ids_by_name[member.member_name.upper()].add(member.member_id)

    issues = []
    for name, ids in ids_by_name.items():
        if len(ids) < 2:
            continue
        message = f"member_name '{name}' maps to {len(ids)} member_ids: {', '.join(sorted(ids))}"
        issues.append(DQIssue("SPEC_KEY_NOT_UNIQUE", Severity.WARNING, message, "batch", column="member_name"))
    return issues


def check_member_id_length_anomalies(members: Iterable[StagedMember]) -> Issues:
    """Flag IDs whose length differs from the dominant length in the batch.
    In the sample, 22345 and 2256 sit next to 6-digit IDs, which looks like truncation."""
    rows = [member for member in members if member.member_id]
    if len(rows) < 3:
        return []
    dominant_length = Counter(len(member.member_id) for member in rows).most_common(1)[0][0]

    issues = []
    for member in rows:
        if len(member.member_id) == dominant_length:
            continue
        message = f"member_id '{member.member_id}' has {len(member.member_id)} chars; most IDs have {dominant_length}"
        issues.append(
            DQIssue(
                "MEMBER_ID_LENGTH_ANOMALY",
                Severity.WARNING,
                message,
                member.source_file,
                member.line_number,
                member.member_id,
                "member_id",
            )
        )
    return issues


BATCH_RULES = (check_duplicate_member_ids, check_spec_key_uniqueness, check_member_id_length_anomalies)


def run_batch_rules(members: Members) -> Issues:
    """Run every batch rule over the whole batch."""
    issues = []
    for rule in BATCH_RULES:
        issues.extend(rule(members))
    return issues
