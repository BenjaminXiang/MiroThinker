# professor-summary-fields Specification

## Purpose
Define durable professor-level paper and patent output summaries used as
stable downstream inputs for research retrieval and vector refresh.

## Requirements
### Requirement: Professor output summaries are durable

The system MUST persist a professor-level paper summary and patent
summary, either as nullable `professor` columns or an equivalent
professor summary table that the vector publisher can query.

#### Scenario: Professor with verified papers gets paper summary

- **GIVEN** a professor has accepted professor-paper links
- **WHEN** the summary backfill runs
- **THEN** the professor receives a durable `paper_summary`
- **AND** the summary is derived from accepted linked papers only

### Requirement: Rejected and uncertain links are excluded

The summary generator MUST exclude rejected, uncertain, or unresolved
paper/patent links.

#### Scenario: Rejected paper does not affect summary

- **GIVEN** a professor has one accepted paper link and one rejected
  paper link
- **WHEN** `paper_summary` is generated
- **THEN** only the accepted paper contributes to the summary

### Requirement: Summary changes are refreshable

When `paper_summary` or `patent_summary` changes, the professor MUST be
discoverable by a later research-vector refresh.

#### Scenario: Changed output summary marks professor for vector refresh

- **GIVEN** a professor research vector already exists
- **WHEN** `paper_summary` changes
- **THEN** the professor can be selected for research-vector rebuild
