# SkyPoints Loyalty Data Pipeline

A data-engineering solution for the Incubyte Data Craftsperson assessment.

The project processes daily SkyPoints loyalty-member and partner-redemption feeds using a layered Snowflake architecture, with a Python reference implementation for executable specifications, automated tests, and local reconciliation.

The implementation focuses on correctness, data quality, idempotency, lineage, and reproducibility rather than only producing the final target tables.

## What the pipeline does

### Member feed

The member pipeline:

1. receives pipe-delimited daily member files;
2. preserves source records losslessly in RAW;
3. uses the source header to map fields safely;
4. normalises country codes;
5. parses and validates dates;
6. derives `Age` and `Stale_Member`;
7. records ERROR and WARNING data-quality findings;
8. applies deterministic latest-record-wins logic;
9. maintains one current member record;
10. detects country moves; and
11. publishes current members into country-specific tables.

### Redemption feed

The redemption pipeline:

1. lands partner JSON as Snowflake `VARIANT`;
2. flattens nested `redemptions[]` arrays;
3. creates one relational row per transaction;
4. validates transaction-level data quality;
5. identifies orphan member redemptions;
6. applies latest-state-wins per `txn_id`; and
7. publishes the current transaction state.

## Architecture

```text
                         Inbound files
                              |
                 +------------+------------+
                 |                         |
          Member flat file          Redemption JSON
                 |                         |
                 +------------+------------+
                              |
                              v
                  Snowflake named stage
                              |
                              v
                       +-------------+
                       |     RAW     |
                       +-------------+
                       | member lines|
                       | JSON VARIANT|
                       +-------------+
                              |
                              v
                      +--------------+
                      |   STAGING    |
                      +--------------+
                      | parse / type |
                      | derive       |
                      | validate     |
                      +--------------+
                         |         |
                    errors       valid
                         |         |
                         v         v
                      AUDIT      CORE
                                  |
                         +--------+---------+
                         |                  |
                  MEMBER_CURRENT      REDEMPTION_TXN
                         |
             +-----------+-----------+
             |           |           |
            USA         INDIA       ...
```

The schemas are separated by responsibility:

- `RAW` - lossless inbound records and Snowflake Streams.
- `STAGING` - parsed, typed, derived, and validated records.
- `CORE` - trusted current member and redemption state.
- `AUDIT` - data-quality findings, country moves, and operational history.
- `CONFIG` - country aliases, routing configuration, and tier reference data.

## Key design decisions

### Header-driven member parsing

The first supplied member file does not contain `Post_Code` in its header, while the later file does.

A fixed positional parser could therefore interpret:

```text
03051985
```

as `Post_Code` instead of DOB.

The implementation inspects each file header before mapping fields. The same approach is implemented in both Python and Snowflake.

### Deterministic Age

Age is calculated as of the file's business date rather than `CURRENT_DATE`.

This makes historical processing reproducible:

```text
same input + same business date = same Age
```

`CORE.V_MEMBER_CURRENT_LIVE` provides a separate current-date reporting interpretation.

### Stale member

A member is stale when more than 90 days have elapsed since the last flight.

For a member with no flight, enrollment date is used as the fallback reference date.

Exactly 90 days is not considered stale.

### Latest record wins

Member recency is ordered by:

```text
business_date
    ↓
extract_ts
    ↓
file_row_number
```

Snowflake implements this using:

```sql
ROW_NUMBER() OVER (...)
QUALIFY ... = 1
```

This avoids treating enrollment date or flight date as change timestamps.

### Country movement

`CORE.MEMBER_CURRENT` is the single source of truth.

If a member changes country, the latest member state replaces the older state, serving tables are republished from current state, and the movement is recorded in:

```text
AUDIT.MEMBER_COUNTRY_MOVES
```

The supplied sample demonstrates member `223458` moving:

```text
IND -> USA
```

### Data-quality severity

Two severities are used:

```text
ERROR   -> record does not reach CORE
WARNING -> issue is recorded but processing may continue
```

Examples include:

```text
FIELD_COUNT_MISMATCH
MANDATORY_FIELD_MISSING
INVALID_DATE
UNKNOWN_COUNTRY
INVALID_TIER_CODE
INVALID_ACTIVE_FLAG
MEMBER_ID_LENGTH_ANOMALY
DUPLICATE_MEMBER_ID
ORPHAN_REDEMPTION
INVALID_MILES
```

### Redemption validation grain

A single parent JSON object can contain multiple transactions.

Data-quality findings therefore include `txn_id`. This prevents one invalid transaction from rejecting valid sibling transactions within the same JSON object.

For example:

```text
RX20001 -> 3000 miles -> valid
RX20002 ->  -50 miles -> rejected
```

## Repository structure

```text
.
├── .github/workflows/
│   └── ci.yml
├── data/
│   ├── input/
│   └── output/
├── docs/
│   └── analysis.md
├── sql/
│   ├── 00_setup.sql
│   ├── 01_file_formats.sql
│   ├── 02_stage.sql
│   ├── 03_raw.sql
│   ├── 04_staging_and_audit.sql
│   ├── 05_core.sql
│   ├── 06_load_raw.sql
│   ├── 07_stage_members.sql
│   ├── 08_validate_members.sql
│   ├── 09_publish_members.sql
│   ├── 10_process_redemptions.sql
│   ├── 11_assertions.sql
│   └── 12_orchestration.sql
├── src/skypoints/
├── tests/
├── Makefile
├── pyproject.toml
└── README.md
```

## Python setup

