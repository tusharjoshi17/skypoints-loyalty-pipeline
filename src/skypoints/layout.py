"""Member flat-file layout, taken from the SkyPoints design document.

The layout is the single source of truth for the field rules (length, type, mandatory). The parser and the validations both read from it, so a change to
the contract only has to be made here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

class DataType(str, Enum):
    VARCHAR = "VARCHAR"
    CHAR = "CHAR"
    DATE = "DATE"
    INT = "INT"

@dataclass(frozen=True)
class FieldSpec:
    """One column of the member flat file, as described in the design doc"""

    position: int
    name: str #canonical snake_case name used everywhere downstream
    header_name: str #name used in the |H| header record
    max_length: int
    data_type: DataType
    mandatory: bool
    spec_key: bool #'Key Column' flag exactly as written in the design doc
    date_format: str | None = None #strptime format, only for DATE fields

MEMBER_LAYOUT: tuple[FieldSpec, ...] = (
    FieldSpec(1, "member_name", "Member_Name", 255, DataType.VARCHAR, True, True),
    FieldSpec(2, "member_id", "Member_ID", 18, DataType.VARCHAR, True, False),
    FieldSpec(3, "enrollment_date", "Enrollment_Date", 8, DataType.DATE, True, False, "%Y%m%d"),
    FieldSpec(4, "last_flight_date", "Last_Flight_Date", 8, DataType.DATE, False, False, "%Y%m%d"),
    FieldSpec(5, "tier_code", "Tier_Code", 5, DataType.CHAR, False, False),
    FieldSpec(6, "agent_name", "Agent_Name", 255, DataType.CHAR, False, False),
    FieldSpec(7, "state", "State", 5, DataType.CHAR, False, False),
    FieldSpec(8, "country", "Country", 5, DataType.CHAR, False, False),
    FieldSpec(9, "post_code", "Post_Code", 5, DataType.INT, False, False),
    # The sample file carries DOB as MMDDYYYY (03051985), unlike the other dates.
    FieldSpec(10, "dob", "DOB", 8, DataType.DATE, False, False, "%m%d%Y"),
    FieldSpec(11, "is_active", "Is_Active", 1, DataType.CHAR, False, False),
)

FIELDS_BY_NAME: dict[str, FieldSpec] = {f.name: f for f in MEMBER_LAYOUT}
FIELDS_BY_HEADER: dict[str, FieldSpec] = {f.header_name.upper(): f for f in MEMBER_LAYOUT}

HEADER_RECORD_TYPE = 'H'
DETAIL_RECORD_TYPE = 'D'
DELIMITER = '|'

# Business reference data. Kept here (not hard-coded in rules) so it is easy to extend.
VALID_TIER_CODES = frozenset({"PLT", "GLD", "SLV"})
VALID_ACTIVE_FLAGS = frozenset({"A", "I"})
STALE_MEMBER_THRESHOLD_DAYS = 90
