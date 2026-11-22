"""Country reference data: normalisation of source codes and target-table routing.

The source sends a mix of ISO alpha-2 (AU), alpha-3 (USA) and free-text codes (PHIL). 
Everything is normalised to ISO 3166-1 alpha-3 before routing so that "AU" and "AUS" end up in the same table.
"""
from __future__ import annotations

# source code (upper-cased, trimmed) -> ISO 3166-1 alpha-3
COUNTRY_ALIASES: dict[str, str] = {
    "USA": "USA", "US": "USA",
    "IND": "IND", "IN": "IND",
    "PHL": "PHL", "PH": "PHL", "PHIL": "PHL",
    "CAN": "CAN", "CA": "CAN",
    "AUS": "AUS", "AU": "AUS",
}

# ISO alpha-3 -> target table. Adding a country = adding one line here
# (and one row in the SKYPOINTS.CONFIG.COUNTRY_ROUTING table in Snowflake).
COUNTRY_TARGET_TABLES: dict[str, str] = {
    "USA": "TABLE_USA",
    "IND": "TABLE_INDIA",
    "PHL": "TABLE_PHILIPPINES",
    "CAN": "TABLE_CANADA",
    "AUS": "TABLE_AUSTRALIA",
}

def normalize_country(raw_code: str | None) -> str | None:
     """Return the ISO alpha-3 code for a source country code, or None if unknown."""
     if raw_code is None:
          return None
     return COUNTRY_ALIASES.get(raw_code.strip().upper())

def target_table_for(country_code: str) -> str:
    """Return the target table for a normalised country code.

    Raises KeyError for countries without a configured table, so routing can never silently drop a member.
    """
    return COUNTRY_TARGET_TABLES[country_code]