Python 3.11 or newer is supported. Development was performed on Python 3.14.

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the project and development dependencies:

```bash
make install
```

## Run the Python reference pipeline

```bash
make run
```

The pipeline writes its outputs under:

```text
data/output/
```

and produces a reconciliation report at:

```text
data/output/dq/run_report.md
```

The reference batch reconciles all 12 member detail records into loaded, rejected, superseded, or ignored outcomes.

A successful run reports:

```text
Reconciled: YES
```

## Profile the country extracts

The supplied AUS, USA, and IND extracts use different source schemas and date representations.

Run:

```bash
make profile
```

The adapters normalise each source onto the canonical member layout before applying shared data-quality rules.

Profiling also identifies that member IDs `1`, `2`, and `3` repeat across the country extracts, so those IDs are treated as source-local rather than assumed to be globally unique.

## Run tests and quality checks

```bash
pytest
ruff check .
ruff format --check .
```

Current reference result:

```text
82 tests passed
```

## Snowflake deployment

Snowflake Data Definition Language (DDL) is version controlled under `sql/`.

A configured Snowflake CLI connection named `skypoints` is required.

Deploy the Snowflake environment with:

```bash
make snowflake-deploy
```

This creates or configures:

```text
SKYPOINTS database
SKYPOINTS_ETL_WH warehouse
RAW / STAGING / CORE / AUDIT / CONFIG schemas
file formats
internal stage
landing tables
staging tables
core tables
audit tables
Streams
reference configuration
```

The deployment scripts use `IF NOT EXISTS` and `MERGE` where appropriate so the environment can be deployed repeatedly without duplicating reference configuration.

## Upload the assessment files

The reproducible demo uses a Snowflake internal stage.

Member files:

```bash
snow stage copy \
  "data/input/SKYPOINTS_MEMBERS_*.txt" \
  "@SKYPOINTS.RAW.STG_SKYPOINTS_INBOUND/members/" \
  -c skypoints \
  --overwrite
```

Redemption files:

```bash
snow stage copy \
  "data/input/SKYPOINTS_REDEMPTIONS_*.json" \
  "@SKYPOINTS.RAW.STG_SKYPOINTS_INBOUND/redemptions/" \
  -c skypoints \
  --overwrite
```

## Run the complete Snowflake pipeline

```bash
make snowflake-run
```

This executes:

```text
COPY INTO RAW
      ↓
member staging
      ↓
member validation
      ↓
latest-record-wins
      ↓
country publishing
      ↓
JSON flattening
      ↓
redemption validation
      ↓
latest transaction state
      ↓
post-run assertions
```

## Snowflake assertions

Run the assertions separately with:

```bash
make snowflake-assert
```

The reference batch currently produces:

```text
13 PASS
0 FAIL
```

Assertions cover:

- member reconciliation;
- current member count;
- uniqueness of current member IDs;
- country-table reconciliation;
- Ravi's current USA state;
- removal of Ravi from India;
- country-move auditing;
- Priya latest-record-wins;
- current redemption count;
- RX10092 latest transaction state;
- invalid redemption exclusion;
- invalid-mile auditing; and
- orphan-redemption auditing.

## Continuous Integration

GitHub Actions runs the Python Continuous Integration (CI) quality gate automatically for pushes and pull requests targeting `main`.

The CI workflow runs:

```text
Ruff lint
Ruff format check
pytest
local end-to-end pipeline
reconciliation verification
```

Live Snowflake execution is intentionally not run from GitHub-hosted CI because it requires account credentials and RSA key-pair authentication.

Snowflake integration is validated separately through Snowflake CLI and executable Snowflake assertions.

## Idempotency

The solution was explicitly tested for reruns.

Examples:

- repeating `COPY INTO` processes zero already-loaded files;
- repeated member publishing does not duplicate `MEMBER_CURRENT`;
- country-movement auditing survives reruns;
- repeated redemption processing does not duplicate transactions;
- data-quality findings are rebuilt rather than duplicated; and
- reference configuration remains stable across deployments.

## Production considerations

The assessment batch is intentionally small, while the brief discusses very large daily volumes.

A production architecture would evolve toward:

```text
Azure Blob Storage
        ↓
External Snowflake Stage
        ↓
Snowpipe / automated ingestion
        ↓
RAW
        ↓
Streams
        ↓
Tasks
        ↓
incremental transformations
        ↓
CORE
```

The repository provisions RAW Streams as the Change Data Capture (CDC) foundation.

The assessment run path remains deterministic and full-batch because this is easier to reproduce with the supplied sample data. A production Snowflake Task should consume the Stream through incremental Data Manipulation Language (DML) operations rather than merely checking whether the Stream contains data.

Other production considerations include:

- least-privilege Snowflake roles rather than day-to-day use of `ACCOUNTADMIN`;
- cloud secret management for authentication keys;
- storage integrations rather than embedded credentials;
- monitoring and alerting for failed loads and data-quality thresholds;
- incremental country-table maintenance at very large scale; and
- explicit service-level objectives for file arrival and processing latency.

## Security

Credentials are not stored in the repository.

The Snowflake demo uses RSA key-pair authentication configured outside the project directory.

The private RSA key and Snowflake CLI configuration must never be committed.

## Further documentation

See:

- `docs/analysis.md` for source-data findings and assumptions.
- `docs/architecture.md` for architecture and data flow.
- `docs/decisions.md` for important engineering trade-offs.
- `docs/assessment-coverage.md` for requirement-to-evidence mapping.
- `docs/ai-usage.md` for AI-assisted development disclosure.
