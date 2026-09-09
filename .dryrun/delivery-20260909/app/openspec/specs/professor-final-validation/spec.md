# professor-final-validation Specification

## Purpose
TBD - created by archiving change prof-final-validation. Update Purpose after archive.
## Requirements
### Requirement: P10 runs a fresh Professor audit preflight

P10 MUST run the current Professor post-full quality audit against
`miroflow_real` before final user-facing or API validation. P10 MUST record
`p9_readiness`, `p9_blockers`, known field defects, duplicate-risk groups,
quality-status distribution, and open issue counts.

#### Scenario: Audit preflight allows final validation

- **WHEN** the audit reports `p9_readiness=ready`
- **AND** `p9_blockers` is empty
- **THEN** P10 may run final validation checks
- **AND** P10 acceptance evidence records the audit command and summary

#### Scenario: Audit preflight blocks final validation

- **WHEN** the audit reports one or more P9 blockers
- **THEN** P10 records the blockers
- **AND** P10 does not claim final validation completion

### Requirement: P10 validates the P9 persistent Professor index artifact

P10 MUST validate the persistent P9 Milvus artifact before final retrieval
checks. The validation MUST verify the exact Milvus URI, collection existence,
collection row counts, and BRESAR identity payload.

#### Scenario: P9 artifact is usable

- **GIVEN** P9 selected `/tmp/p9prof25.db`
- **WHEN** P10 opens the artifact in a fresh process with
  `MILVUS_USE_REAL_CLIENT=1`
- **THEN** `professor_identity_profiles` exists
- **AND** `professor_research_profiles` exists
- **AND** the identity collection contains BRESAR with `title=助理教授`

### Requirement: P10 verifies final Professor retrieval behavior

P10 MUST run final Professor identity and research retrieval smokes against the
P9 artifact. The checks MUST record the query text, quality-filter setting,
returned object ids, collection names, retrieval-index labels, and BRESAR title
visibility.

#### Scenario: BRESAR identity is visible when quality filtering is disabled

- **WHEN** a BRESAR identity retrieval smoke runs with
  `filter_by_quality_status=false`
- **THEN** the result set includes `PROF-6553974C5393`
- **AND** the visible title is exactly `助理教授`
- **AND** the result metadata records `quality_status=needs_enrichment`

#### Scenario: Default quality filter behavior is documented

- **WHEN** the same BRESAR identity retrieval smoke runs with default
  quality-status filtering
- **THEN** P10 records whether BRESAR is hidden or visible
- **AND** P10 records the launch implication of that behavior

#### Scenario: Research retrieval uses the research split collection

- **WHEN** a Professor research-topic query runs
- **THEN** at least one result is returned from `professor_research_profiles`
- **AND** the result metadata records `professor_retrieval_index=research`

### Requirement: P10 records API or chat validation status

P10 MUST attempt a final API or chat-level Professor validation when the local
runtime can be started safely. If API validation cannot run, P10 MUST record
the blocker, confidence impact, and next command.

#### Scenario: API smoke runs

- **WHEN** the local runtime is available with the P9 retrieval configuration
- **THEN** P10 runs a Professor API or chat smoke
- **AND** records the command, URL, response summary, and source traceability

#### Scenario: API smoke cannot run safely

- **WHEN** runtime startup or configuration is unsafe or unavailable
- **THEN** P10 records the exact blocker
- **AND** P10 does not claim API validation passed

### Requirement: P10 records final residual-risk decisions

P10 MUST classify remaining duplicate-risk groups, quality-gate issue counts,
dirty canonical names, seed 5 carryover, and skipped cleanup operations as
launch blockers or accepted residual risks. P10 MUST NOT mark cleanup complete
unless separate cleanup evidence exists.

#### Scenario: Residual risks are explicitly classified

- **WHEN** final validation finishes
- **THEN** P10 acceptance evidence includes a residual-risk decision table
- **AND** every accepted residual risk includes confidence impact and follow-up
- **AND** every blocker includes the next required remediation step

### Requirement: P10 completion updates required artifacts

P10 MUST NOT be marked complete until `tasks.md`, `acceptance.md`, and
`.agents/runs/prof-final-validation/verification.md` contain the audit
preflight, artifact verification, retrieval/API checks, quality-filter result,
residual-risk decisions, targeted tests or skipped-check rationale, and
OpenSpec validation evidence.

#### Scenario: Artifact evidence is complete

- **WHEN** P10 validation finishes
- **THEN** `tasks.md` is updated only after evidence exists
- **AND** `acceptance.md` records per-requirement evidence
- **AND** the run verification file records exact commands and outcomes

