# paper-ingest-dedup Specification

## Purpose
TBD - created by archiving change ingest-dedup-anchor-before-insert. Update Purpose after archive.
## Requirements
### Requirement: Content-anchor dedup before INSERT

The system SHALL check a content anchor (DOI > arxiv_id > canonical-title+year) against the global `paper` table before INSERTing a new `paper` row at ingest. The title+year path SHALL NOT require author-overlap.

#### Scenario: Co-authored paper on a second professor's page reuses the existing row
- **WHEN** a paper (title T, year Y) was already inserted for professor A, and professor B's homepage lists the same paper (title T', year Y, no DOI/arxiv)
- **THEN** the ingest finds the existing paper via the content anchor (canonical-title+year) and creates a `professor_paper_link` for professor B, WITHOUT INSERTing a new `paper` row

#### Scenario: DOI match reuses the existing row
- **WHEN** a paper with DOI D was already inserted, and a new ingest has DOI D
- **THEN** the ingest finds the existing paper via DOI and link-attaches

#### Scenario: arxiv match reuses the existing row
- **WHEN** a paper with arxiv_id A was already inserted, and a new ingest has arxiv_id A
- **THEN** the ingest finds the existing paper via arxiv_id and link-attaches

#### Scenario: No content-anchor match — INSERT proceeds
- **WHEN** no existing paper matches the content anchor (DOI/arxiv/title+year)
- **THEN** the ingest proceeds to INSERT a new `paper` row (unchanged behavior)

### Requirement: Anchor normalization consistency

The content-anchor check's title normalization SHALL be identical to `canonical_writer._build_paper_id`'s title branch, so the pre-INSERT check finds rows that INSERT would dedup.

#### Scenario: Title-normalization consistency
- **WHEN** the ingest checks the content anchor for a title T
- **THEN** the normalization used (whitespace-stripped-lowercased title + year) matches `canonical_writer._build_paper_id`'s title fallback, ensuring a hit maps to the same `paper_id`

