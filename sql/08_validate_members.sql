-- =============================================================================
-- 08_validate_members.sql
--
-- Applies member data-quality rules to STAGING.MEMBER_STG.
--
-- Severity policy:
--
-- ERROR
--     Record is rejected and never reaches CORE.
--
-- WARNING
--     Record remains eligible for CORE but the issue is audited.
--
-- The script is idempotent for the demo batch: member DQ issues are rebuilt
-- from the current staging contents on every run.
-- =============================================================================

USE DATABASE SKYPOINTS;
USE WAREHOUSE SKYPOINTS_ETL_WH;


-- -----------------------------------------------------------------------------
-- Rebuild member validation issues for the current staged batch.
--
-- Redemption issues will later use FEED = 'REDEMPTIONS', so they aren't touched.
-- -----------------------------------------------------------------------------

DELETE FROM AUDIT.DQ_ISSUES
WHERE feed = 'MEMBERS';


-- =============================================================================
-- ERRORS
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Structural error: row has a different number of fields from its file header.
-- -----------------------------------------------------------------------------

INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    column_name,
    message
)

SELECT
    'FIELD_COUNT_MISMATCH',
    'ERROR',
    'MEMBERS',
    source_file,
    file_row_number,
    member_id,
    NULL,
    'Expected '
        || expected_field_count
        || ' business fields but found '
        || field_count

FROM STAGING.MEMBER_STG

WHERE field_count <> expected_field_count;


-- -----------------------------------------------------------------------------
-- Mandatory fields
-- -----------------------------------------------------------------------------

INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    column_name,
    message
)

SELECT
    'MANDATORY_FIELD_MISSING',
    'ERROR',
    'MEMBERS',
    source_file,
    file_row_number,
    member_id,
    'member_name',
    'member_name is mandatory'

FROM STAGING.MEMBER_STG

WHERE member_name IS NULL;


INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    column_name,
    message
)

SELECT
    'MANDATORY_FIELD_MISSING',
    'ERROR',
    'MEMBERS',
    source_file,
    file_row_number,
    member_id,
    'member_id',
    'member_id is mandatory'

FROM STAGING.MEMBER_STG

WHERE member_id IS NULL;


INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    column_name,
    message
)

SELECT
    'MANDATORY_FIELD_MISSING',
    'ERROR',
    'MEMBERS',
    source_file,
    file_row_number,
    member_id,
    'enrollment_date',
    'enrollment_date is mandatory'

FROM STAGING.MEMBER_STG

WHERE enrollment_date_raw IS NULL;


-- -----------------------------------------------------------------------------
-- Invalid mandatory enrollment date
-- -----------------------------------------------------------------------------

INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    column_name,
    message
)

SELECT
    'INVALID_DATE',
    'ERROR',
    'MEMBERS',
    source_file,
    file_row_number,
    member_id,
    'enrollment_date',
    'enrollment_date='
        || enrollment_date_raw
        || ' is not a valid YYYYMMDD date'

FROM STAGING.MEMBER_STG

WHERE enrollment_date_raw IS NOT NULL
  AND enrollment_date IS NULL;


-- -----------------------------------------------------------------------------
-- Unknown / unroutable country
-- -----------------------------------------------------------------------------

INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    column_name,
    message
)

SELECT
    'UNKNOWN_COUNTRY',
    'ERROR',
    'MEMBERS',
    source_file,
    file_row_number,
    member_id,
    'country',
    'country='
        || COALESCE(country_raw, 'NULL')
        || ' has no routing rule'

FROM STAGING.MEMBER_STG

WHERE country_code IS NULL;


-- =============================================================================
-- WARNINGS
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Tier isn't part of configured tier reference data.
-- -----------------------------------------------------------------------------

INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    column_name,
    message
)

SELECT
    'INVALID_TIER_CODE',
    'WARNING',
    'MEMBERS',
    member.source_file,
    member.file_row_number,
    member.member_id,
    'tier_code',
    'tier_code='
        || member.tier_code
        || ' is not configured'

FROM STAGING.MEMBER_STG AS member

LEFT JOIN CONFIG.TIER AS tier
    ON UPPER(member.tier_code) = tier.tier_code

WHERE member.tier_code IS NOT NULL
  AND tier.tier_code IS NULL;


-- -----------------------------------------------------------------------------
-- Active flag
-- -----------------------------------------------------------------------------

INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    column_name,
    message
)

