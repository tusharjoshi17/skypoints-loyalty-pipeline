# Engineering decisions

## 1. Member ID rather than Member Name as operational key

The supplied specification marks Member Name as a key.

The samples demonstrate that names are not unique, so `member_id` is used as the operational member key.

A `SPEC_KEY_NOT_UNIQUE` warning records evidence where the documented key assumption fails.

## 2. Preserve RAW data before typing

Source values remain unchanged in RAW.

This avoids destructive transformations such as converting:

```text
03051985
```

into:

```text
3051985
```

before DOB has been interpreted.

Typed values are produced in STAGING while relevant raw values remain available for DQ reporting.

## 3. Header-driven member mapping

The supplied member files do not have identical headers.

The first feed is missing `Post_Code`.

Using fixed positions could shift DOB into Post_Code, so parsing is driven by the file header.

## 4. Business date for deterministic derivations

Age and Stale_Member are calculated using the feed business date.

This makes historical processing reproducible.

A separate Snowflake view supplies current-date Age and Stale_Member values for reporting.

## 5. Latest-record-wins ordering

Recency is determined by:

1. business date;
2. extract timestamp; and
3. source row number.

Enrollment and flight dates are business attributes and are therefore not used as change timestamps.

## 6. ERROR versus WARNING

ERROR means the record is excluded from trusted CORE data.

WARNING records an anomaly while allowing processing to continue.

This prevents known bad records from polluting targets while preserving visibility into suspicious but potentially valid values.

## 7. Configuration instead of hard-coded country routing

Country aliases and routing targets live in CONFIG tables.

This separates reference data from transformation logic and makes new mappings easier to introduce.

## 8. MEMBER_CURRENT as single source of truth

Country-specific serving tables are derived from `MEMBER_CURRENT`.

This prevents a member that changes country from remaining active in both the previous and new country tables.

## 9. Transaction-grain redemption DQ

One JSON member object can contain several redemption transactions.

DQ findings therefore include `txn_id`.

Otherwise one invalid transaction could incorrectly reject valid siblings in the same parent JSON record.

## 10. Internal stage for the assessment demo

The production design targets cloud object storage and an external Snowflake stage.

The assessment uses a Snowflake internal named stage so the solution is reproducible without requiring separate Azure credentials.

## 11. Python plus Snowflake

Python is retained as a reference implementation, local executable specification, and test harness.

Snowflake provides the production-oriented warehouse implementation.

This separation enables fast tests while still demonstrating Snowflake-native loading, `VARIANT`, `LATERAL FLATTEN`, `MERGE`, window functions, Streams, and layered schemas.

## 12. Deterministic demo instead of fake incremental orchestration

RAW Streams are provisioned, but the assessment transformation scripts intentionally read the complete tiny reference batch.

The project does not claim that these scripts consume Streams.

A production implementation would refactor the transformations into incremental DML executed by Snowflake Tasks guarded by `SYSTEM$STREAM_HAS_DATA`.

## 13. Snowflake credentials excluded from GitHub CI

GitHub Actions validates Python linting, formatting, tests, end-to-end processing, and reconciliation.

The live Snowflake trial is not called from GitHub-hosted runners because doing so would require storing Snowflake authentication material as CI secrets solely for the assessment.

Snowflake integration is instead validated through Snowflake CLI using RSA key-pair authentication outside the repository.
