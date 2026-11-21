# Problem analysis

Analysis of the SkyPoints brief and sample data, written before any code.
Every design decision in this repo traces back to a finding or assumption below.

## 1. What is being asked

- **Feed 1 (members):** a daily pipe-delimited flat file of member profiles.
  It has one header record (`|H|...`) followed by detail records (`|D|...`).
  The design document defines the layout: 11 fields with length, data type and mandatory flag.
- **Feed 2 (redemptions):** a daily semi-structured JSON feed from a partner airline.
  Each member object has a `member_id`, a `feed_date` and a nested `redemptions[]` array of transactions.
- **Volume:** billions of records per day, so the design must load incrementally and in parallel.
- **Deliverables:**
  1. DDL for the raw/landing, staging and country-specific target tables
  2. Staging load with derived columns **Age** and **Stale_Member** (more than 90 days since last flight)
  3. Split members into one table per country, where the **latest record wins** if a member moved country
  4. Flatten the JSON redemptions and explain how to join them to member profiles
  5. Data validations
  6. A live demo of the solution

## 2. Open questions in the brief and my assumptions

| Question | My assumption | Why |
|---|---|---|
| What does "latest record" mean with no timestamp column? | Order by the file's business date (from the file name), then extract time, then line number in the file | A member can move country without flying, so flight or enrollment dates are business facts, not change timestamps. A late-arriving old file must never overwrite newer data. |
| The brief says a file-naming spec exists but doesn't give it | `SKYPOINTS_<FEED>_<YYYYMMDD>_<HHMMSS>.<ext>` | The date in the name gives each file an "as-of" date for re-runs and ordering |
| Age and Stale_Member: as of which date? | As of the feed's business date, not today | Re-running an old file gives the same result (deterministic). A separate view can give "as of today". |
| Is a member who never flew stale? | Judge them on enrollment date: stale if enrolled more than 90 days ago | Otherwise a member who joined years ago and never flew would never be flagged |
| Is exactly 90 days stale? | No, the rule is **more than** 90 days | Matches the wording "greater than 90 days" |
| What date format is DOB? | `MMDDYYYY` (e.g. `03051985`); the other dates are `YYYYMMDD` | Matches the sample values |
| Which key identifies a member? | `Member ID`, not `Member Name` | Names are not unique (see finding 9) |
| Which country codes are valid? | Normalise to ISO 3166-1 alpha-3 (`AU` to `AUS`, `PHIL` to `PHL`) and keep the original value | One country must map to exactly one table |
| What happens to a record that fails validation? | ERROR: quarantined, never reaches a country table. WARNING: loaded and reported. | Bad data must not silently disappear, and must not pollute targets |
| Can a redemption's status change between feeds? | Yes (e.g. PENDING to COMPLETED); the latest feed's version of a `txn_id` wins | Partner feeds usually re-send transactions as they settle |
| How do the AUS/USA/IND extracts relate to the main feed? | They are separate source systems with source-local IDs | Their IDs restart at 1 in every file (see finding 13) |

## 3. Data-quality observations

| # | Where | What I found | Why it matters |
|---|---|---|---|
| 1 | Member file header | The header has 10 columns; the layout has 11. `Post_Code` is missing. | Reading columns by position would silently shift `DOB` into `Post_Code`. Columns must be mapped by header name. |
| 2 | Member IDs in sample file | `22345` and `2256` sit next to 6-digit IDs (`223457`, `223458`, ...) | Looks like truncation upstream. Truncated IDs would also break the join to redemptions. |
| 3 | Country values | Mixed formats: `USA`, `IND`, `CAN` (alpha-3), `AU` (alpha-2), `PHIL` (free text) | Without normalisation, the same country could land in two tables or none |
| 4 | Date formats | DOB is `MMDDYYYY`, other dates are `YYYYMMDD` | Parsing every date with one format would give wrong or invalid dates |
| 5 | Intermediate table: DOB | `03051985` became `3051985`: the leading zero was lost | DOB was typed as a number too early. Raw data must be stored as text. |
| 6 | Intermediate table: Agent_Name | Blank for 4 of 5 rows, although the source has `Sam` | A mapping or load bug lost data. Row and column counts must be reconciled after every load. |
| 7 | Intermediate table: State | Values have leading spaces (e.g. ` TN`) | No trimming. Comparisons and joins on State would fail. |
| 8 | Intermediate table: column name | `County` instead of `Country` | Typo in the DDL. Column names should come from the layout, not be typed by hand. |
| 9 | Layout "Key Column" | `Member Name` is marked as the key | Names are not unique (e.g. `Mike` appears in both the AUS and USA extracts with different IDs). `Member ID` is the real key. |
| 10 | Sample last flight dates | All sample members last flew on 2012-10-13 | Every member will be stale. Expected, and it proves the flag works. |
| 11 | AUS.xlsx, row 1 (Mike) | Date of Birth is the text `NULL`, not an empty cell | The text must be treated as a real NULL, not loaded as a value |
| 12 | AUS.xlsx, row 2 (Jonnathan) | Date of Enrollment is `2021-13-13`: month 13 does not exist | Enrollment is mandatory, so this record must be rejected |
| 13 | AUS/USA/IND extracts | IDs `1, 2, 3` appear in all three files | IDs are local to each source, not global. They can't be merged with the main feed without a cross-reference. |
| 14 | USA.xlsx dates | Stored as integers in `MMDDYYYY` order; January lost its leading zero (`1052022`) | `1052022` is ambiguous: 5 Jan or 5 Oct? `1152022`: 15 Jan or 5 Nov? These must be flagged, not guessed silently. |
| 15 | Different schema per extract | Column names and date formats differ in each file; IND has an extra `Individual or Corporate` column | Each source needs its own mapping onto the common layout, then the same rules apply |
| 16 | IND.xlsx, row 3 (Sameer) | DOB 1952 (age about 74) | Valid but worth a plausibility check (e.g. flag ages above 120) |

## 4. Questions I would ask the data owner

1. Should the key column be `Member ID` rather than `Member Name`?
2. Are 4- and 5-digit member IDs valid, or are they truncated upstream?
3. Can the source send ISO alpha-3 country codes, and always include `Post_Code` in the header?
4. What is the official file-naming specification, and can each record carry a `last_updated` timestamp?
5. Can the USA extract send zero-padded dates (`01052022`) to remove the ambiguity?
6. How do the AUS/USA/IND extract IDs map to the global member ID?
7. Which redemption statuses exist, and can a transaction change status after it is first sent?
8. What should happen to a record with a valid ID but an unknown country? Quarantine, or a default table?
