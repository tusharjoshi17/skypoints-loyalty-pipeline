-- =============================================================================
-- 06_load_raw.sql
--
-- Loads staged inbound files into the lossless RAW layer.
--
-- File movement:
--
--   @RAW.STG_SKYPOINTS_INBOUND/members
--                     |
--                     v
--              RAW.MEMBER_LANDING
--
--   @RAW.STG_SKYPOINTS_INBOUND/redemptions
--                     |
--                     v
--           RAW.REDEMPTION_LANDING
--
-- Snowflake load metadata is persisted for lineage.
-- =============================================================================

USE DATABASE SKYPOINTS;
USE WAREHOUSE SKYPOINTS_ETL_WH;


-- =============================================================================
-- MEMBER FEED
--
-- One physical input line becomes one RAW row.
-- =============================================================================

COPY INTO RAW.MEMBER_LANDING
(
    raw_line,
    source_file,
    file_row_number,
    file_last_modified
)
FROM
(
    SELECT
        $1,
        METADATA$FILENAME,
        METADATA$FILE_ROW_NUMBER,
        METADATA$FILE_LAST_MODIFIED

    FROM @RAW.STG_SKYPOINTS_INBOUND/members
        (FILE_FORMAT => RAW.FF_MEMBER_LINE)
)
ON_ERROR = 'ABORT_STATEMENT';


-- =============================================================================
-- REDEMPTION FEED
--
-- JSON remains VARIANT in RAW.
-- =============================================================================

COPY INTO RAW.REDEMPTION_LANDING
(
    payload,
    source_file,
    file_row_number,
    file_last_modified
)
FROM
(
    SELECT
        $1,
        METADATA$FILENAME,
        METADATA$FILE_ROW_NUMBER,
        METADATA$FILE_LAST_MODIFIED

    FROM @RAW.STG_SKYPOINTS_INBOUND/redemptions
        (FILE_FORMAT => RAW.FF_REDEMPTION_JSON)
)
ON_ERROR = 'ABORT_STATEMENT';