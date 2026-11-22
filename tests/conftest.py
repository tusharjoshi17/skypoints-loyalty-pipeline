"""Shared test fixtures."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from skypoints.models import FileMetadata

BUSINESS_DATE = date(2024, 1, 15)
EXTRACT_TS = datetime(2024, 1, 15, 1, 30)


@pytest.fixture
def meta() -> FileMetadata:
    return FileMetadata("SKYPOINTS_MEMBERS_20240115_013000.txt", BUSINESS_DATE, EXTRACT_TS)
