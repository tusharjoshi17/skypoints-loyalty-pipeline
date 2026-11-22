-- =============================================================================
-- 01_file_formats.sql
--
-- Named file formats define how Snowflake interprets inbound files.
-- =============================================================================

USE DATABASE SKYPOINTS;
USE SCHEMA RAW;


-- -----------------------------------------------------------------------------
-- Member feed
--
-- Important design decision:
--
-- We deliberately load ONE PHYSICAL LINE as ONE STRING rather than asking
-- Snowflake to split the pipe-delimited fields during COPY.
--
-- Why?
--
-- The assessment sample header has 10 fields while the documented layout has
-- 11 because Post_Code is missing. Positional loading could shift DOB into
-- Post_Code. The RAW layer therefore preserves the original line exactly.
-- -----------------------------------------------------------------------------

CREATE FILE FORMAT IF NOT EXISTS RAW.FF_MEMBER_LINE
    TYPE = CSV
    FIELD_DELIMITER = NONE
    RECORD_DELIMITER = '\n'
    SKIP_HEADER = 0
    TRIM_SPACE = FALSE
    EMPTY_FIELD_AS_NULL = FALSE
    ENCODING = 'UTF8';


-- -----------------------------------------------------------------------------
-- Redemption JSON
--
-- JSON is landed as VARIANT in RAW.REDEMPTION_LANDING.
-- STRIP_OUTER_ARRAY allows an outer JSON array to be treated as individual
-- records during loading.
-- -----------------------------------------------------------------------------

CREATE FILE FORMAT IF NOT EXISTS RAW.FF_REDEMPTION_JSON
    TYPE = JSON
    STRIP_OUTER_ARRAY = TRUE
    IGNORE_UTF8_ERRORS = FALSE;