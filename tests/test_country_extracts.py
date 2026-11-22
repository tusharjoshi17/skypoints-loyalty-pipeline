from datetime import date, datetime

import pytest
from openpyxl import Workbook

from skypoints.sources.country_extracts import read_country_extract, to_canonical_date
from skypoints.staging import to_staged_member

AS_OF = date(2026, 11, 21)

AUS_HEADER = ["Unique ID", "Member Name", "Tier Type", "Date of Birth", "Date of Enrollment", "Date of Flight"]


def write_xlsx(path, rows):
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    workbook.save(path)
    return path


def test_aus_extract_null_text_and_invalid_month_are_caught(tmp_path):
    path = write_xlsx(
        tmp_path / "AUS.xlsx",
        [
            AUS_HEADER,
            [1, "Mike", "PLT", "NULL", datetime(2022, 5, 11), datetime(2022, 8, 1)],
            [2, "Jonnathan", "GLD", datetime(1997, 12, 13), "2021-13-13", datetime(2022, 1, 5)],
        ],
    )

    records, _ = read_country_extract(path, AS_OF)
    mike, jonnathan = (to_staged_member(record) for record in records)

    assert mike.dob is None
    assert not mike.has_errors
    assert mike.country_code == "AUS"
    assert jonnathan.has_errors
    assert "INVALID_DATE" in {issue.rule for issue in jonnathan.issues}


def test_usa_integer_dates_are_zero_padded_and_flagged_as_ambiguous(tmp_path):
    path = tmp_path / "USA.csv"
    path.write_text(
        "ID,Name,TierCode,EnrollmentDate,FlightDate\n2,John,SLV,1052022,1152022\n3,Mike,GLD,12282021,12302021\n"
    )

    records, issues = read_country_extract(path, AS_OF)

    assert records[0].values.get("enrollment_date") == "20220105"
    assert records[1].values.get("enrollment_date") == "20211228"
    assert {issue.rule for issue in issues} == {"AMBIGUOUS_DATE_FORMAT"}
    assert len(issues) == 2  # only John's two 7-digit values


@pytest.mark.parametrize(
    ("value", "column", "expected"),
    [
        (datetime(1985, 3, 5), "dob", ("03051985", False)),
        ("2022-05-11", "enrollment_date", ("20220511", False)),
        ("1/1/2022", "enrollment_date", ("20220101", False)),
        ("6/15/2022", "last_flight_date", ("20220615", False)),
        ("12/1/1998", "dob", ("12011998", False)),
        ("NULL", "dob", (None, False)),
        (12282021, "enrollment_date", ("20211228", False)),
        (1052022, "enrollment_date", ("20220105", True)),
        ("2021-13-13", "enrollment_date", ("2021-13-13", False)),
    ],
)
def test_to_canonical_date(value, column, expected):
    assert to_canonical_date(value, column) == expected


def test_unknown_extract_is_rejected(tmp_path):
    path = write_xlsx(tmp_path / "FRA.xlsx", [["ID"]])

    with pytest.raises(ValueError, match="No extract spec"):
        read_country_extract(path, AS_OF)
