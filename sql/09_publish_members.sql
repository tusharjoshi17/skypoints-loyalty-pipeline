-- =============================================================================
-- 09_publish_members.sql
--
-- Publishes validated member records from STAGING into CORE.
--
-- Rules:
--
-- 1. ERROR records never reach CORE.
-- 2. If the same member occurs multiple times, the latest record wins.
-- 3. Recency order:
--      business_date
--      extract_ts
--      file_row_number
-- 4. Country changes are written to AUDIT.MEMBER_COUNTRY_MOVES.
-- 5. MEMBER_CURRENT is the single source of truth.
-- 6. Country tables are published from MEMBER_CURRENT.
-- =============================================================================

USE DATABASE SKYPOINTS;
USE WAREHOUSE SKYPOINTS_ETL_WH;


-- =============================================================================
-- COUNTRY MOVE AUDIT
--
-- Detect a change between consecutive valid versions of the same member.
--
-- Example:
--
--     2024-01-15  223458  IND
--     2024-01-16  223458  USA
--
-- produces:
--
--     223458 | IND | USA | 2024-01-16
-- =============================================================================

DELETE FROM AUDIT.MEMBER_COUNTRY_MOVES
WHERE source_file IN
(
    SELECT DISTINCT source_file
    FROM STAGING.MEMBER_STG
);


INSERT INTO AUDIT.MEMBER_COUNTRY_MOVES
(
    member_id,
    from_country,
    to_country,
    business_date,
    source_file
)

WITH history AS
(
    SELECT
        member_id,
        country_code,
        business_date,
        extract_ts,
        file_row_number,
        source_file,

        LAG(country_code) OVER
        (
            PARTITION BY member_id

            ORDER BY
                business_date,
                extract_ts,
                file_row_number
        ) AS previous_country

    FROM STAGING.MEMBER_STG

    WHERE dq_status IN ('VALID', 'PUBLISHED', 'SUPERSEDED')
      AND member_id IS NOT NULL
      AND country_code IS NOT NULL
)

SELECT
    member_id,
    previous_country,
    country_code,
    business_date,
    source_file

FROM history

WHERE previous_country IS NOT NULL
  AND previous_country <> country_code;


-- =============================================================================
-- LATEST RECORD WINS
--
-- ROW_NUMBER assigns:
--
--     1 = newest record
--     2 = previous version
--     3 = older version
--
-- QUALIFY filters after the window function is calculated.
-- =============================================================================

MERGE INTO CORE.MEMBER_CURRENT AS target

USING
(
    SELECT
        member_id,
        member_name,
        enrollment_date,
        last_flight_date,
        tier_code,
        agent_name,
        state,
        country_code,
        post_code,
        dob,
        is_active,
        age,
        days_since_last_flight,
        is_stale_member,
        business_date,
        extract_ts,
        source_file,
        file_row_number

    FROM STAGING.MEMBER_STG

    WHERE dq_status IN ('VALID', 'PUBLISHED', 'SUPERSEDED')
      AND member_id IS NOT NULL


    QUALIFY ROW_NUMBER() OVER
    (
        PARTITION BY member_id

        ORDER BY
            business_date DESC,
            extract_ts DESC,
            file_row_number DESC
    ) = 1
) AS source

ON target.member_id = source.member_id


-- -----------------------------------------------------------------------------
-- Existing member: update only when the incoming version is newer.
-- -----------------------------------------------------------------------------

WHEN MATCHED
AND
(
       source.business_date > target.business_date

    OR (
        source.business_date = target.business_date
        AND source.extract_ts > target.extract_ts
    )

    OR (
        source.business_date = target.business_date
        AND source.extract_ts = target.extract_ts
        AND source.file_row_number > target.file_row_number
    )
)

THEN UPDATE SET

    target.member_name =
        source.member_name,

    target.enrollment_date =
        source.enrollment_date,

    target.last_flight_date =
        source.last_flight_date,

    target.tier_code =
        source.tier_code,

    target.agent_name =
        source.agent_name,

    target.state =
        source.state,

    target.country_code =
        source.country_code,

    target.post_code =
        source.post_code,

    target.dob =
        source.dob,

    target.is_active =
        source.is_active,

    target.age =
        source.age,

    target.days_since_last_flight =
        source.days_since_last_flight,

    target.is_stale_member =
        source.is_stale_member,

    target.business_date =
        source.business_date,

    target.extract_ts =
        source.extract_ts,

    target.source_file =
        source.source_file,

    target.file_row_number =
        source.file_row_number,

    target.updated_at =
        CURRENT_TIMESTAMP()


-- -----------------------------------------------------------------------------
-- New member
-- -----------------------------------------------------------------------------

WHEN NOT MATCHED THEN INSERT
(
    member_id,
    member_name,
    enrollment_date,
    last_flight_date,
    tier_code,
    agent_name,
    state,
    country_code,
    post_code,
    dob,
    is_active,
    age,
    days_since_last_flight,
    is_stale_member,
    business_date,
    extract_ts,
    source_file,
    file_row_number
)

