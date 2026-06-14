# company-prd-acceptance-closure Specification

## Purpose
TBD - created by archiving change company-prd-acceptance-closure. Update Purpose after archive.
## Requirements
### Requirement: Company mandatory summaries SHALL be complete

The system SHALL provide an acceptance repair path that verifies every released Company record has non-empty `profile_summary` and `technology_route_summary`.

When either mandatory summary is missing, the repair path SHALL backfill the field from trusted XLSX baseline fields and accepted Company source material before claiming PRD completeness. The repair report SHALL include the pre-run missing count, repaired company IDs, unrepaired company IDs, and post-run missing count.

#### Scenario: Missing mandatory summaries are repaired
- **WHEN** the Company summary completeness repair runs against the current canonical Company table
- **THEN** the report includes the number of companies missing `profile_summary` or `technology_route_summary` before the repair
- **AND** companies with enough trusted XLSX or accepted source material receive non-empty values
- **AND** the post-run report shows the remaining missing count

#### Scenario: Sparse company remains explicitly blocked
- **WHEN** a company lacks enough trusted material to generate either mandatory summary
- **THEN** the company remains listed in the report with a blocker reason
- **AND** the repair does not fabricate unsupported summary text

### Requirement: Company Top-5 retrieval relevance SHALL be evaluated with human labels

The system SHALL provide a reproducible Company retrieval evaluation harness for at least 50 enterprise-class queries. Each query SHALL retrieve the current Top-5 Company results from the active Company retrieval path and export an annotation-ready CSV.

The CSV SHALL include query metadata, rank, company ID, company name, retrieval score when available, profile summary, technology-route summary, product snippets, scenario snippets, evidence/source hints, and empty human label fields. The acceptance report SHALL compute Top-5 hit rate from human labels and SHALL pass only when at least 85% of queries contain at least one `hit` result in the Top-5.

`partial` labels SHALL be reported for diagnostics but SHALL NOT count as PRD hits unless the user explicitly changes the scoring rule.

#### Scenario: Retrieval evaluation CSV is generated
- **WHEN** the Company Top-5 evaluation harness runs with at least 50 queries
- **THEN** it exports one annotation-ready row per query-result pair
- **AND** each query has at most five ranked Company results
- **AND** each row includes enough Company context for human relevance review

#### Scenario: Human labels produce PRD pass or fail
- **WHEN** a labeled Company Top-5 CSV is scored
- **THEN** the report computes query-level Top-5 hit rate as labeled queries with at least one `hit` in rank 1 through 5 divided by total labeled queries
- **AND** the report marks the PRD gate passed only when the hit rate is at least 85%
- **AND** Top-1 hit rate, Precision@5, partial count, and failure reasons are reported as auxiliary diagnostics

### Requirement: Company retrieval SHALL support a ten-query candidate-pool pilot before full PRD labeling

Before the full 50-query Top-5 PRD labeling pass, the system SHALL provide a ten-query pilot export that helps reviewers decide whether each query is answerable from the current 1024-company corpus. The pilot SHALL not claim the PRD Top-5 gate as passed.

The candidate-pool export SHALL merge active semantic retrieval candidates with corpus lexical candidates built from company names, summaries, technology-route summaries, products, application scenarios, business descriptions, industry fields, and evidence hints. Each row SHALL preserve whether the candidate appeared in the active retrieval Top-5.

Human scoring SHALL support query-level `answerable`, `corpus_gap`, and `uncertain` states. Top-5 hit-rate metrics SHALL be computed only for queries marked `answerable`; `corpus_gap` queries SHALL be reported as corpus coverage gaps instead of retrieval misses.

#### Scenario: Candidate-pool pilot is generated
- **WHEN** the ten-query Company retrieval pilot runs
- **THEN** it exports an annotation-ready candidate-pool CSV for ten queries
- **AND** each row includes candidate source, retrieval rank when present, Top-5 membership, lexical matched terms, company context, products, scenarios, and empty human label fields
- **AND** the export report records query count, candidate row count, retrieval depth, lexical depth, pool size, and fallback-reranker usage

#### Scenario: Candidate-pool labels separate corpus gaps from retrieval misses
- **WHEN** a labeled candidate-pool CSV is scored
- **THEN** the report counts answerable, corpus-gap, uncertain, and unlabeled queries separately
- **AND** Top-5 hit rate, Top-1 hit rate, and Precision@5 are computed only over answerable queries
- **AND** answerable queries with a hit outside the active Top-5 are reported as retrieval misses
- **AND** corpus-gap queries are reported as corpus coverage gaps, not Top-5 failures

