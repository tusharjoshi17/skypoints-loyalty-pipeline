import pytest

from skypoints.parser import MissingHeaderError, parse_member_lines

HEADER = "|H|Member_Name|Member_Id|Enrollment_Date|Last_Flight_Date|Tier_Code|Agent_Name|State|Country|DOB|Is_Active"
ELENA = "|D|Elena|223457|20101012|20121013|GLD|Sam|CA|USA|03051985|A"


def rules(result):
    return [issue.rule for issue in result.issues]


def test_maps_detail_fields_by_header_name(meta):
    result = parse_member_lines([HEADER, ELENA], meta)

    values = result.records[0].values
    assert values["member_id"] == "223457"
    assert values["dob"] == "03051985"  # kept as text: leading zero preserved
    assert values["country"] == "USA"


def test_column_missing_from_header_is_null_and_reported(meta):
    result = parse_member_lines([HEADER, ELENA], meta)

    assert result.records[0].values["post_code"] is None
    assert "LAYOUT_COLUMN_MISSING" in rules(result)


def test_whitespace_is_trimmed_and_empty_becomes_null(meta):
    result = parse_member_lines([HEADER, "|D|Ravi|223458|20101012|20121013|SLV|| TN |IND|03051985|A"], meta)

    values = result.records[0].values
    assert values["state"] == "TN"
    assert values["agent_name"] is None


def test_row_with_wrong_field_count_is_rejected_not_shifted(meta):
    result = parse_member_lines([HEADER, "|D|Sara|223462|20230101|20240110|SLV|Anil|CA|USA"], meta)

    assert result.records == []
    assert rules(result) == ["LAYOUT_COLUMN_MISSING", "FIELD_COUNT_MISMATCH"]
    assert result.detail_rows_read == 1


def test_unknown_record_type_is_reported(meta):
    result = parse_member_lines([HEADER, "|T|5"], meta)

    assert "UNKNOWN_RECORD_TYPE" in rules(result)


def test_file_without_header_fails_fast(meta):
    with pytest.raises(MissingHeaderError):
        parse_member_lines([ELENA], meta)


def test_empty_file_fails_fast(meta):
    with pytest.raises(MissingHeaderError):
        parse_member_lines([], meta)


def test_records_carry_lineage(meta):
    result = parse_member_lines([HEADER, "", ELENA], meta)

    record = result.records[0]
    assert record.source_file == meta.file_name
    assert record.line_number == 3
    assert record.business_date == meta.business_date
