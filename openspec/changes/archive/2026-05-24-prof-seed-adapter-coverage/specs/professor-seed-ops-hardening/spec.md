# Spec Delta: professor-seed-ops-hardening

## ADDED Requirements

### Requirement: Fetch-blocked evidence includes response shape

The system MUST persist response-shape evidence when a preview or sample seed
run is classified as `fetch_blocked`, so operators can distinguish a transport
failure, HTTP block, JavaScript challenge, and parser-low-quality case.

The evidence MUST include seed id, school, department, seed URL, trigger mode,
fetch method when known, HTTP status when known, response character count when
known, Chinese character count when known, anchor count when known, and the
failure class.

#### Scenario: Tokenized challenge page is diagnosable

- **GIVEN** a seed fetch returns a status 202 tokenized XHTML page
- **AND** the page has 0 Chinese characters and 0 anchors
- **WHEN** the seed run is classified as `fetch_blocked`
- **THEN** `pipeline_issue.evidence_snapshot` includes the HTTP status,
  response character count, Chinese character count, anchor count, seed
  identity, trigger mode, and `failure_class='fetch_blocked'`

#### Scenario: Browser connection close is diagnosable

- **GIVEN** a browser probe fails with `net::ERR_CONNECTION_CLOSED`
- **WHEN** the seed run is classified as `fetch_blocked`
- **THEN** `pipeline_issue.evidence_snapshot` includes the browser diagnostic
- **AND** the run is not classified as `parser_low_quality`
