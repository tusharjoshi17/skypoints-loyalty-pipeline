-- =============================================================================
-- 11_assertions.sql
--
-- Post-run assertions for the SkyPoints reference batch.
--
-- These queries make pipeline correctness executable rather than relying on
-- visual inspection.
--
-- Each assertion returns PASS or FAIL together with the observed value.
-- =============================================================================

USE DATABASE SKYPOINTS;
USE WAREHOUSE SKYPOINTS_ETL_WH;


-- =============================================================================
-- MEMBER RECONCILIATION
-- =============================================================================

SELECT
    'MEMBER_RECONCILIATION' AS assertion_name,

    IFF(
        (
            SELECT COUNT(*)
            FROM STAGING.MEMBER_STG
        )
        =
        (
            SELECT COUNT(*)
            FROM STAGING.MEMBER_STG
            WHERE dq_status IN
            (
                'PUBLISHED',
                'REJECTED',
                'SUPERSEDED'
            )
        ),
        'PASS',
        'FAIL'
    ) AS result,

    (
        SELECT COUNT(*)
        FROM STAGING.MEMBER_STG
    ) AS observed_value,

    12 AS expected_value;


-- =============================================================================
-- CURRENT MEMBER COUNT
-- =============================================================================

SELECT
    'CURRENT_MEMBER_COUNT' AS assertion_name,

    IFF(
        COUNT(*) = 7,
        'PASS',
        'FAIL'
    ) AS result,

    COUNT(*) AS observed_value,

    7 AS expected_value

FROM CORE.MEMBER_CURRENT;


-- =============================================================================
-- NO DUPLICATE CURRENT MEMBERS
-- =============================================================================

SELECT
    'MEMBER_CURRENT_UNIQUE' AS assertion_name,

    IFF(
        COUNT(*) = COUNT(DISTINCT member_id),
        'PASS',
        'FAIL'
    ) AS result,

    COUNT(*) AS observed_value,

    COUNT(DISTINCT member_id) AS expected_value

FROM CORE.MEMBER_CURRENT;


-- =============================================================================
-- COUNTRY TABLE RECONCILIATION
-- =============================================================================

SELECT
    'COUNTRY_TABLE_RECONCILIATION' AS assertion_name,

    IFF(
        (
            SELECT COUNT(*)
            FROM CORE.MEMBER_CURRENT
        )
        =
        (
              (SELECT COUNT(*) FROM CORE.TABLE_USA)
            + (SELECT COUNT(*) FROM CORE.TABLE_INDIA)
            + (SELECT COUNT(*) FROM CORE.TABLE_PHILIPPINES)
            + (SELECT COUNT(*) FROM CORE.TABLE_CANADA)
            + (SELECT COUNT(*) FROM CORE.TABLE_AUSTRALIA)
        ),
        'PASS',
        'FAIL'
    ) AS result,

    (
          (SELECT COUNT(*) FROM CORE.TABLE_USA)
        + (SELECT COUNT(*) FROM CORE.TABLE_INDIA)
        + (SELECT COUNT(*) FROM CORE.TABLE_PHILIPPINES)
        + (SELECT COUNT(*) FROM CORE.TABLE_CANADA)
        + (SELECT COUNT(*) FROM CORE.TABLE_AUSTRALIA)
    ) AS observed_value,

    (
        SELECT COUNT(*)
        FROM CORE.MEMBER_CURRENT
    ) AS expected_value;


-- =============================================================================
-- RAVI COUNTRY MOVE
-- =============================================================================

SELECT
    'RAVI_CURRENT_COUNTRY' AS assertion_name,

    IFF(
        COUNT_IF(
            member_id = '223458'
            AND country_code = 'USA'
        ) = 1,
        'PASS',
        'FAIL'
    ) AS result,

    COUNT_IF(
        member_id = '223458'
        AND country_code = 'USA'
    ) AS observed_value,

    1 AS expected_value

FROM CORE.MEMBER_CURRENT;


SELECT
    'RAVI_REMOVED_FROM_INDIA' AS assertion_name,

    IFF(
        COUNT(*) = 0,
        'PASS',
        'FAIL'
    ) AS result,

    COUNT(*) AS observed_value,

    0 AS expected_value

FROM CORE.TABLE_INDIA

WHERE member_id = '223458';


SELECT
    'RAVI_COUNTRY_MOVE_AUDITED' AS assertion_name,

    IFF(
        COUNT(*) = 1,
        'PASS',
        'FAIL'
    ) AS result,

    COUNT(*) AS observed_value,

    1 AS expected_value

FROM AUDIT.MEMBER_COUNTRY_MOVES

WHERE member_id = '223458'
  AND from_country = 'IND'
  AND to_country = 'USA'
  AND business_date = '2024-01-16';


-- =============================================================================
-- PRIYA LATEST RECORD WINS
-- =============================================================================

SELECT
    'PRIYA_LATEST_RECORD_WINS' AS assertion_name,

    IFF(
        COUNT(*) = 1,
        'PASS',
        'FAIL'
    ) AS result,

    COUNT(*) AS observed_value,

    1 AS expected_value

FROM CORE.MEMBER_CURRENT

WHERE member_id = '223460'
  AND tier_code = 'GLD'
  AND last_flight_date = '2024-01-12'
  AND file_row_number = 4;


-- =============================================================================
-- REDEMPTION CURRENT STATE
-- =============================================================================

SELECT
    'CURRENT_REDEMPTION_COUNT' AS assertion_name,

    IFF(
        COUNT(*) = 4,
        'PASS',
        'FAIL'
    ) AS result,

    COUNT(*) AS observed_value,

    4 AS expected_value

FROM CORE.REDEMPTION_TXN;


SELECT
    'RX10092_LATEST_STATE' AS assertion_name,

    IFF(
        COUNT(*) = 1,
        'PASS',
        'FAIL'
    ) AS result,

    COUNT(*) AS observed_value,

    1 AS expected_value

FROM CORE.REDEMPTION_TXN

WHERE txn_id = 'RX10092'
  AND status = 'COMPLETED'
  AND feed_date = '2024-01-16';


SELECT
    'INVALID_REDEMPTION_EXCLUDED' AS assertion_name,

    IFF(
        COUNT(*) = 0,
        'PASS',
        'FAIL'
    ) AS result,

    COUNT(*) AS observed_value,

    0 AS expected_value

FROM CORE.REDEMPTION_TXN

WHERE txn_id = 'RX20002';


-- =============================================================================
-- EXPECTED DQ FINDINGS
-- =============================================================================

SELECT
    'INVALID_MILES_AUDITED' AS assertion_name,

    IFF(
        COUNT(*) = 1,
        'PASS',
        'FAIL'
    ) AS result,

    COUNT(*) AS observed_value,

    1 AS expected_value

FROM AUDIT.DQ_ISSUES

WHERE feed = 'REDEMPTIONS'
  AND rule_code = 'INVALID_MILES'
  AND txn_id = 'RX20002';


SELECT
    'ORPHAN_REDEMPTION_AUDITED' AS assertion_name,

    IFF(
        COUNT(*) = 1,
        'PASS',
        'FAIL'
    ) AS result,

    COUNT(*) AS observed_value,

    1 AS expected_value

FROM AUDIT.DQ_ISSUES

WHERE feed = 'REDEMPTIONS'
  AND rule_code = 'ORPHAN_REDEMPTION'
  AND txn_id = 'RX30001';