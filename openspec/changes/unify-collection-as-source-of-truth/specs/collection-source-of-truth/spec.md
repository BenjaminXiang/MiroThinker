## ADDED Requirements

### Requirement: Every pack record is present in the collection database

After the backfill, each professor and paper in the serving pack MUST have a row
in the collection database that carries its fields, and re-running the backfill
MUST NOT create duplicates.

#### Scenario: Backfill rerun

- **WHEN** the professor backfill runs twice
- **THEN** the collection database still holds one row per pack professor

#### Scenario: Sample parity

- **WHEN** 50 pack professors (and papers) are compared against their collection
  rows
- **THEN** at least 98% of the sampled fields match

### Requirement: Divergence is visible

A daily check MUST report, per domain, how many pack records are missing from the
collection database, and the admin status MUST expose it.

#### Scenario: New pack, stale database

- **WHEN** the pack gains records the database lacks
- **THEN** the guard reports a non-zero gap for that domain
