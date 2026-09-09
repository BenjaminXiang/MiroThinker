## ADDED Requirements

### Requirement: Source-gapped rows are not repaired by direct LLM fabrication

Paper cleanup MUST NOT use an LLM to invent abstracts, venues, identifiers, or
Chinese summaries for rows with no usable source text. LLM usage is allowed for
translation, summarization, self-check, and classification only when the input
evidence is recorded.

#### Scenario: Missing source text blocks summary write

- **WHEN** a Paper row has no usable abstract, full-text excerpt, or other
  approved source text
- **THEN** LLM summary generation MUST NOT write `summary_zh`
- **AND** the row is reported as source-gapped with the next action needed

### Requirement: Paper cleanup preserves the professor-seeded boundary

Paper cleanup MUST preserve the Professor official-page seed boundary. It MAY
enrich already discovered Paper rows by official page evidence, title, DOI,
OpenAlex id, Crossref metadata, arXiv id, or full-text source evidence, but it
MUST NOT create Professor paper lists from author-name searches against
external scholarly providers.

#### Scenario: Author-name discovery remains forbidden

- **WHEN** a cleanup lane needs more Paper source evidence for a Professor
- **THEN** it does not call author-name Paper discovery providers to create new
  Professor-Paper links
- **AND** it records the row as requiring homepage parser repair, identifier
  evidence, or manual review

### Requirement: Interrupted remediation runs close with evidence

Long-running remediation workers MUST leave terminal pipeline-run state when
operators stop or supersede them. Partial runs MUST record checkpoint counts
and interruption reasons so later audits do not misread them as active work.

#### Scenario: Superseded worker is closed as partial

- **WHEN** an operator terminates a worker because the lane is too slow or has
  been superseded by a better lane
- **THEN** the corresponding pipeline run is marked `partial`
- **AND** its error summary records checkpoint counts, written rows, skipped
  rows, rejected rows, and the interruption reason
