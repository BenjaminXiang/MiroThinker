## ADDED Requirements

### Requirement: Paper source gaps are classified before remediation

The system MUST provide a read-only source-gap audit for active Paper rows
missing `summary_zh` or `abstract_clean`. The audit MUST classify each row into
one primary next-action lane and preserve source-bucket counts so operators can
run the right remediation path instead of a broad mixed backfill.

#### Scenario: Source-gap audit reports lane counts

- **WHEN** the Paper source-gap audit runs against active Paper rows
- **THEN** it reports counts for existing abstract fast path, identifier
  metadata enrichment, professor-page full-text acquisition,
  `prof_page_only` title/parser cleanup, review-only residuals, and unsafe
  rows
- **AND** it records source buckets, selected Paper ids, skipped reasons, and a
  deterministic selection hash for each lane

#### Scenario: Row has exactly one primary next action

- **WHEN** a Paper row qualifies for multiple possible repair paths
- **THEN** the audit assigns one primary next-action lane using the configured
  precedence
- **AND** lower-priority possible actions remain visible as secondary evidence

### Requirement: Existing source text uses a summary fast path

The system MUST support a fast summary lane for Papers that already have usable
`abstract_clean`, `paper_full_text.abstract`, or `paper_full_text.intro`. This
lane MUST run LLM Chinese summary generation without DOI metadata enrichment,
PDF fetching, or title resolver calls.

#### Scenario: Existing abstract summary lane avoids source acquisition

- **WHEN** the existing-source-text summary lane runs
- **THEN** it selects only rows with usable existing source text and missing
  `summary_zh`
- **AND** it MUST NOT call DOI metadata providers, title resolver providers, or
  PDF/full-text fetchers
- **AND** its report records processed, written, rejected, skipped, provider
  failures, and script-level row errors

### Requirement: Prof-page-only rows require conservative source repair

Remaining `prof_page_only` rows MUST be treated as source-acquisition or parser
cleanup work. They MUST NOT receive LLM-generated summaries unless a title
resolver, homepage parser, official page, or full-text lane first provides
usable source text.

#### Scenario: Prof-page-only row without source text remains residual

- **WHEN** a `prof_page_only` Paper row has no usable abstract, full-text
  excerpt, DOI, OpenAlex id, arXiv id, or high-confidence title-resolution
  evidence
- **THEN** the row remains in a residual source-gap bucket
- **AND** the system records the missing source evidence instead of generating
  `summary_zh`

#### Scenario: Re-resolution preserves professor-page evidence

- **WHEN** title re-resolution finds a higher-quality canonical Paper row for a
  professor-page Paper
- **THEN** the official Professor-page link evidence is migrated or aliased to
  the canonical Paper
- **AND** unresolved or low-confidence title matches remain unresolved with
  source-quality evidence
