# AI-assisted development

AI assistance was used during this assessment as a development aid.

## How AI was used

AI was used for:

- discussing architecture and implementation options;
- explaining Python, SQL, Snowflake, Git, pytest, Ruff, and Snowflake CLI concepts;
- suggesting implementation approaches and test cases;
- reviewing terminal output and error messages;
- identifying possible edge cases;
- helping draft SQL, documentation, and Git commit / pull-request wording; and
- troubleshooting issues found during actual execution.

## Validation approach

AI-generated suggestions were not treated as proof that an implementation worked.

Changes were validated through executable evidence, including:

```text
pytest
Ruff
Python end-to-end reconciliation
Snowflake CLI execution
repeat-run / idempotency checks
Snowflake post-run assertions
GitHub Actions CI
```

Several issues were discovered only after executing suggested implementations against the real data, including:

- additional date formats in the country extracts;
- a missing SQL statement terminator;
- redemption mileage conversion from Snowflake VARIANT;
- transaction-grain DQ needed for sibling JSON transactions; and
- a country-movement audit rerun issue.

Those findings were corrected in the implementation and retested.

## Ownership

The final repository reflects decisions that were executed, reviewed, and validated against the supplied assessment data.

AI assistance does not replace understanding of the implementation. The code, SQL, assumptions, trade-offs, and validation approach are documented so they can be explained and reproduced independently.
