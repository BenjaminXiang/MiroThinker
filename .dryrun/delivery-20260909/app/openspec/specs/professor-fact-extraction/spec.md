# professor-fact-extraction Specification

## Purpose
TBD - created by archiving change prof-fact-extraction-expansion. Update Purpose after archive.
## Requirements
### Requirement: Extract structured experience facts

The system MUST extract `education`, `work_experience`, `award`, and
`academic_position` facts from non-empty `profile_raw_text` using a
structured extraction flow. For Tsinghua SIGS `.sudy-tab` pages, deterministic
section parsing MUST extract those fact types directly from labeled official
sections before any LLM-backed enrichment. Extracted facts MUST be written to
`professor_fact` with provenance, evidence span, confidence, status, and run
id.

#### Scenario: Education fact is persisted with provenance

- **GIVEN** a professor profile raw text mentions a PhD education entry
- **WHEN** the fact extractor runs
- **THEN** an active `professor_fact` row is written with
  `fact_type = education`
- **AND** the row includes source page, evidence span, confidence, and
  run id

#### Scenario: SIGS labeled sections are extracted deterministically

- **GIVEN** a Tsinghua SIGS official profile page contains `教育经历`,
  `工作经历`, `学术兼职`, and `荣誉奖项` sections in `.sudy-tab`
- **WHEN** the deterministic SIGS tab extractor runs
- **THEN** it returns `education`, `work_experience`,
  `academic_position`, and `award` fact candidates without requiring an LLM

### Requirement: Backfill uses measured eligible set

The runner MUST preflight the eligible set before writing data. The
eligible set MUST be measured from current canonical rows and MUST NOT
use a hardcoded count from earlier join-inflated queries.

#### Scenario: Preflight reports skipped rows

- **GIVEN** some professor rows have no `profile_raw_text`
- **WHEN** the preflight runs
- **THEN** those rows are counted as skipped
- **AND** they are not sent to the LLM extractor

### Requirement: Backfill is idempotent and failure-isolated

The backfill runner MUST avoid duplicating active facts on repeated
runs. A failure for one professor MUST be logged and counted without
aborting the full batch.

For this child, duplicate detection MUST use the application-level
active-fact key:

```text
professor_id + fact_type + normalized_fact_key
```

where `normalized_fact_key` is `value_normalized` when present, and
otherwise a deterministic normalized form of `value_raw` (trimmed,
case-folded where applicable, and whitespace-collapsed). `source_page_id`
and `evidence_span` MUST NOT be part of the duplicate key; they are
provenance fields. If the same fact is seen again with different
provenance, the existing active fact is updated or supplemented rather
than creating another active row.

#### Scenario: Re-running does not duplicate facts

- **GIVEN** a backfill has already written an education fact for a
  professor
- **WHEN** the same profile text is processed again
- **THEN** no duplicate active education fact is created

#### Scenario: Same fact from another span does not duplicate

- **GIVEN** an active `award` fact exists for a professor with
  `value_normalized = "National Science Fund for Distinguished Young Scholars"`
- **WHEN** the extractor finds the same normalized award in another
  evidence span or source page
- **THEN** the existing active fact is updated or supplemented
- **AND** no second active fact with the same active-fact key is created

### Requirement: Backfill triggers quality re-evaluation

After a successful backfill batch, the runner MUST invoke the
`prof-quality-status-rework` re-evaluation entry point so the
newly-written facts can update professor quality status.

#### Scenario: New facts improve quality status

- **GIVEN** a trustworthy professor was previously
  `needs_enrichment` due to missing facts
- **WHEN** the backfill writes the missing facts and re-evaluation runs
- **THEN** the resulting quality status reflects the updated canonical
  state

