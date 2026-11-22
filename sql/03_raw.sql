-- =============================================================================
-- 03_raw.sql
--
-- RAW is the lossless landing layer.
--
-- Rules:
--   1. Never transform source values here.
--   2. Never reject a valid physical record because of a business rule.
--   3. Retain file and row lineage.
--   4. Type business attributes later in STAGING.
-- =============================================================================

USE DATABASE SKYPOINTS;
USE SCHEMA RAW;


-- -----------------------------------------------------------------------------
-- Member flat-file landing table
--
-- One physical input line -> one RAW row.
-- -----------------------------------------------------------------------------

CREATE TRANSIENT TABLE IF NOT EXISTS RAW.MEMBER_LANDING
(
    raw_line           VARCHAR       NOT NULL,

    source_file        VARCHAR(500)  NOT NULL,
    file_row_number    NUMBER(18, 0) NOT NULL,
    file_last_modified TIMESTAMP_NTZ,

    loaded_at          TIMESTAMP_LTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP()
)
DATA_RETENTION_TIME_IN_DAYS = 1
COMMENT = 'Lossless landing table for SkyPoints member flat files';


-- -----------------------------------------------------------------------------
-- Redemption JSON landing table
-- -----------------------------------------------------------------------------

CREATE TRANSIENT TABLE IF NOT EXISTS RAW.REDEMPTION_LANDING
(
    payload            VARIANT       NOT NULL,

    source_file        VARCHAR(500)  NOT NULL,
    file_row_number    NUMBER(18, 0) NOT NULL,
    file_last_modified TIMESTAMP_NTZ,

    loaded_at          TIMESTAMP_LTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP()
)
DATA_RETENTION_TIME_IN_DAYS = 1
COMMENT = 'Lossless landing table for partner redemption JSON feeds';

-- -----------------------------------------------------------------------------
-- Streams
--
-- Streams track changes since the last successful consumer transaction.
-- APPEND_ONLY is appropriate because the landing tables only receive INSERTs.
-- -----------------------------------------------------------------------------

CREATE STREAM IF NOT EXISTS RAW.MEMBER_LANDING_STREAM
    ON TABLE RAW.MEMBER_LANDING
    APPEND_ONLY = TRUE;


CREATE STREAM IF NOT EXISTS RAW.REDEMPTION_LANDING_STREAM
    ON TABLE RAW.REDEMPTION_LANDING
    APPEND_ONLY = TRUE;