VALUES
(
    source.member_id,
    source.member_name,
    source.enrollment_date,
    source.last_flight_date,
    source.tier_code,
    source.agent_name,
    source.state,
    source.country_code,
    source.post_code,
    source.dob,
    source.is_active,
    source.age,
    source.days_since_last_flight,
    source.is_stale_member,
    source.business_date,
    source.extract_ts,
    source.source_file,
    source.file_row_number
);


-- =============================================================================
-- STAGING LIFECYCLE
--
-- Mark older duplicate versions as SUPERSEDED.
-- Keep rejected records as REJECTED.
-- Latest valid versions become PUBLISHED.
-- =============================================================================

UPDATE STAGING.MEMBER_STG AS member

SET
    dq_status = 'SUPERSEDED',
    status_updated_at = CURRENT_TIMESTAMP()

FROM
(
    SELECT
        source_file,
        file_row_number,

        ROW_NUMBER() OVER
        (
            PARTITION BY member_id

            ORDER BY
                business_date DESC,
                extract_ts DESC,
                file_row_number DESC
        ) AS recency_rank

    FROM STAGING.MEMBER_STG

    WHERE dq_status IN ('VALID', 'PUBLISHED', 'SUPERSEDED')
      AND member_id IS NOT NULL
) AS ranked

WHERE member.source_file = ranked.source_file
  AND member.file_row_number = ranked.file_row_number
  AND ranked.recency_rank > 1;


UPDATE STAGING.MEMBER_STG

SET
    dq_status = 'PUBLISHED',
    status_updated_at = CURRENT_TIMESTAMP()

WHERE dq_status IN ('VALID', 'PUBLISHED');


-- =============================================================================
-- COUNTRY SERVING TABLES
--
-- MEMBER_CURRENT is the source of truth.
--
-- For the reference implementation the serving tables are rebuilt from current
-- state. This guarantees that a member cannot remain in an old country after
-- moving to another country.
--
-- At much larger scale this can be replaced with incremental MERGE + DELETE.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- USA
-- -----------------------------------------------------------------------------

TRUNCATE TABLE CORE.TABLE_USA;


INSERT INTO CORE.TABLE_USA
(
    member_id,
    member_name,
    enrollment_date,
    last_flight_date,
    tier_code,
    agent_name,
    state,
    country_code,
    post_code,
    dob,
    is_active,
    age,
    days_since_last_flight,
    is_stale_member,
    business_date,
    source_file
)

SELECT
    member_id,
    member_name,
    enrollment_date,
    last_flight_date,
    tier_code,
    agent_name,
    state,
    country_code,
    post_code,
    dob,
    is_active,
    age,
    days_since_last_flight,
    is_stale_member,
    business_date,
    source_file

FROM CORE.MEMBER_CURRENT

WHERE country_code = 'USA';


-- -----------------------------------------------------------------------------
-- INDIA
-- -----------------------------------------------------------------------------

TRUNCATE TABLE CORE.TABLE_INDIA;


INSERT INTO CORE.TABLE_INDIA

SELECT
    member_id,
    member_name,
    enrollment_date,
    last_flight_date,
    tier_code,
    agent_name,
    state,
    country_code,
    post_code,
    dob,
    is_active,
    age,
    days_since_last_flight,
    is_stale_member,
    business_date,
    source_file,
    CURRENT_TIMESTAMP()

FROM CORE.MEMBER_CURRENT

WHERE country_code = 'IND';


-- -----------------------------------------------------------------------------
-- PHILIPPINES
-- -----------------------------------------------------------------------------

TRUNCATE TABLE CORE.TABLE_PHILIPPINES;


INSERT INTO CORE.TABLE_PHILIPPINES

SELECT
    member_id,
    member_name,
    enrollment_date,
    last_flight_date,
    tier_code,
    agent_name,
    state,
    country_code,
    post_code,
    dob,
    is_active,
    age,
    days_since_last_flight,
    is_stale_member,
    business_date,
    source_file,
    CURRENT_TIMESTAMP()

FROM CORE.MEMBER_CURRENT

WHERE country_code = 'PHL';


-- -----------------------------------------------------------------------------
-- CANADA
-- -----------------------------------------------------------------------------

TRUNCATE TABLE CORE.TABLE_CANADA;


INSERT INTO CORE.TABLE_CANADA

SELECT
    member_id,
    member_name,
    enrollment_date,
    last_flight_date,
    tier_code,
    agent_name,
    state,
    country_code,
    post_code,
    dob,
    is_active,
    age,
    days_since_last_flight,
    is_stale_member,
    business_date,
    source_file,
    CURRENT_TIMESTAMP()

FROM CORE.MEMBER_CURRENT

WHERE country_code = 'CAN';


-- -----------------------------------------------------------------------------
-- AUSTRALIA
-- -----------------------------------------------------------------------------

TRUNCATE TABLE CORE.TABLE_AUSTRALIA;


INSERT INTO CORE.TABLE_AUSTRALIA

SELECT
    member_id,
    member_name,
    enrollment_date,
    last_flight_date,
    tier_code,
    agent_name,
    state,
    country_code,
    post_code,
    dob,
    is_active,
    age,
    days_since_last_flight,
    is_stale_member,
    business_date,
    source_file,
    CURRENT_TIMESTAMP()

FROM CORE.MEMBER_CURRENT

WHERE country_code = 'AUS';