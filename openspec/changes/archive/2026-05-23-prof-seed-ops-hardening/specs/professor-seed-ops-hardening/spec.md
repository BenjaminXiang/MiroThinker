# Spec: professor-seed-ops-hardening

> Capability: Professor seed runs can be triggered safely in bounded
> modes and report diagnostic failure classes suitable for operations.

## ADDED Requirements

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
