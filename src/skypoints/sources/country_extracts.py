"""Adapters for the per-country sample extracts (AUS, USA, IND as .xlsx or .csv).

Each extract has its own column names and date encodings. An adapter maps it
onto the canonical member layout (the same text the flat file would carry), so
the exact same staging and DQ rules apply to every source. Adding a source
means adding one ExtractSpec, with no new transformation code.

Important finding: the IDs in these extracts are 1, 2, 3 in every file, so they
are local to each source system, not global member IDs. They are kept as-is and
the collision is reported; they must not be merged with the main feed without a
cross-reference table.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from openpyxl import load_workbook

from skypoints.models import DQIssue, RawMemberRecord, Severity

# Canonical text formats expected by the member layout (see layout.py).
LAYOUT_DATE_FORMATS = {"enrollment_date": "%Y%m%d", "last_flight_date": "%Y%m%d", "dob": "%m%d%Y"}
NULL_TEXT = frozenset({"", "NULL", "NONE"})

# Type aliases keep the signatures short and readable.
SourceRow = dict[str, object]
Records = list[RawMemberRecord]
Issues = list[DQIssue]
ConvertedDate = tuple[str | None, bool]


@dataclass(frozen=True)
class ExtractSpec:
    country: str
    column_map: dict  # source header -> canonical column name


EXTRACT_SPECS = {
    "AUS": ExtractSpec(
        country="AUS",
        column_map={
            "Unique ID": "member_id",
            "Member Name": "member_name",
            "Tier Type": "tier_code",
            "Date of Birth": "dob",
            "Date of Enrollment": "enrollment_date",
            "Date of Flight": "last_flight_date",
        },
    ),
    "USA": ExtractSpec(
        country="USA",
        column_map={
            "ID": "member_id",
            "Name": "member_name",
            "TierCode": "tier_code",
            "EnrollmentDate": "enrollment_date",
            "FlightDate": "last_flight_date",
        },
    ),
    "IND": ExtractSpec(
        country="IND",
        column_map={
            "ID": "member_id",
            "Name": "member_name",
            "DOB": "dob",
            "TierCode": "tier_code",
            "EnrollmentDate": "enrollment_date",
            "Individual or Corporate": "member_type",
            "Flight Date": "last_flight_date",
        },
    ),
}


def _read_rows(path: Path) -> Iterator[SourceRow]:
    """Yield one dict per data row, from either a CSV or the first sheet of an Excel file."""
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            yield from csv.DictReader(handle)
        return

    sheet = load_workbook(path, read_only=True, data_only=True).worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    headers = [str(header).strip() for header in next(rows)]
    for values in rows:
        if any(value is not None for value in values):
            yield dict(zip(headers, values, strict=False))


def to_canonical_date(value: object, column: str) -> ConvertedDate:
    """Return (canonical date text, was_ambiguous).

    Unparseable values are passed through untouched, so the shared INVALID_DATE
    rule reports them with the original value (e.g. '2021-13-13').
    """
    target_format = LAYOUT_DATE_FORMATS.get(column)
    if value is None or str(value).strip().upper() in NULL_TEXT:
        return None, False
    if isinstance(value, datetime | date):
        return value.strftime(target_format), False

    text = str(value).strip()
    if text.endswith(".0"):  # numbers read from CSV/Excel can arrive as floats
        text = text[:-2]

    if text.isdigit() and len(text) in (7, 8):
        # The USA extract stores MMDDYYYY as an integer, so January loses its leading
        # zero (1052022). A 7-digit value is ambiguous (1/05 or 10/5). We assume the
        # day always has two digits, which holds for every 8-digit value in the sample,
        # and flag the value so a human can confirm.
        try:
            parsed = datetime.strptime(text.zfill(8), "%m%d%Y")
        except ValueError:
            return text, False
        return parsed.strftime(target_format), len(text) == 7

    for source_format in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(text, source_format)
            return parsed.strftime(target_format), False
        except ValueError:
            continue

    return text, False


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text.upper() in NULL_TEXT else text


def read_country_extract(path: str | Path, as_of: date) -> tuple[Records, Issues]:
    """Read one country extract and map it onto the canonical member layout."""
    path = Path(path)
    spec = EXTRACT_SPECS.get(path.stem.upper())
    if spec is None:
        known = ", ".join(EXTRACT_SPECS)
        raise ValueError(f"No extract spec for '{path.name}'. Known extracts: {known}")

    records: Records = []
    issues: Issues = []
    extract_ts = datetime.combine(as_of, time.min)
    id_column = next(source for source, canonical in spec.column_map.items() if canonical == "member_id")

    for line_number, row in enumerate(_read_rows(path), start=2):  # row 1 is the header
        values = {"country": spec.country}
        for source_column, canonical in spec.column_map.items():
            raw = row.get(source_column)
            if canonical not in LAYOUT_DATE_FORMATS:
                values[canonical] = _clean_text(raw)
                continue
            converted, ambiguous = to_canonical_date(raw, canonical)
            values[canonical] = converted
            if ambiguous:
                issues.append(
                    DQIssue(
                        rule="AMBIGUOUS_DATE_FORMAT",
                        severity=Severity.WARNING,
                        message=f"{source_column}={raw} has 7 digits; interpreted as {converted}",
                        source_file=path.name,
                        line_number=line_number,
                        member_id=_clean_text(row.get(id_column)),
                        column=canonical,
                    )
                )
        records.append(RawMemberRecord(values, path.name, line_number, as_of, extract_ts))
    return records, issues
