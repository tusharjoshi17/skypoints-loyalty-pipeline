-- =============================================================================
-- 05_core.sql
--
-- CORE is the trusted serving layer.
--
-- MEMBER_CURRENT is the single source of truth for the latest known state of
-- every member.
--
-- Country-specific tables are published from MEMBER_CURRENT.
-- =============================================================================

USE DATABASE SKYPOINTS;
USE WAREHOUSE SKYPOINTS_ETL_WH;
USE SCHEMA CORE;


-- =============================================================================
-- MEMBER_CURRENT
-- =============================================================================

CREATE TABLE IF NOT EXISTS CORE.MEMBER_CURRENT
(
    member_id               VARCHAR(18)   NOT NULL,

    member_name             VARCHAR(255)  NOT NULL,

    enrollment_date         DATE          NOT NULL,

    last_flight_date        DATE,

    tier_code               VARCHAR(5),

    agent_name              VARCHAR(255),

    state                   VARCHAR(5),

    country_code            CHAR(3)       NOT NULL,

    post_code               NUMBER(5, 0),

    dob                     DATE,

    is_active               CHAR(1),

    age                     NUMBER(3, 0),

    days_since_last_flight  NUMBER(9, 0),

    is_stale_member         BOOLEAN,


    -- -------------------------------------------------------------------------
    -- Recency / lineage
    --
    -- Used for "latest record wins".
    -- -------------------------------------------------------------------------

    business_date           DATE          NOT NULL,

    extract_ts              TIMESTAMP_NTZ NOT NULL,

    source_file             VARCHAR(500)  NOT NULL,

    file_row_number         NUMBER(18, 0) NOT NULL,


    created_at              TIMESTAMP_LTZ
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP(),

    updated_at              TIMESTAMP_LTZ
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP(),


    CONSTRAINT PK_MEMBER_CURRENT
        PRIMARY KEY (member_id)
)
COMMENT = 'Latest trusted state of each SkyPoints member';


-- =============================================================================
-- COUNTRY TABLES
--
-- Requirement from the assessment:
-- members are split into separate tables based on country.
--
-- All tables intentionally have the same structure.
-- =============================================================================


CREATE TABLE IF NOT EXISTS CORE.TABLE_USA
(
    member_id               VARCHAR(18)   NOT NULL,

    member_name             VARCHAR(255)  NOT NULL,

    enrollment_date         DATE          NOT NULL,

    last_flight_date        DATE,

    tier_code               VARCHAR(5),

    agent_name              VARCHAR(255),

    state                   VARCHAR(5),

    country_code            CHAR(3)       NOT NULL,

    post_code               NUMBER(5, 0),

    dob                     DATE,

    is_active               CHAR(1),

    age                     NUMBER(3, 0),

    days_since_last_flight  NUMBER(9, 0),

    is_stale_member         BOOLEAN,

    business_date           DATE          NOT NULL,

    source_file             VARCHAR(500)  NOT NULL,

    published_at            TIMESTAMP_LTZ
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP(),


    CONSTRAINT PK_TABLE_USA
        PRIMARY KEY (member_id)
);


-- -----------------------------------------------------------------------------
-- CREATE TABLE ... LIKE copies the table structure.
--
-- This avoids manually duplicating the same DDL four more times.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS CORE.TABLE_INDIA
    LIKE CORE.TABLE_USA;


CREATE TABLE IF NOT EXISTS CORE.TABLE_PHILIPPINES
    LIKE CORE.TABLE_USA;


CREATE TABLE IF NOT EXISTS CORE.TABLE_CANADA
    LIKE CORE.TABLE_USA;


CREATE TABLE IF NOT EXISTS CORE.TABLE_AUSTRALIA
    LIKE CORE.TABLE_USA;


-- =============================================================================
-- REDEMPTION TRANSACTIONS
--
-- Latest known state of each transaction.
--
-- A transaction may be sent again:
--
--     Day 1: RX10092 -> PENDING
--     Day 2: RX10092 -> COMPLETED
--
-- The later feed replaces the earlier state.
-- =============================================================================

CREATE TABLE IF NOT EXISTS CORE.REDEMPTION_TXN
(
    txn_id            VARCHAR(50)   NOT NULL,

    member_id         VARCHAR(18)   NOT NULL,

    txn_date          DATE          NOT NULL,

    partner           VARCHAR(255),

    miles_redeemed    NUMBER(18, 0) NOT NULL,

    status            VARCHAR(20)   NOT NULL,

    feed_date         DATE          NOT NULL,

    source_file       VARCHAR(500)  NOT NULL,

    updated_at        TIMESTAMP_LTZ
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP(),


    CONSTRAINT PK_REDEMPTION_TXN
        PRIMARY KEY (txn_id)
)
COMMENT = 'Latest known state of each partner redemption transaction';

-- =============================================================================
-- Live reporting view
--
-- Stored Age and Stale_Member are derived AS OF the feed's business date.
--
-- That is deliberate:
--
--     replay old file -> same result
--
-- But reporting users may also want:
--
--     age / stale status AS OF today
--
-- This view provides that without rewriting historical stored values.
-- =============================================================================

CREATE OR REPLACE VIEW CORE.V_MEMBER_CURRENT_LIVE AS

SELECT
    * EXCLUDE
    (
        age,
        days_since_last_flight,
        is_stale_member
    ),

    YEAR(CURRENT_DATE())
        - YEAR(dob)
        - IFF(
            MONTH(CURRENT_DATE()) * 100 + DAY(CURRENT_DATE())
                < MONTH(dob) * 100 + DAY(dob),
            1,
            0
        ) AS age,

    DATEDIFF(
        day,
        last_flight_date,
        CURRENT_DATE()
    ) AS days_since_last_flight,

    DATEDIFF(
        day,
        COALESCE(last_flight_date, enrollment_date),
        CURRENT_DATE()
    ) > 90 AS is_stale_member

FROM CORE.MEMBER_CURRENT;