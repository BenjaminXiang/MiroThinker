# Spec: paper-fulltext-from-prof-page

> Capability: Direct PDFs linked from professor pages can be fetched,
> persisted by hash, and attached to paper full-text storage.

## ADDED Requirements

### Requirement: Professor-page PDF links are discoverable

The paper page-ingest path MUST preserve direct PDF links found near
publication entries on professor pages.

#### Scenario: Publication entry links PDF

- **GIVEN** a Publications entry contains a direct PDF link
- **WHEN** homepage paper ingest parses the entry
- **THEN** the paper candidate carries the PDF URL as full-text
  evidence

### Requirement: PDF fetch is capped and diagnostic

The fetcher MUST enforce size, timeout, content-type, redirect, and
per-run count caps. Cap violations MUST create diagnostic issues
without aborting the whole seed run.

#### Scenario: PDF exceeds size cap

- **GIVEN** a PDF URL responds with content larger than the configured
  cap
- **WHEN** PDF fetch runs
- **THEN** no raw PDF is persisted
- **AND** a diagnostic pipeline issue is written

### Requirement: Raw PDFs are deduped by sha256

Raw PDF persistence MUST key content by sha256 or an approved blob
reference containing sha256. Repeated fetches of identical content MUST
not create duplicate raw blobs.

#### Scenario: Duplicate PDF content is reused

- **GIVEN** two paper entries link the same PDF bytes
- **WHEN** full-text ingest runs
- **THEN** the raw PDF content is stored once by sha256
- **AND** both paper full-text records can reference it