SELECT
    'INVALID_ACTIVE_FLAG',
    'WARNING',
    'MEMBERS',
    source_file,
    file_row_number,
    member_id,
    'is_active',
    'is_active='
        || is_active
        || ' is not A or I'

FROM STAGING.MEMBER_STG

WHERE is_active IS NOT NULL
  AND is_active NOT IN ('A', 'I');


-- -----------------------------------------------------------------------------
-- Non-standard but recognized country representation.
--
-- Example:
--     PHIL -> PHL
--     AU   -> AUS
-- -----------------------------------------------------------------------------

INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    column_name,
    message
)

SELECT
    'NON_STANDARD_COUNTRY_CODE',
    'WARNING',
    'MEMBERS',
    source_file,
    file_row_number,
    member_id,
    'country',
    'country='
        || country_raw
        || ' normalized to '
        || country_code

FROM STAGING.MEMBER_STG

WHERE country_code IS NOT NULL
  AND UPPER(country_raw) <> country_code;


-- -----------------------------------------------------------------------------
-- Member IDs with a length different from the dominant length.
--
-- Sample examples:
--     22345
--     2256
--
-- while most IDs contain 6 characters.
-- -----------------------------------------------------------------------------

INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    column_name,
    message
)

WITH id_lengths AS
(
    SELECT
        LENGTH(member_id) AS id_length,
        COUNT(*) AS frequency

    FROM STAGING.MEMBER_STG

    WHERE member_id IS NOT NULL

    GROUP BY LENGTH(member_id)
),

dominant AS
(
    SELECT
        id_length

    FROM id_lengths

    QUALIFY ROW_NUMBER() OVER
    (
        ORDER BY frequency DESC, id_length DESC
    ) = 1
)

SELECT
    'MEMBER_ID_LENGTH_ANOMALY',
    'WARNING',
    'MEMBERS',
    member.source_file,
    member.file_row_number,
    member.member_id,
    'member_id',
    'member_id='
        || member.member_id
        || ' has '
        || LENGTH(member.member_id)
        || ' characters; dominant length is '
        || dominant.id_length

FROM STAGING.MEMBER_STG AS member

CROSS JOIN dominant

WHERE member.member_id IS NOT NULL
  AND LENGTH(member.member_id) <> dominant.id_length;


-- -----------------------------------------------------------------------------
-- Duplicate member_id within the staged batch.
--
-- This isn't an ERROR because latest-record-wins will resolve it.
-- -----------------------------------------------------------------------------

INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    column_name,
    message
)

SELECT
    'DUPLICATE_MEMBER_ID',
    'WARNING',
    'MEMBERS',
    MAX(source_file),
    NULL,
    member_id,
    'member_id',
    COUNT(*)
        || ' staged records exist for member_id '
        || member_id
        || '; latest record wins'

FROM STAGING.MEMBER_STG

WHERE member_id IS NOT NULL

GROUP BY member_id

HAVING COUNT(*) > 1;


-- -----------------------------------------------------------------------------
-- The design document identifies Member Name as the key.
--
-- We deliberately use Member ID as the actual operational key and report cases
-- where the documented key is not unique.
-- -----------------------------------------------------------------------------

INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    column_name,
    message
)

SELECT
    'SPEC_KEY_NOT_UNIQUE',
    'WARNING',
    'MEMBERS',
    'batch',
    NULL,
    NULL,
    'member_name',
    'member_name='
        || UPPER(member_name)
        || ' maps to '
        || COUNT(DISTINCT member_id)
        || ' different member IDs'

FROM STAGING.MEMBER_STG

WHERE member_name IS NOT NULL
  AND member_id IS NOT NULL

GROUP BY UPPER(member_name)

HAVING COUNT(DISTINCT member_id) > 1;


-- =============================================================================
-- Synchronize staging status with ERROR issues.
--
-- A record with no ERROR remains VALID even when WARNING issues exist.
-- =============================================================================

UPDATE STAGING.MEMBER_STG AS member

SET
    dq_status =
        IFF(
            EXISTS
            (
                SELECT 1

                FROM AUDIT.DQ_ISSUES AS issue

                WHERE issue.feed = 'MEMBERS'
                  AND issue.severity = 'ERROR'
                  AND issue.source_file = member.source_file
                  AND issue.file_row_number = member.file_row_number
            ),
            'REJECTED',
            'VALID'
        ),

    status_updated_at = CURRENT_TIMESTAMP();