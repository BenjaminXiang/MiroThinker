# professor-seed-ops-hardening Specification

## Purpose
Define safety and observability requirements for Professor seed operations,
including bounded trigger modes, failure-class reporting, safe UI trigger
choices, and fetch-blocked diagnostic evidence.
## Requirements
### Requirement: Seed trigger supports bounded modes

The system MUST support `full`, `sample`, and `preview` modes when an
admin triggers a single professor seed.

`full` mode MAY run the complete seed and write canonical rows.
`sample` mode MUST require a positive `limit` and MUST write no more
than that number of professor bundles. `preview` mode MUST perform
fetch/parse diagnostics without writing canonical professor rows.

An empty request body to `POST /api/seeds/{id}/trigger` MUST remain
backward-compatible and behave as `full`.

#### Scenario: Sample trigger is bounded

- **GIVEN** a seed whose full roster contains many profiles
- **WHEN** an admin triggers it with `mode="sample"` and `limit=3`
- **THEN** the run writes at most three professor bundles
- **AND** `pipeline_run.run_scope` records `trigger_mode="sample"` and
  `limit=3`

#### Scenario: Preview does not write canonical rows

- **GIVEN** a seed exists
- **WHEN** an admin triggers it with `mode="preview"`
- **THEN** the system fetches and parses enough to report diagnostic
  shape
- **AND** no canonical professor row is inserted or updated by that run

### Requirement: Seed runs report failure classes

The system MUST classify terminal single-seed outcomes with one of:
`adapter_missing`, `fetch_blocked`, `parser_low_quality`,
`pipeline_exception`, or `success`.

The compatibility `last_run_status` MUST remain one of the existing
values from `prof-seed-admin-console`. `adapter_missing` maps to the
existing `adapter_missing` status. `fetch_blocked`,
`parser_low_quality`, and `pipeline_exception` map to compatibility
`failure`, with the detailed class stored in the run and issue payloads.

#### Scenario: HTTP 412 is fetch blocked, not adapter missing

- **GIVEN** a seed has a registered adapter
- **AND** fetching the page fails with HTTP 412 or equivalent
  JavaScript challenge behavior
- **WHEN** the run finishes
- **THEN** `failure_class` is `fetch_blocked`
- **AND** compatibility `last_run_status` is `failure`
- **AND** the issue payload records the HTTP/browser diagnostic

#### Scenario: Parser low quality is distinct from fetch blocked

- **GIVEN** fetching succeeds
- **AND** parser output is below the configured usable-roster threshold
- **WHEN** the run finishes
- **THEN** `failure_class` is `parser_low_quality`
- **AND** compatibility `last_run_status` is `failure`

### Requirement: Seed UI exposes safe trigger choices

The seed management UI MUST require an explicit trigger-mode choice
before starting a seed run. The recommended/default UI choice MUST be a
bounded mode, not an unbounded full crawl.

#### Scenario: Full run requires explicit confirmation

- **GIVEN** an admin clicks the seed trigger action
- **WHEN** they choose `full`
- **THEN** the UI shows the seed identity before submitting
- **AND** the submitted request records `mode="full"`

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

### Requirement: Refreshed blocked evidence records source-remediation context

The system MUST preserve source-remediation context when a P5
source-remediation run keeps a seed in `fetch_blocked`. It MUST preserve the
existing response-shape evidence and also record the
source-remediation context needed by operators: original URL, replacement URLs
that were evaluated, rejection reason for each replacement candidate, and the
final operator-facing next action.

#### Scenario: Replacement unavailable is diagnosable

- **GIVEN** seed id 5 still fails against the current CSSE URL
- **AND** no official replacement source is accepted
- **WHEN** P5 records a `fetch_blocked` outcome
- **THEN** the evidence includes HTTP/browser diagnostics for the current URL
- **AND** it includes the evaluated replacement candidates and why they were not
  accepted
- **AND** the outcome remains distinct from `parser_low_quality`

### Requirement: P6 trigger recommendations respect bounded modes

P6 MUST use the existing `preview`, `sample`, and `full` trigger modes when
recommending next actions for Professor seed operations.

The default recommendation for a resolver-covered seed without current bounded
evidence MUST be a bounded mode. An unbounded `full` recommendation MUST only
appear after successful post-P5 sample evidence and MUST still require a later
explicit operator confirmation before execution.

#### Scenario: Default recommendation is bounded

- **WHEN** a seed has a named resolver but lacks post-P5 sample evidence
- **THEN** the P6 recommendation is not `full`
- **AND** the recommendation records the bounded mode needed next

#### Scenario: Full recommendation remains confirmation-gated

- **WHEN** a seed is recommended as `full` by the P6 planner
- **THEN** the matrix records the bounded sample run that justifies it
- **AND** P6 does not execute the full run automatically

### Requirement: P6 verification records skipped unsafe operations

P6 verification MUST explicitly record that destructive cleanup and unbounded
bulk full runs were skipped. The record MUST include the reason and the next
stage that would own those operations if approved.

#### Scenario: Unsafe operation is skipped with reason

- **WHEN** P6 verification is written
- **THEN** it states that cleanup and unbounded full recollection were not run
- **AND** it identifies the later-stage approval point for those operations

### Requirement: P7 full mode remains controlled and auditable

P7 full-mode execution MUST remain controlled, row-level auditable, and
separate from cleanup or publish refresh. Full-mode runs MUST record the same
run-scope fields used by existing seed-runner semantics, including trigger
mode, limit, failure class, diagnostic profile count when available, and
written profile count when available.

#### Scenario: Full run records run scope

- **WHEN** P7 executes a seed in `full` mode
- **THEN** the resulting `pipeline_run.run_scope` records
  `trigger_mode='full'`
- **AND** the run records the terminal failure class and write counts when
  available

#### Scenario: P7 does not bypass blocked evidence

- **WHEN** a seed has current blocked evidence and is not full-ready
- **THEN** P7 does not force a `full` run for that seed
- **AND** the skipped row remains visible in the evidence

