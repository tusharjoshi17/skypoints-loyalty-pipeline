# Assessment coverage

This document maps the requested deliverables to implementation evidence.

| Deliverable | Implementation |
|---|---|
| 1. Snowflake DDL | `sql/00_setup.sql` through `sql/05_core.sql` |
| RAW / landing tables | `RAW.MEMBER_LANDING`, `RAW.REDEMPTION_LANDING` |
| Staging tables | `STAGING.MEMBER_STG`, `STAGING.REDEMPTION_TXN_STG` |
| Country-specific tables | `CORE.TABLE_USA`, `TABLE_INDIA`, `TABLE_PHILIPPINES`, `TABLE_CANADA`, `TABLE_AUSTRALIA` |
| 2. Age | Python staging logic and `sql/07_stage_members.sql`; business-date deterministic calculation |
| 2. Stale_Member | Python staging logic and `sql/07_stage_members.sql`; greater than 90 days |
| 3. Country split | `sql/09_publish_members.sql` |
| 3. Latest record wins | `ROW_NUMBER` + `QUALIFY` + `MERGE` in `sql/09_publish_members.sql` |
| Country movement | `AUDIT.MEMBER_COUNTRY_MOVES` |
| 4. JSON flattening | Snowflake `VARIANT` + `LATERAL FLATTEN` in `sql/10_process_redemptions.sql` |
| Redemption/member relationship | `member_id`; orphan activity audited when no current member exists |
| Redemption latest state | `MERGE` by `txn_id` and latest `feed_date` |
| 5. Data validation | Python DQ rules plus `AUDIT.DQ_ISSUES` and `sql/08_validate_members.sql` / `sql/10_process_redemptions.sql` |
| Structural validation | Header/layout checks and `FIELD_COUNT_MISMATCH` |
| Mandatory values | `MANDATORY_FIELD_MISSING` |
| Date validity | `INVALID_DATE` |
| Country validation | normalisation plus `UNKNOWN_COUNTRY` |
| Tier validation | `INVALID_TIER_CODE` |
| Member ID anomalies | `MEMBER_ID_LENGTH_ANOMALY` |
| Duplicate detection | `DUPLICATE_MEMBER_ID` |
| Redemption validation | `INVALID_MILES`, status/date checks, orphan warning |
| 6. Live demo | `make run` for Python and `make snowflake-run` for Snowflake |
| Automated tests | 82 pytest tests |
| Snowflake verification | 13 executable assertions in `sql/11_assertions.sql` |
| CI | `.github/workflows/ci.yml` |
| Source analysis | `docs/analysis.md` |
| Design documentation | `README.md`, `docs/architecture.md`, `docs/decisions.md` |
| AI disclosure | `docs/ai-usage.md` |

## Demonstrated reference results

### Member reconciliation

```text
12 member detail rows
7 current/published members
3 rejected records
2 superseded versions
```

All input detail rows are accounted for.

### Country movement

Member `223458` demonstrates:

```text
IND -> USA
```

The member is removed from the current India serving table and appears in the USA table.

### Latest member version

Member `223460` retains the later same-file version:

```text
tier = GLD
last_flight_date = 2024-01-12
```

### Redemptions

Six transaction versions flatten from the supplied JSON.

The resulting valid current transaction set contains four transactions.

`RX10092` demonstrates:

```text
PENDING -> COMPLETED
```

`RX20002` is excluded because its mileage value is negative.

`RX30001` remains processable but generates an orphan-member warning.

### Automated evidence

Python:

```text
82 tests passed
```

Snowflake:

```text
13 PASS
0 FAIL
```

CI additionally executes the local pipeline and verifies successful reconciliation.
