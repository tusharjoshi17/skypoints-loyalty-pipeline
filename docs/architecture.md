# Architecture

## Overview

SkyPoints uses a layered data architecture that separates ingestion, transformation, trusted business state, audit information, and configuration.

```text
Inbound data
    |
    +-- Member flat files
    |
    +-- Partner redemption JSON
    |
    v
Snowflake Stage
    |
    v
RAW
    |
    +-- MEMBER_LANDING
    +-- REDEMPTION_LANDING
    |
    v
STAGING
    |
    +-- MEMBER_STG
    +-- REDEMPTION_TXN_STG
    |
    +--------------------+
    |                    |
    v                    v
AUDIT                  CORE
                         |
                 +-------+-------+
                 |               |
          MEMBER_CURRENT   REDEMPTION_TXN
                 |
       +---------+---------+---------+---------+---------+
       |         |         |         |         |
      USA      INDIA      PHL       CAN       AUS
```

## RAW

RAW preserves what arrived from the source.

Member files are stored one physical line per row so malformed or structurally different records remain inspectable.

Redemption JSON is stored as Snowflake `VARIANT`.

Source lineage includes:

- source file;
- physical row number;
- file modification timestamp; and
- load timestamp.

No business record is silently corrected in RAW.

## STAGING

STAGING converts source representations into typed business columns.

Member processing includes:

- header-aware field mapping;
- date parsing;
- country normalisation;
- Age calculation;
- days since last flight;
- Stale_Member derivation; and
- record-level DQ status.

Redemption processing uses `LATERAL FLATTEN` to convert nested JSON transactions into relational rows.

## CORE

`CORE.MEMBER_CURRENT` is the single source of truth for the latest accepted state of each member.

Latest-record-wins ordering is:

```text
business_date DESC
extract_ts DESC
file_row_number DESC
```

Country-specific tables are published from `MEMBER_CURRENT`.

This prevents the same current member from remaining in multiple country tables after a country move.

`CORE.REDEMPTION_TXN` stores the latest valid state of each redemption `txn_id`.

## AUDIT

The AUDIT schema contains information required to explain pipeline behaviour.

`DQ_ISSUES` records rule, severity, source lineage, member ID, transaction ID where applicable, affected column, and message.

`MEMBER_COUNTRY_MOVES` records accepted member movement between countries.

`RUN_LOG` provides the foundation for operational execution history.

## CONFIG

Configuration is separated from transformation logic.

`COUNTRY_ALIAS` normalises source representations such as:

```text
AU   -> AUS
PHIL -> PHL
US   -> USA
```

`COUNTRY_ROUTING` maps canonical country codes to serving tables.

`TIER` defines recognised loyalty tiers.

## Python reference implementation

The Python implementation acts as an executable specification and local test harness.

It allows transformation and DQ behaviour to be validated quickly without requiring a live Snowflake account for every test.

Snowflake implements the production-oriented relational design using the same business rules.

## Deployment

Snowflake objects are defined in version-controlled SQL.

```text
Git repository
      |
      v
Snowflake CLI
      |
      v
Snowflake account
```

`make snowflake-deploy` creates the environment.

`make snowflake-run` executes the reference Snowflake pipeline.

## Production evolution

The reproducible assessment uses a Snowflake internal stage.

The production target would use:

```text
Azure Blob Storage
        |
        v
External Snowflake Stage
        |
        v
Snowpipe
        |
        v
RAW
        |
        v
Streams
        |
        v
Tasks
        |
        v
incremental STAGING / CORE processing
```

RAW Streams are included as the Change Data Capture foundation.

The provided transformation scripts intentionally remain deterministic full-batch operations for the small supplied assessment dataset. A production Task implementation should consume Streams through incremental DML so Stream offsets advance correctly.
