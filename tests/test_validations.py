import pytest

from conftest import make_member
from skypoints.models import Severity
from skypoints.validations import (
    check_duplicate_member_ids,
    check_member_id_length_anomalies,
    check_spec_key_uniqueness,
)


def rules_of(member):
    return {issue.rule: issue.severity for issue in member.issues}


@pytest.mark.parametrize("column", ["member_name", "member_id", "enrollment_date"])
def test_missing_mandatory_field_is_an_error(column):
    member = make_member(**{column: None})

    assert rules_of(member)["MANDATORY_FIELD_MISSING"] is Severity.ERROR
    assert member.has_errors


def test_invalid_mandatory_date_is_an_error():
    assert rules_of(make_member(enrollment_date="20231345"))["INVALID_DATE"] is Severity.ERROR


def test_field_longer_than_layout_is_an_error():
    assert rules_of(make_member(member_id="1" * 19))["FIELD_LENGTH_EXCEEDED"] is Severity.ERROR


@pytest.mark.parametrize(("country", "rule"), [(None, "COUNTRY_MISSING"), ("UAE", "UNKNOWN_COUNTRY")])
def test_member_that_cannot_be_routed_is_an_error(country, rule):
    assert rules_of(make_member(country=country))[rule] is Severity.ERROR


@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        ({"tier_code": "XYZ"}, "INVALID_TIER_CODE"),
        ({"is_active": "Y"}, "INVALID_ACTIVE_FLAG"),
        ({"member_id": "22A457"}, "MEMBER_ID_NOT_NUMERIC"),
        ({"last_flight_date": "20091012"}, "FLIGHT_BEFORE_ENROLLMENT"),
        ({"dob": "01011900"}, "IMPLAUSIBLE_AGE"),
    ],
)
def test_suspicious_values_are_warnings(overrides, rule):
    member = make_member(**overrides)

    assert rules_of(member)[rule] is Severity.WARNING
    assert not member.has_errors


@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        ({"enrollment_date": "20250101", "last_flight_date": None}, "ENROLLMENT_IN_FUTURE"),
        ({"dob": "01012030"}, "DOB_IN_FUTURE"),
        ({"dob": "01012011"}, "ENROLLED_BEFORE_BIRTH"),
    ],
)
def test_impossible_dates_are_errors(overrides, rule):
    assert rules_of(make_member(**overrides))[rule] is Severity.ERROR


def test_duplicate_member_id_is_reported_once_per_id():
    batch = [make_member(line_number=2), make_member(line_number=3), make_member(member_id="999999")]

    issues = check_duplicate_member_ids(batch)

    assert [(issue.rule, issue.member_id) for issue in issues] == [("DUPLICATE_MEMBER_ID", "223457")]


def test_spec_key_member_name_not_unique_is_reported():
    batch = [make_member(member_id="1"), make_member(member_id="2", member_name="ELENA")]

    assert check_spec_key_uniqueness(batch)[0].rule == "SPEC_KEY_NOT_UNIQUE"


def test_member_id_length_anomaly_matches_the_sample_data():
    ids = ["223457", "223458", "223459", "22345", "2256"]
    batch = [make_member(member_id=i, member_name=f"m{i}") for i in ids]

    flagged = {issue.member_id for issue in check_member_id_length_anomalies(batch)}

    assert flagged == {"22345", "2256"}
