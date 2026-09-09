## MODIFIED Requirements

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
