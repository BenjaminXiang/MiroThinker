## ADDED Requirements

### Requirement: Cleanup dry-run and safety gates

The system MUST provide a cleanup planning step that runs before any
destructive deletion or truncation of verification data.

The cleanup plan MUST include the target database fingerprint, current
Alembic revision, affected table list, affected row counts, and whether
the command is dry-run or destructive. A destructive cleanup MUST require
an explicit non-dry-run flag and MUST NOT be the default mode.

#### Scenario: Cleanup preview before deletion

- **WHEN** an operator runs the cleanup command without the destructive
  flag
- **THEN** no rows are deleted
- **AND** the output lists the target database, Alembic revision,
  affected tables, and affected row counts

#### Scenario: Destructive cleanup requires explicit intent

- **WHEN** an operator runs the cleanup command without confirming the
  intended target database
- **THEN** the command exits without deleting rows
- **AND** the output explains which confirmation is missing

### Requirement: Bounded recollection batch

The system MUST support a bounded recollection batch before a full seed
run. The bounded batch MUST accept an explicit seed list and at least one
limit control so operators can validate the pipeline without triggering
large full-school runs.

#### Scenario: Sample seed batch

- **WHEN** an operator starts a recollection batch with a seed list and
  sample limit
- **THEN** only the requested seeds are processed
- **AND** the report records the limit, processed seed ids, seed status
  transitions, elapsed time, and failure reasons

#### Scenario: Full run blocked without sample evidence

- **WHEN** an operator requests a full recollection run before a bounded
  sample report exists
- **THEN** the runbook blocks the full-run step
- **AND** it points to the missing sample evidence

### Requirement: Recollection evidence report

The system MUST generate a recollection evidence report for every run.
The report MUST include at least seed status summary, pipeline issue
taxonomy, professor quality-status distribution, professor fact coverage,
profile summary coverage, professor-paper link evidence, professor-patent
link evidence, paper summary readiness, Milvus refresh result, and RAG
retrieval sanity checks.

#### Scenario: Evidence report is generated

- **WHEN** a recollection batch finishes
- **THEN** a report is written under the run workspace
- **AND** the report contains the required sections with the command
  output or SQL used to produce each section

#### Scenario: Failures are classified

- **WHEN** a recollection batch produces pipeline issues
- **THEN** the report groups failures by stage and issue type
- **AND** includes representative samples with seed id, source URL, and
  recommended next action

### Requirement: Post-recollection quality gates

The recollection report MUST explicitly distinguish code-path success
from data-readiness success. A run MUST NOT be marked data-ready unless
collection, cleaning, summary generation, Milvus refresh, and retrieval
sanity all have recorded evidence.

#### Scenario: Code path passes but data is not ready

- **WHEN** collectors run without crashing but summaries or Milvus
  refresh are missing
- **THEN** the report marks the code path as passed
- **AND** marks data readiness as incomplete with the missing evidence

#### Scenario: Data readiness pass

- **WHEN** the recollection report has passing evidence for seed status,
  quality distribution, facts, summaries, links, Milvus refresh, and RAG
  sanity
- **THEN** the report marks the recollected batch as data-ready for
  stakeholder review

### Requirement: Run workspace auditability

The system MUST store each recollection attempt in a timestamped run
workspace with commands, environment fingerprint, dry-run output,
destructive cleanup confirmation if used, batch report, and skipped-check
rationale.

#### Scenario: Audit previous recollection

- **WHEN** a reviewer opens a recollection run workspace
- **THEN** they can see what database was targeted, what commands ran,
  what rows were affected, what validation passed, and what checks were
  skipped
