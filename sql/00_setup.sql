-- =============================================================================
-- 00_setup.sql
-- Creates the top-level Snowflake objects and reusable configuration.
--
-- Object model:
--
--   SKYPOINTS
--     RAW       -> lossless inbound data
--     STAGING   -> typed, cleaned and validated data
--     CORE      -> current member state and country serving tables
--     AUDIT     -> data-quality and operational history
--     CONFIG    -> reference data and routing configuration
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Database and schemas
-- -----------------------------------------------------------------------------

CREATE DATABASE IF NOT EXISTS SKYPOINTS;

USE DATABASE SKYPOINTS;

CREATE SCHEMA IF NOT EXISTS RAW;
CREATE SCHEMA IF NOT EXISTS STAGING;
CREATE SCHEMA IF NOT EXISTS CORE;
CREATE SCHEMA IF NOT EXISTS AUDIT;
CREATE SCHEMA IF NOT EXISTS CONFIG;


-- -----------------------------------------------------------------------------
-- Virtual warehouse
--
-- Storage and compute are separate in Snowflake.
-- This warehouse supplies compute for COPY, transformations and MERGE operations.
--
-- XSMALL keeps the demonstration inexpensive. Production sizing would be based
-- on daily volume, file count and the required load window.
-- -----------------------------------------------------------------------------

CREATE WAREHOUSE IF NOT EXISTS SKYPOINTS_ETL_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Compute warehouse for the SkyPoints data pipeline';


USE WAREHOUSE SKYPOINTS_ETL_WH;


-- -----------------------------------------------------------------------------
-- Country aliases
--
-- Source systems use inconsistent country representations:
--
--     US   -> USA
--     AU   -> AUS
--     PHIL -> PHL
--
-- The pipeline converts all known aliases into ISO-style alpha-3 codes before
-- routing data into country-specific tables.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS CONFIG.COUNTRY_ALIAS
(
    source_code VARCHAR(10) NOT NULL,
    iso3_code   CHAR(3)     NOT NULL,

    CONSTRAINT PK_COUNTRY_ALIAS PRIMARY KEY (source_code)
);


MERGE INTO CONFIG.COUNTRY_ALIAS AS target
USING
(
    SELECT column1 AS source_code,
           column2 AS iso3_code
    FROM VALUES
        ('USA',  'USA'),
        ('US',   'USA'),
        ('IND',  'IND'),
        ('IN',   'IND'),
        ('PHL',  'PHL'),
        ('PH',   'PHL'),
        ('PHIL', 'PHL'),
        ('CAN',  'CAN'),
        ('CA',   'CAN'),
        ('AUS',  'AUS'),
        ('AU',   'AUS')
) AS source
ON target.source_code = source.source_code

WHEN NOT MATCHED THEN
    INSERT
    (
        source_code,
        iso3_code
    )
    VALUES
    (
        source.source_code,
        source.iso3_code
    );


-- -----------------------------------------------------------------------------
-- Country routing
--
-- Routing is configuration rather than hard-coded CASE logic.
-- Adding a country therefore becomes a data/configuration change.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS CONFIG.COUNTRY_ROUTING
(
    iso3_code    CHAR(3)      NOT NULL,
    target_table VARCHAR(100) NOT NULL,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,

    CONSTRAINT PK_COUNTRY_ROUTING PRIMARY KEY (iso3_code),
    CONSTRAINT UQ_COUNTRY_TARGET UNIQUE (target_table)
);


MERGE INTO CONFIG.COUNTRY_ROUTING AS target
USING
(
    SELECT column1 AS iso3_code,
           column2 AS target_table
    FROM VALUES
        ('USA', 'TABLE_USA'),
        ('IND', 'TABLE_INDIA'),
        ('PHL', 'TABLE_PHILIPPINES'),
        ('CAN', 'TABLE_CANADA'),
        ('AUS', 'TABLE_AUSTRALIA')
) AS source
ON target.iso3_code = source.iso3_code

WHEN NOT MATCHED THEN
    INSERT
    (
        iso3_code,
        target_table
    )
    VALUES
    (
        source.iso3_code,
        source.target_table
    );


-- -----------------------------------------------------------------------------
-- Tier reference data
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS CONFIG.TIER
(
    tier_code VARCHAR(5)  NOT NULL,
    tier_name VARCHAR(50) NOT NULL,

    CONSTRAINT PK_TIER PRIMARY KEY (tier_code)
);


MERGE INTO CONFIG.TIER AS target
USING
(
    SELECT column1 AS tier_code,
           column2 AS tier_name
    FROM VALUES
        ('PLT', 'Platinum'),
        ('GLD', 'Gold'),
        ('SLV', 'Silver')
) AS source
ON target.tier_code = source.tier_code

WHEN NOT MATCHED THEN
    INSERT
    (
        tier_code,
        tier_name
    )
    VALUES
    (
        source.tier_code,
        source.tier_name
    );