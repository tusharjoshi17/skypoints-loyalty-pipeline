-- =============================================================================
-- 04_staging_and_audit.sql
--
-- STAGING:
--   Parsed, typed and cleaned data from RAW.
--   Data-quality status is attached to each record.
--
-- AUDIT:
--   Permanent operational history of data-quality issues, country moves
--   and pipeline executions.
-- =============================================================================

USE DATABASE SKYPOINTS;
USE WAREHOUSE SKYPOINTS_ETL_WH;


-- =============================================================================
-- STAGING
-- =============================================================================

USE SCHEMA STAGING;


-- -----------------------------------------------------------------------------
-- Member staging table
--
-- Text columns intentionally use VARCHAR without a restrictive length here.
--
-- Reason:
-- If the source sends Member_Name with 300 characters while the contract says
-- 255, staging must still be able to receive the value so that the pipeline can
-- record FIELD_LENGTH_EXCEEDED.
--
-- Rejecting it during INSERT would prevent proper data-quality reporting.
-- -----------------------------------------------------------------------------

CREATE TRANSIENT TABLE IF NOT EXISTS STAGING.MEMBER_STG
(
    -- -------------------------------------------------------------------------
    -- Lineage
    -- -------------------------------------------------------------------------

    source_file           VARCHAR(500)  NOT NULL,
    file_row_number       NUMBER(18, 0) NOT NULL,

    record_type           VARCHAR,

    business_date         DATE          NOT NULL,
    extract_ts            TIMESTAMP_NTZ NOT NULL,

    field_count           NUMBER(4, 0),
    expected_field_count  NUMBER(4, 0),


    -- -------------------------------------------------------------------------
    -- Typed business columns
    -- -------------------------------------------------------------------------

    member_name           VARCHAR,
    member_id             VARCHAR,

    enrollment_date       DATE,
    last_flight_date      DATE,

    tier_code             VARCHAR,
    agent_name            VARCHAR,
    state                 VARCHAR,

    country_code          CHAR(3),

    post_code             NUMBER(5, 0),

    dob                   DATE,
    is_active             VARCHAR,


    -- -------------------------------------------------------------------------
    -- Raw values retained after parsing
    --
    -- These let us report exactly what was wrong.
    --
    -- Example:
    --     enrollment_date_raw = '2021-13-13'
    --     enrollment_date     = NULL
    -- -------------------------------------------------------------------------

    enrollment_date_raw   VARCHAR,
    last_flight_date_raw  VARCHAR,
    dob_raw               VARCHAR,
    post_code_raw         VARCHAR,
    country_raw           VARCHAR,


    -- -------------------------------------------------------------------------
    -- Derived columns required by the assessment
    -- -------------------------------------------------------------------------

    age                    NUMBER(3, 0),

    days_since_last_flight NUMBER(9, 0),

    is_stale_member        BOOLEAN,


    -- -------------------------------------------------------------------------
    -- Data-quality lifecycle
    --
    -- PENDING
    --     |
    --     +--> VALID
    --     |      |
    --     |      +--> PUBLISHED
    --     |      +--> SUPERSEDED
    --     |      +--> IGNORED_OLDER
    --     |
    --     +--> REJECTED
    -- -------------------------------------------------------------------------

    dq_status             VARCHAR(20)
        NOT NULL
        DEFAULT 'PENDING',

    staged_at             TIMESTAMP_LTZ
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP(),

    status_updated_at     TIMESTAMP_LTZ
)
COMMENT = 'Typed and validated member staging records';


-- -----------------------------------------------------------------------------
-- Redemption transaction staging
--
-- One nested redemption transaction will become one relational row.
-- -----------------------------------------------------------------------------

CREATE TRANSIENT TABLE IF NOT EXISTS STAGING.REDEMPTION_TXN_STG
(
    source_file       VARCHAR(500)  NOT NULL,
    file_row_number   NUMBER(18, 0) NOT NULL,

    txn_index         NUMBER(9, 0),

    member_id         VARCHAR,

    feed_date         DATE,

    txn_id            VARCHAR,

    txn_date          DATE,

    partner           VARCHAR,

    miles_redeemed    NUMBER(18, 0),

    status            VARCHAR,

    raw_txn           VARIANT,

    dq_status         VARCHAR(20)
        NOT NULL
        DEFAULT 'PENDING',

    staged_at         TIMESTAMP_LTZ
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Flattened partner redemption transactions';


-- =============================================================================
-- AUDIT
-- =============================================================================

USE SCHEMA AUDIT;


-- -----------------------------------------------------------------------------
-- Data-quality issues
--
-- One row per rule violation.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS AUDIT.DQ_ISSUES
(
    rule_code         VARCHAR(50)   NOT NULL,

    severity          VARCHAR(10)   NOT NULL,

    feed              VARCHAR(20)   NOT NULL,

    source_file       VARCHAR(500),

    file_row_number   NUMBER(18, 0),

    member_id         VARCHAR,

    column_name       VARCHAR(100),

    message           VARCHAR,

    detected_at       TIMESTAMP_LTZ
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Data-quality issues detected by the SkyPoints pipeline';


-- -----------------------------------------------------------------------------
-- Member country movement history
--
-- Example:
--
--     223458 | IND | USA | 2024-01-16
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS AUDIT.MEMBER_COUNTRY_MOVES
(
    member_id         VARCHAR(18)   NOT NULL,

    from_country      CHAR(3)       NOT NULL,

    to_country        CHAR(3)       NOT NULL,

    business_date     DATE          NOT NULL,

    source_file       VARCHAR(500)  NOT NULL,

    recorded_at       TIMESTAMP_LTZ
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'History of members moving between country target tables';


-- -----------------------------------------------------------------------------
-- Pipeline operational log
--
-- details uses VARIANT so different pipeline steps can record different
-- metadata without constantly changing the table definition.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS AUDIT.RUN_LOG
(
    run_id            VARCHAR(36)
        NOT NULL
        DEFAULT UUID_STRING(),

    step              VARCHAR(50)   NOT NULL,

    rows_affected     NUMBER(18, 0),

    details           VARIANT,

    logged_at         TIMESTAMP_LTZ
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Operational history for SkyPoints pipeline steps';