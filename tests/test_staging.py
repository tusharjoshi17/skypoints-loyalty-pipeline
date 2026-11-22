from datetime import date

import pytest

from conftest import make_member
from skypoints.staging import calculate_age, is_stale_member


@pytest.mark.parametrize(
    ("dob", "as_of", "expected"),
    [
        (date(1985, 3, 5), date(2024, 3, 5), 39),  # birthday today
        (date(1985, 3, 5), date(2024, 3, 4), 38),  # day before birthday
        (date(2000, 2, 29), date(2023, 2, 28), 22),  # leap-day birthday, non-leap year
        (None, date(2024, 1, 1), None),
        (date(2030, 1, 1), date(2024, 1, 1), None),  # future DOB: no age
    ],
)
def test_calculate_age(dob, as_of, expected):
    assert calculate_age(dob, as_of) == expected


@pytest.mark.parametrize(
    ("last_flight", "expected"),
    [
        (date(2023, 10, 17), False),  # exactly 90 days -> not stale (rule is > 90)
        (date(2023, 10, 16), True),  # 91 days
    ],
)
def test_stale_member_boundary(last_flight, expected):
    assert is_stale_member(last_flight, date(2020, 1, 1), date(2024, 1, 15)) is expected


def test_member_who_never_flew_is_judged_on_enrollment_date():
    as_of = date(2024, 1, 15)
    assert is_stale_member(None, date(2024, 1, 1), as_of) is False
    assert is_stale_member(None, date(2020, 1, 1), as_of) is True


def test_staging_types_record_and_derives_columns():
    member = make_member()

    assert member.enrollment_date == date(2010, 10, 12)
    assert member.dob == date(1985, 3, 5)  # MMDDYYYY parsed correctly
    assert member.age == 38  # as of feed date 2024-01-15, not "today"
    assert member.is_stale_member is True
    assert member.days_since_last_flight == (date(2024, 1, 15) - date(2012, 10, 13)).days
    assert member.issues == []


def test_country_is_normalised_and_original_kept_for_lineage():
    member = make_member(country="PHIL")

    assert member.country_code == "PHL"
    assert member.source_country_code == "PHIL"
    assert [issue.rule for issue in member.issues] == ["NON_STANDARD_COUNTRY_CODE"]


def test_bad_optional_date_is_nulled_but_member_kept():
    member = make_member(dob="13131985")

    assert member.dob is None
    assert member.age is None
    assert not member.has_errors