### Requirement: Company evidence SHALL be visible at API and release boundaries

The system SHALL audit Company detail API and release payloads for evidence/source traceability. The audit SHALL cover profile summary, technology-route summary, products, application scenarios, recent dynamics, and financing events when those facts are present.

For each sampled Company, the audit SHALL verify that source type or source tier, source URL or stable source identifier, update timestamp or capture timestamp, and field-level evidence/support are present when available in storage. Missing evidence SHALL be reported with the affected API/release field and company ID.

#### Scenario: Detail API exposes source-backed facts
- **WHEN** the evidence/source audit samples Company detail API payloads
- **THEN** source-backed products, scenarios, signal events, profile summaries, and technology summaries include traceable source metadata when available
- **AND** missing source metadata is listed as an audit failure with company ID and field path

#### Scenario: Release payload retains evidence
- **WHEN** the evidence/source audit samples Company release payloads
- **THEN** released Company records retain evidence/source entries for published source-backed facts
- **AND** the audit distinguishes XLSX source identifiers from external URL-backed sources

### Requirement: Company deduplication accuracy SHALL use labeled candidate pairs

The system SHALL provide a duplicate-pair evaluation harness that exports at least 100 Company candidate pairs for human labeling. Candidate pairs SHALL include likely duplicates, likely non-duplicates, and hard ambiguous pairs.

The pair CSV SHALL include both Company IDs, names, normalized names, credit codes when present, legal representatives when present, websites when present, address or region hints when present, profile snippets, and the system's duplicate prediction. The scoring report SHALL compute deduplication accuracy from human labels, excluding `uncertain` rows.

#### Scenario: Duplicate candidate pairs are exported
- **WHEN** the deduplication evaluation harness runs
- **THEN** it exports at least 100 candidate pairs
- **AND** each pair contains enough comparison fields for a human to label `duplicate`, `not_duplicate`, or `uncertain`
- **AND** the file preserves the system prediction separately from the human label

#### Scenario: Labeled pairs produce deduplication accuracy
- **WHEN** a labeled duplicate-pair CSV is scored
- **THEN** the report excludes `uncertain` rows
- **AND** computes accuracy, true positives, false positives, true negatives, and false negatives
- **AND** marks the PRD gate passed only when labeled accuracy is at least 95%

### Requirement: Company refresh SHALL support monthly and on-demand incremental execution

The system SHALL provide an operator workflow for monthly and on-demand Company refreshes. The workflow SHALL select companies by uploaded/touched IDs, stale source timestamps, missing mandatory fields, explicit company IDs, or explicit operator request.

The refresh workflow SHALL support dry-run mode, checkpoint/resume, bounded external-source stages, touched-company vector refresh, and a report that includes selected companies, skipped companies, enabled stages, write counts, runtime, failures, and next retry candidates.

#### Scenario: Monthly refresh dry-run reports scope
- **WHEN** an operator runs the Company refresh workflow in monthly dry-run mode
- **THEN** the report lists selected companies, selection reasons, enabled stages, skipped stages, expected writes, and expected vector refresh count
- **AND** no business fact tables are modified

#### Scenario: On-demand refresh stays scoped
- **WHEN** an operator runs an on-demand refresh for explicit Company IDs
- **THEN** only those Company IDs are processed
- **AND** vector refresh is restricted to touched companies
- **AND** failures are checkpointed for retry without rerunning successful stages by default

### Requirement: Company review-state policy SHALL separate publication from human review

The system SHALL define a Company review-state policy that determines whether facts are visible in default detail and retrieval surfaces. High-confidence XLSX baseline facts, official-site facts, and source-judged external facts with target-company identity and attribution evidence MAY be visible without per-row human review. Low-confidence generic web facts, weakly attributed facts, conflicting facts, and rejected facts MUST remain out of default published surfaces and retrieval text.

The policy SHALL preserve review state for operator audit. It SHALL NOT require all Company data to be human-reviewed before publication.

#### Scenario: High-confidence fact is visible before manual review
- **WHEN** a Company product or scenario is derived from trusted XLSX or official-site material with identity and attribution evidence
- **THEN** the review policy allows it to appear in default Company detail and retrieval surfaces
- **AND** the row still preserves source evidence and review status for audit

#### Scenario: Low-confidence generic fact remains review-gated
- **WHEN** a Company fact comes only from weak generic web material or has unresolved attribution
- **THEN** the review policy excludes it from default Company detail and retrieval surfaces
- **AND** the fact remains available in review or diagnostic surfaces with the rejection or review reason

