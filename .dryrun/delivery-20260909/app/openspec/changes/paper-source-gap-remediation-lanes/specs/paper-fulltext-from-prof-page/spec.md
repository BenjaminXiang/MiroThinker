## ADDED Requirements

### Requirement: Full-text acquisition is a bounded slow lane

PDF and full-text acquisition MUST run as a separate bounded slow lane for
source-gapped Paper rows. It MUST NOT be coupled to the main summary fast path.
The slow lane MUST record per-source failures without blocking other lanes.

#### Scenario: PDF failures are counted by reason

- **WHEN** the full-text slow lane attempts to fetch PDF or full-text evidence
- **THEN** its report records attempted, fetched, persisted, skipped, failed,
  timeout, HTTP status, content-type rejection, size-cap rejection, and parse
  failure counts
- **AND** representative failure samples include Paper id, source URL or
  provider, reason, and retry recommendation

#### Scenario: Slow lane does not block summary fast path

- **WHEN** PDF/full-text acquisition is slow, blocked, or rate-limited
- **THEN** existing-source-text summary generation can still run to completion
  independently
- **AND** the full-text lane remains resumable from its own checkpoint and run
  evidence

### Requirement: Full-text output feeds source-grounded summaries

Full-text extraction MUST produce source text evidence before any downstream
summary write. A fetched PDF or full-text page alone is insufficient; the lane
MUST persist a usable abstract, intro, or excerpt before a Paper becomes
eligible for summary generation.

#### Scenario: Fetched PDF with no usable text remains residual

- **WHEN** full-text fetch succeeds but extraction produces no usable abstract,
  intro, or excerpt
- **THEN** the Paper remains missing source text for summary generation
- **AND** the report records a full-text extraction residual instead of writing
  `summary_zh`
