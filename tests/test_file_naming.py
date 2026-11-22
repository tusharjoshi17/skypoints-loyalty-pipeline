from datetime import date, datetime

import pytest

from skypoints.file_naming import InvalidFileNameError, parse_file_name


def test_extracts_business_date_and_timestamp_from_member_file_name():
    meta = parse_file_name("in/SKYPOINTS_MEMBERS_20240115_013000.txt", "MEMBERS")

    assert meta.business_date == date(2024, 1, 15)
    assert meta.extract_ts == datetime(2024, 1, 15, 1, 30)
    assert meta.file_name == "SKYPOINTS_MEMBERS_20240115_013000.txt"


@pytest.mark.parametrize(
    "name",
    [
        "members.txt",  # no contract at all
        "SKYPOINTS_MEMBERS_20240115.txt",  # missing time
        "SKYPOINTS_MEMBERS_20241315_013000.txt",  # month 13: right shape, impossible date
        "SKYPOINTS_MEMBERS_20240115_013000.json",  # wrong extension for this feed
    ],
)
def test_rejects_file_names_that_break_the_contract(name):
    with pytest.raises(InvalidFileNameError):
        parse_file_name(name, "MEMBERS")


def test_rejects_a_redemption_file_passed_as_member_feed():
    with pytest.raises(InvalidFileNameError, match="expected MEMBERS"):
        parse_file_name("SKYPOINTS_REDEMPTIONS_20240115_013000.json", "MEMBERS")
