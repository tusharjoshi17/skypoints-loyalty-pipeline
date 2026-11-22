"""Streaming parser for the pipe-delimited member flat file.

Design choices:
* Header-driven: columns are mapped by the names in the |H| record, not by
  position. The sample header has 10 columns while the layout has 11 (Post Code
  is missing), so position-based parsing would silently shift DOB into Post Code.
* Streaming: lines are yielded one at a time, so memory stays flat regardless
  of file size. At billions of rows the production path is Snowflake COPY INTO;
  this parser is the reference implementation and test harness.
* Lossless: values are kept as strings; typing happens in the staging step.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from skypoints.layout import (
    DELIMITER,
    DETAIL_RECORD_TYPE,
    FIELDS_BY_HEADER,
    HEADER_RECORD_TYPE,
    MEMBER_LAYOUT,
)
from skypoints.models import DQIssue, FileMetadata, RawMemberRecord, Severity

_UNKNOWN_PREFIX = "__unknown__"
_NULL_TOKENS = frozenset({"", "NULL", "null"})
_STRUCTURAL_RULES = frozenset({"FIELD_COUNT_MISMATCH", "UNKNOWN_RECORD_TYPE"})


class MissingHeaderError(ValueError):
    """Raised when a member file does not start with a |H| header record."""


@dataclass
class ParseResult:
    records: list[RawMemberRecord] = field(default_factory=list)
    issues: list[DQIssue] = field(default_factory=list)
    detail_rows_read: int = 0


def _split_record(line: str) -> list[str]:
    """Split '|D|a|b' style lines. The leading delimiter produces an empty first token."""
    tokens = line.rstrip("\r\n").split(DELIMITER)
    if tokens and tokens[0] == "":
        tokens = tokens[1:]
    return [token.strip() for token in tokens]


def _empty_to_none(value: str) -> str | None:
    return None if value in _NULL_TOKENS else value


def _read_header(tokens: list[str], meta: FileMetadata) -> tuple[list[str], list[DQIssue]]:
    """Map header column names to canonical names and report layout drift."""
    issues: list[DQIssue] = []
    columns: list[str] = []

    for header_name in tokens[1:]:
        spec = FIELDS_BY_HEADER.get(header_name.upper())
        if spec is None:
            issues.append(
                DQIssue(
                    "UNKNOWN_HEADER_COLUMN",
                    Severity.WARNING,
                    f"Header column '{header_name}' is not in the layout; it will be ignored",
                    meta.file_name,
                    1,
                )
            )
            columns.append(_UNKNOWN_PREFIX + header_name)
        else:
            columns.append(spec.name)

    missing = [spec.header_name for spec in MEMBER_LAYOUT if spec.name not in columns]
    if missing:
        issues.append(
            DQIssue(
                "LAYOUT_COLUMN_MISSING",
                Severity.WARNING,
                f"Header is missing layout column(s): {', '.join(missing)}; loaded as NULL",
                meta.file_name,
                1,
            )
        )
    return columns, issues


def iter_member_records(lines: Iterable[str], meta: FileMetadata) -> Iterator[RawMemberRecord | DQIssue]:
    """Yield a RawMemberRecord per valid detail line, or a DQIssue for structural problems."""
    columns: list[str] | None = None

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        tokens = _split_record(line)
        record_type = tokens[0].upper()

        if columns is None:
            if record_type != HEADER_RECORD_TYPE:
                raise MissingHeaderError(f"{meta.file_name}: first record must be a header (|H|)")
            columns, header_issues = _read_header(tokens, meta)
            yield from header_issues
            continue

        if record_type != DETAIL_RECORD_TYPE:
            yield DQIssue(
                "UNKNOWN_RECORD_TYPE",
                Severity.ERROR,
                f"Record type '{record_type}' is not supported",
                meta.file_name,
                line_number,
            )
            continue

        values = tokens[1:]
        if len(values) != len(columns):
            yield DQIssue(
                "FIELD_COUNT_MISMATCH",
                Severity.ERROR,
                f"Expected {len(columns)} fields, found {len(values)}",
                meta.file_name,
                line_number,
            )
            continue

        mapped = {
            column: _empty_to_none(value)
            for column, value in zip(columns, values, strict=True)
            if not column.startswith(_UNKNOWN_PREFIX)
        }
        for spec in MEMBER_LAYOUT:  # columns absent from the header become NULL
            mapped.setdefault(spec.name, None)

        yield RawMemberRecord(
            values=mapped,
            source_file=meta.file_name,
            line_number=line_number,
            business_date=meta.business_date,
            extract_ts=meta.extract_ts,
        )

    if columns is None:
        raise MissingHeaderError(f"{meta.file_name}: file is empty")


def parse_member_lines(lines: Iterable[str], meta: FileMetadata) -> ParseResult:
    """Collect the streaming parser output into a ParseResult (handy for small files and tests)."""
    result = ParseResult()
    for item in iter_member_records(lines, meta):
        if isinstance(item, RawMemberRecord):
            result.records.append(item)
            result.detail_rows_read += 1
        else:
            result.issues.append(item)
            if item.rule in _STRUCTURAL_RULES:
                result.detail_rows_read += 1
    return result
