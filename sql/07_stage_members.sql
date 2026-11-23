-- =============================================================================
-- 07_stage_members.sql
--
-- RAW -> STAGING member transformation.
--
-- Important:
--   The source header controls the positional mapping.
--
--   Day-1 source does not contain Post_Code.
--   Day-2 source does contain Post_Code.
--
-- A positional parser that blindly assumes 11 business columns could silently
-- shift DOB into Post_Code. The source header is therefore inspected per file.
-- =============================================================================

USE DATABASE SKYPOINTS;
USE WAREHOUSE SKYPOINTS_ETL_WH;


-- Start clean while validating the reference/demo batch.
TRUNCATE TABLE STAGING.MEMBER_STG;


INSERT INTO STAGING.MEMBER_STG
(
    source_file,
    file_row_number,
    record_type,
    business_date,
    extract_ts,
    field_count,
    expected_field_count,

    member_name,
    member_id,
    enrollment_date,
    last_flight_date,
    tier_code,
    agent_name,
    state,
    country_code,
    post_code,
    dob,
    is_active,

    enrollment_date_raw,
    last_flight_date_raw,
    dob_raw,
    post_code_raw,
    country_raw,

    age,
    days_since_last_flight,
    is_stale_member,

    dq_status,
    status_updated_at
)

WITH file_headers AS
(
    SELECT
        source_file,

        ARRAY_SIZE(SPLIT(raw_line, '|')) - 2
            AS expected_field_count,

        POSITION('|Post_Code|' IN raw_line) > 0
            AS has_post_code

    FROM RAW.MEMBER_LANDING

    WHERE raw_line LIKE '|H|%'
),


detail_rows AS
(
    SELECT
        raw.source_file,
        raw.file_row_number,

        SPLIT(raw.raw_line, '|')
            AS tokens,

        header.expected_field_count,
        header.has_post_code,

        ARRAY_SIZE(SPLIT(raw.raw_line, '|')) - 2
            AS field_count,

        TO_DATE(
            REGEXP_SUBSTR(
                raw.source_file,
                '[0-9]{8}'
            ),
            'YYYYMMDD'
        ) AS business_date,

        TO_TIMESTAMP_NTZ(
            REGEXP_SUBSTR(
                raw.source_file,
                '[0-9]{8}_[0-9]{6}'
            ),
            'YYYYMMDD_HH24MISS'
        ) AS extract_ts

    FROM RAW.MEMBER_LANDING AS raw

    INNER JOIN file_headers AS header
        ON raw.source_file = header.source_file

    WHERE raw.raw_line LIKE '|D|%'
),


parsed AS
(
    SELECT
        source_file,
        file_row_number,

        'D' AS record_type,

        business_date,
        extract_ts,

        field_count,
        expected_field_count,

        NULLIF(TRIM(GET(tokens, 2)::VARCHAR), '')
            AS member_name,

        NULLIF(TRIM(GET(tokens, 3)::VARCHAR), '')
            AS member_id,

        NULLIF(TRIM(GET(tokens, 4)::VARCHAR), '')
            AS enrollment_date_raw,

        NULLIF(TRIM(GET(tokens, 5)::VARCHAR), '')
            AS last_flight_date_raw,

        NULLIF(TRIM(GET(tokens, 6)::VARCHAR), '')
            AS tier_code,

        NULLIF(TRIM(GET(tokens, 7)::VARCHAR), '')
            AS agent_name,

        NULLIF(TRIM(GET(tokens, 8)::VARCHAR), '')
            AS state,

        NULLIF(TRIM(GET(tokens, 9)::VARCHAR), '')
            AS country_raw,

        CASE
            WHEN has_post_code
                THEN NULLIF(TRIM(GET(tokens, 10)::VARCHAR), '')
            ELSE NULL
        END AS post_code_raw,

        CASE
            WHEN has_post_code
                THEN NULLIF(TRIM(GET(tokens, 11)::VARCHAR), '')
            ELSE NULLIF(TRIM(GET(tokens, 10)::VARCHAR), '')
        END AS dob_raw,

        CASE
            WHEN has_post_code
                THEN NULLIF(TRIM(GET(tokens, 12)::VARCHAR), '')
            ELSE NULLIF(TRIM(GET(tokens, 11)::VARCHAR), '')
        END AS is_active_raw

    FROM detail_rows
),


typed AS
(
    SELECT
        parsed.*,

        TRY_TO_DATE(
            enrollment_date_raw,
            'YYYYMMDD'
        ) AS enrollment_date,

        TRY_TO_DATE(
            last_flight_date_raw,
            'YYYYMMDD'
        ) AS last_flight_date,

        TRY_TO_DATE(
            dob_raw,
            'MMDDYYYY'
        ) AS dob,

        TRY_TO_NUMBER(post_code_raw)
            AS post_code,

        alias.iso3_code
            AS country_code

    FROM parsed

    LEFT JOIN CONFIG.COUNTRY_ALIAS AS alias
        ON UPPER(parsed.country_raw) = alias.source_code
),


derived AS
(
    SELECT
        *,

        CASE
            WHEN dob IS NULL
                OR dob > business_date
                THEN NULL

            ELSE
                YEAR(business_date)
                - YEAR(dob)
                - IFF(
                    MONTH(business_date) * 100
                        + DAY(business_date)
                    <
                    MONTH(dob) * 100
                        + DAY(dob),
                    1,
                    0
                )
        END AS age,

        CASE
            WHEN last_flight_date IS NULL
                THEN NULL

            ELSE
                DATEDIFF(
                    day,
                    last_flight_date,
                    business_date
                )
        END AS days_since_last_flight,

        DATEDIFF(
            day,
            COALESCE(
                last_flight_date,
                enrollment_date
            ),
            business_date
        ) > 90 AS is_stale_member

    FROM typed
)


SELECT
    source_file,
    file_row_number,
    record_type,
    business_date,
    extract_ts,
    field_count,
    expected_field_count,

    member_name,
    member_id,
    enrollment_date,
    last_flight_date,
    tier_code,
    agent_name,
    state,
    country_code,
    post_code,
    dob,
    UPPER(is_active_raw),

    enrollment_date_raw,
    last_flight_date_raw,
    dob_raw,
    post_code_raw,
    country_raw,

    age,
    days_since_last_flight,
    is_stale_member,

    CASE

        WHEN field_count <> expected_field_count
            THEN 'REJECTED'

        WHEN member_name IS NULL
            OR member_id IS NULL
            OR enrollment_date IS NULL
            THEN 'REJECTED'

        WHEN country_code IS NULL
            THEN 'REJECTED'

        ELSE 'VALID'

    END AS dq_status,

    CURRENT_TIMESTAMP()

FROM derived;