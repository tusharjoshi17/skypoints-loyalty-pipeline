"""File-name contract for the inbound feeds.

Assumed naming specification (the brief says one exists but does not give it):

    SKYPOINTS_MEMBERS_<YYYYMMDD>_<HHMMSS>.txt       pipe-delimited member profiles
    SKYPOINTS_REDEMPTIONS_<YYYYMMDD>_<HHMMSS>.json  partner redemption feed

The business date in the name drives "as-of" logic (Age, Stale_Member) and the
"latest record wins" ordering, which makes re-runs deterministic: replaying an
old file gives the same result it gave on the day it arrived.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from skypoints.models import FileMetadata

_FILE_NAME_PATTERN = re.compile(
    r"^SKYPOINTS_(?P<feed>MEMBERS|REDEMPTIONS)_(?P<date>\d{8})_(?P<time>\d{6})\.(?P<ext>txt|json)$"
)
_EXPECTED_EXTENSION = {"MEMBERS": "txt", "REDEMPTIONS": "json"}


class InvalidFileNameError(ValueError):
    """Raised when an inbound file does not follow the naming contract."""


def parse_file_name(path: str | Path, expected_feed: str) -> FileMetadata:
    """Validate a feed file name and extract its business date and extract timestamp."""
    name = Path(path).name
    match = _FILE_NAME_PATTERN.match(name)
    if not match:
        raise InvalidFileNameError(f"'{name}' does not match the SkyPoints naming contract")

    feed = match.group("feed")
    if feed != expected_feed:
        raise InvalidFileNameError(f"'{name}' is a {feed} feed, expected {expected_feed}")

    expected_ext = _EXPECTED_EXTENSION.get(feed)
    if match.group("ext") != expected_ext:
        raise InvalidFileNameError(f"'{name}' must have extension .{expected_ext}")

    try:
        extract_ts = datetime.strptime(match.group("date") + match.group("time"), "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise InvalidFileNameError(f"'{name}' contains an invalid date/time") from exc

    return FileMetadata(file_name=name, business_date=extract_ts.date(), extract_ts=extract_ts)
