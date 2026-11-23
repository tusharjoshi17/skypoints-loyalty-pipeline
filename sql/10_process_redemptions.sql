-- =============================================================================
-- 10_process_redemptions.sql
--
-- RAW JSON -> flattened redemption staging -> DQ -> current transaction state.
-- =============================================================================

USE DATABASE SKYPOINTS;
USE WAREHOUSE SKYPOINTS_ETL_WH;

-- Transaction-level lineage is needed because one parent JSON row can contain
-- several redemptions and only one of those transactions may be invalid.
ALTER TABLE AUDIT.DQ_ISSUES
    ADD COLUMN IF NOT EXISTS txn_id VARCHAR(50);


-- =============================================================================
-- STAGE / FLATTEN
-- =============================================================================

TRUNCATE TABLE STAGING.REDEMPTION_TXN_STG;


INSERT INTO STAGING.REDEMPTION_TXN_STG
(
    source_file,
    file_row_number,
    txn_index,
    member_id,
    feed_date,
    txn_id,
    txn_date,
    partner,
    miles_redeemed,
    status,
    raw_txn,
    dq_status
)

SELECT
    raw.source_file,
    raw.file_row_number,
    flattened.index,

    raw.payload:member_id::VARCHAR,

    TRY_TO_DATE(
        raw.payload:feed_date::VARCHAR,
        'YYYYMMDD'
    ),

    flattened.value:txn_id::VARCHAR,

    TRY_TO_DATE(
        flattened.value:txn_date::VARCHAR,
        'YYYYMMDD'
    ),

    flattened.value:partner::VARCHAR,

    TRY_TO_NUMBER(
        flattened.value:miles_redeemed::VARCHAR
    ),

    UPPER(
        flattened.value:status::VARCHAR
    ),

    flattened.value,

    'PENDING'

FROM RAW.REDEMPTION_LANDING AS raw,

LATERAL FLATTEN(
    INPUT => raw.payload:redemptions
) AS flattened;


-- =============================================================================
-- REBUILD REDEMPTION DQ
-- =============================================================================

DELETE FROM AUDIT.DQ_ISSUES
WHERE feed = 'REDEMPTIONS';


-- Missing transaction ID
INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    txn_id,
    column_name,
    message
)

SELECT
    'TXN_ID_MISSING',
    'ERROR',
    'REDEMPTIONS',
    source_file,
    file_row_number,
    member_id,
    txn_id,
    'txn_id',
    'redemption transaction has no txn_id'

FROM STAGING.REDEMPTION_TXN_STG

WHERE txn_id IS NULL;


-- Invalid transaction date
INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    txn_id,
    column_name,
    message
)

SELECT
    'INVALID_DATE',
    'ERROR',
    'REDEMPTIONS',
    source_file,
    file_row_number,
    member_id,
    txn_id,
    'txn_date',
    'transaction date is invalid'

FROM STAGING.REDEMPTION_TXN_STG

WHERE raw_txn:txn_date IS NOT NULL
  AND txn_date IS NULL;

-- Transaction after feed date
INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    txn_id,
    column_name,
    message
)

SELECT
    'TXN_AFTER_FEED_DATE',
    'ERROR',
    'REDEMPTIONS',
    source_file,
    file_row_number,
    member_id,
    txn_id,
    'txn_date',
    'transaction date is after feed date'

FROM STAGING.REDEMPTION_TXN_STG

WHERE txn_date > feed_date;


-- Miles must be positive
INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    txn_id,
    column_name,
    message
)

SELECT
    'INVALID_MILES',
    'ERROR',
    'REDEMPTIONS',
    source_file,
    file_row_number,
    member_id,
    txn_id,
    'miles_redeemed',
    'miles_redeemed must be a positive integer'

FROM STAGING.REDEMPTION_TXN_STG

WHERE miles_redeemed IS NULL
   OR miles_redeemed <= 0;


-- Known statuses only
INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    txn_id,
    column_name,
    message
)

