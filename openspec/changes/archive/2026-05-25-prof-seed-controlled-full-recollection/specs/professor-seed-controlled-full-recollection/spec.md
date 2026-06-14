## ADDED Requirements

### Requirement: P7 candidate selection uses the latest readiness matrix

P7 MUST select controlled full-recollection candidates from the latest
Professor seed readiness matrix. A seed is eligible only when its latest
readiness row has `recommended_next_mode='full'` and
`full_recollection_allowed=true`.

P7 MUST exclude seed 5 while it remains `blocked`, and MUST exclude any other
seed whose latest readiness row is not full-ready.

#### Scenario: Full-ready rows are selected

- **WHEN** the latest readiness matrix contains 19 rows with
  `full_recollection_allowed=true`
- **THEN** P7 selects exactly those rows for full execution
- **AND** the selected seed ids are recorded before execution starts

#### Scenario: Blocked row is excluded

- **WHEN** seed id 5 is `blocked`
- **THEN** P7 does not run seed id 5 in `full` mode
- **AND** the P7 evidence records the exclusion reason

### Requirement: P7 full execution records row-level E2E evidence

P7 MUST execute `full` mode for every selected seed and record a row-level E2E
matrix. Each row MUST include seed id, adapter name, run id, terminal status,
failure class, items processed, items failed, latest issue id or reason, and
whether the row is ready for P8 quality validation.

#### Scenario: Successful full run is recorded

- **WHEN** a selected seed completes `full` mode with `status='success'`
- **THEN** the E2E matrix records the run id, adapter, items processed, items
  failed, and `failure_class='success'`
- **AND** the row is marked ready for P8 quality validation

#### Scenario: Failed full run remains visible

- **WHEN** a selected seed completes `full` mode with a non-success failure
  class
- **THEN** the E2E matrix records the run id, failure class, item counts, and
  issue reference
- **AND** the row is not silently removed from the P8 handoff

### Requirement: P7 completion updates required artifacts

P7 MUST NOT be marked complete until `tasks.md`, `acceptance.md`, and
`.agents/runs/prof-seed-controlled-full-recollection/verification.md` contain
the candidate list, exact commands, full-run E2E matrix, skipped unsafe
operations, and verification results.

#### Scenario: Artifact evidence is complete

- **WHEN** P7 full execution finishes
- **THEN** the exact command and result are recorded in the run verification
  file
- **AND** `acceptance.md` records the row-level matrix
- **AND** `tasks.md` is updated only after evidence exists

### Requirement: P7 does not perform cleanup or publish refresh

P7 MUST NOT truncate tables, delete canonical data, hard-delete seeds, refresh
online RAG indexes, or publish the resulting data to downstream search
collections.

#### Scenario: Unsafe operations are skipped

- **WHEN** P7 verification is reviewed
- **THEN** cleanup, deletion, publish refresh, and RAG index refresh are listed
  as skipped operations
- **AND** later-stage ownership is recorded

