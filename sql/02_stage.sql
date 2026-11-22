-- =============================================================================
-- 02_stage.sql
--
-- Stage used by the SkyPoints inbound feeds.
--
-- Production architecture:
--     Azure Blob Storage -> external Snowflake stage
--
-- Demo architecture:
--     Snowflake internal named stage
--
-- An internal stage lets this project run on a trial account without requiring
-- Azure credentials, while the production Azure design remains documented.
-- =============================================================================

USE DATABASE SKYPOINTS;
USE SCHEMA RAW;


-- -----------------------------------------------------------------------------
-- Demo / trial environment
-- -----------------------------------------------------------------------------

CREATE STAGE IF NOT EXISTS RAW.STG_SKYPOINTS_INBOUND
    COMMENT = 'Inbound member and redemption files for the SkyPoints pipeline';


-- -----------------------------------------------------------------------------
-- Production Azure alternative
--
-- Not executed in the demo because it requires a real Azure Storage Account
-- and Snowflake STORAGE INTEGRATION.
--
-- Example architecture:
--
-- CREATE STORAGE INTEGRATION SKYPOINTS_AZURE_INT
--     TYPE = EXTERNAL_STAGE
--     STORAGE_PROVIDER = 'AZURE'
--     ENABLED = TRUE
--     AZURE_TENANT_ID = '<azure-tenant-id>'
--     STORAGE_ALLOWED_LOCATIONS =
--     (
--         'azure://<storage-account>.blob.core.windows.net/skypoints-inbound/'
--     );
--
--
-- CREATE STAGE RAW.STG_SKYPOINTS_INBOUND_AZURE
--     URL =
--       'azure://<storage-account>.blob.core.windows.net/skypoints-inbound/'
--     STORAGE_INTEGRATION = SKYPOINTS_AZURE_INT;
-- -----------------------------------------------------------------------------