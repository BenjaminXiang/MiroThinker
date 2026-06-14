# professor-publish-index-refresh Specification

## Purpose
TBD - created by archiving change prof-publish-index-refresh. Update Purpose after archive.
## Requirements
### Requirement: P9 preflight uses the current P8 audit

P9 MUST run the current P8 post-full quality audit against `miroflow_real`
before any Professor publish/index refresh. P9 MUST NOT refresh the index while
the audit reports any P9 blocker.

#### Scenario: P8 audit allows P9

- **WHEN** the P8 audit reports `p9_readiness=ready`
- **AND** `p9_blockers` is empty
- **THEN** P9 may proceed to publish/index refresh
- **AND** the P9 acceptance evidence records the audit command and summary

#### Scenario: P8 audit blocks P9

- **WHEN** the P8 audit reports one or more P9 blockers
- **THEN** P9 records the blockers
- **AND** P9 does not run the index refresh command

### Requirement: P9 records residual-risk decisions before refresh

P9 MUST explicitly record whether duplicate identity risk groups and historical
quality-gate issue counts are blockers for the publish/index refresh. If they
are accepted as non-blocking, the acceptance MUST state that P9 does not claim
duplicate cleanup or quality-status remediation is complete.

#### Scenario: Residual risks are accepted for index refresh only

- **WHEN** duplicate-risk groups or quality-gate issues remain in the P8 audit
- **THEN** P9 acceptance evidence lists them
- **AND** P9 records whether they are accepted as non-blocking for this refresh
- **AND** P9 does not mark duplicate cleanup or quality remediation complete

### Requirement: P9 refreshes Professor split indexes from canonical rows

P9 MUST refresh the Professor identity and research Milvus collections from the
current canonical Professor rows in `miroflow_real`. The refresh MUST record the
database URL target, Milvus URI, rebuild mode, row counts, processed counts,
skipped counts, error counts, and per-collection counts.

#### Scenario: Split index refresh succeeds

- **WHEN** P9 runs the Professor Milvus backfill with rebuild enabled
- **THEN** the command exits successfully
- **AND** `professor_identity_profiles` and `professor_research_profiles`
  receive refreshed records
- **AND** the report records zero unhandled errors

### Requirement: P9 verifies refreshed retrieval payloads

P9 MUST verify at least one refreshed Professor retrieval payload after the
index refresh. The verification MUST include the BRESAR, Miha CUHK(SZ) SDS
record and prove the visible title is `助理教授`.

#### Scenario: BRESAR title is visible after refresh

- **WHEN** the refreshed Professor index is queried for BRESAR, Miha
- **THEN** the result set includes the BRESAR Professor id
- **AND** the visible title is exactly `助理教授`
- **AND** the verification records whether quality-status filtering was enabled
  or disabled

### Requirement: P9 completion updates required artifacts

P9 MUST NOT be marked complete until `tasks.md`, `acceptance.md`, and
`.agents/runs/prof-publish-index-refresh/verification.md` include the preflight
audit, refresh command, retrieval smoke results, skipped operations, residual
risk decisions, and OpenSpec validation evidence.

#### Scenario: Artifact evidence is complete

- **WHEN** P9 refresh and verification finish
- **THEN** `tasks.md` is updated only after evidence exists
- **AND** `acceptance.md` records per-requirement evidence
- **AND** the run verification file records exact commands and outcomes