SELECT
    'INVALID_STATUS',
    'ERROR',
    'REDEMPTIONS',
    source_file,
    file_row_number,
    member_id,
    txn_id,
    'status',
    'unknown redemption status='
        || COALESCE(status, 'NULL')

FROM STAGING.REDEMPTION_TXN_STG

WHERE status IS NULL
   OR status NOT IN
   (
       'COMPLETED',
       'PENDING',
       'CANCELLED',
       'REVERSED'
   );


-- Orphan redemption
INSERT INTO AUDIT.DQ_ISSUES
(
    rule_code,
    severity,
    feed,
    source_file,
    file_row_number,
    member_id,
    txn_id,
    column_name,
    message
)

SELECT
    'ORPHAN_REDEMPTION',
    'WARNING',
    'REDEMPTIONS',
    txn.source_file,
    txn.file_row_number,
    txn.member_id,
    txn.txn_id,
    'member_id',
    'member_id has redemption activity but no member profile'

FROM STAGING.REDEMPTION_TXN_STG AS txn

LEFT JOIN CORE.MEMBER_CURRENT AS member
    ON txn.member_id = member.member_id

WHERE txn.member_id IS NOT NULL
  AND member.member_id IS NULL;


-- =============================================================================
-- UPDATE DQ STATUS
-- =============================================================================

UPDATE STAGING.REDEMPTION_TXN_STG AS txn

SET dq_status =
    IFF(
        EXISTS
        (
            SELECT 1

            FROM AUDIT.DQ_ISSUES AS issue

            WHERE issue.feed = 'REDEMPTIONS'
              AND issue.severity = 'ERROR'
              AND issue.source_file = txn.source_file
              AND issue.file_row_number = txn.file_row_number
              AND
              (
                  issue.txn_id = txn.txn_id
                  OR (
                      issue.txn_id IS NULL
                      AND txn.txn_id IS NULL
                  )
              )
        ),
        'REJECTED',
        'VALID'
    );

-- =============================================================================
-- LATEST TRANSACTION STATE
--
-- Example:
--
-- Day 1: RX10092 = PENDING
-- Day 2: RX10092 = COMPLETED
--
-- Latest feed wins.
-- =============================================================================

MERGE INTO CORE.REDEMPTION_TXN AS target

USING
(
    SELECT
        txn_id,
        member_id,
        txn_date,
        partner,
        miles_redeemed,
        status,
        feed_date,
        source_file

    FROM STAGING.REDEMPTION_TXN_STG

    WHERE dq_status = 'VALID'
      AND txn_id IS NOT NULL

    QUALIFY ROW_NUMBER() OVER
    (
        PARTITION BY txn_id

        ORDER BY
            feed_date DESC,
            file_row_number DESC,
            txn_index DESC
    ) = 1
) AS source

ON target.txn_id = source.txn_id


WHEN MATCHED
AND source.feed_date > target.feed_date

THEN UPDATE SET

    target.member_id =
        source.member_id,

    target.txn_date =
        source.txn_date,

    target.partner =
        source.partner,

    target.miles_redeemed =
        source.miles_redeemed,

    target.status =
        source.status,

    target.feed_date =
        source.feed_date,

    target.source_file =
        source.source_file,

    target.updated_at =
        CURRENT_TIMESTAMP()


WHEN NOT MATCHED THEN INSERT
(
    txn_id,
    member_id,
    txn_date,
    partner,
    miles_redeemed,
    status,
    feed_date,
    source_file
)

VALUES
(
    source.txn_id,
    source.member_id,
    source.txn_date,
    source.partner,
    source.miles_redeemed,
    source.status,
    source.feed_date,
    source.source_file
);


-- =============================================================================
-- MARK STAGING LIFECYCLE
-- =============================================================================

UPDATE STAGING.REDEMPTION_TXN_STG

SET dq_status = 'PUBLISHED'

WHERE dq_status = 'VALID';