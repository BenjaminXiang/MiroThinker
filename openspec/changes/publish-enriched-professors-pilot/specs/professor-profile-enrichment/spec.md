## ADDED Requirements

### Requirement: Enriched biographies reach the serving line

A professor biography written by the enrichment pipeline MUST be publishable to
the serving manual-recall store without rebuilding the pack, using deterministic
records so a re-run replaces rather than duplicates.

#### Scenario: Pilot batch published

- **WHEN** 18 enriched professors are published and the service restarts
- **THEN** the store holds 18 additional `manual_record` points and a query for
  one of them answers from the enriched text with citations

#### Scenario: Re-running the publisher

- **WHEN** the publisher runs twice for the same professor
- **THEN** the store still holds one record for that professor

### Requirement: Publishing is reversible

Before writing, the operator MUST have a copy of the store directory; restoring
it (or tombstoning the records) returns the previous behaviour.

#### Scenario: Bad biography published

- **WHEN** an operator tombstones the record by ref `pilot-<professor_id>`
- **THEN** the professor's manual claim disappears from answers
