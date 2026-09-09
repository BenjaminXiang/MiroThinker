# Spec: professor-seed-adapter-coverage

> Capability: The professor seed pipeline can prove row-level crawler/adapter
> coverage for the current real seed inventory before a staged collection phase
> is marked complete.

## ADDED Requirements

### Requirement: Real seed coverage guard

The system MUST provide a deterministic coverage guard for the professor seed
inventory. The guard MUST load `professor_seed` rows from the configured
database and report, for every row, the seed id, school, department, seed URL,
current `last_run_status`, resolver result, coverage state, diagnostic status,
and issue id or reason when available.

The guard MUST fail non-zero when any current seed has neither a registered
adapter/API path nor an approved blocked classification with structured
evidence.

#### Scenario: Missing adapter fails the guard

- **GIVEN** a `professor_seed` row has no resolver result
- **AND** it has no approved blocked classification with issue evidence
- **WHEN** the coverage guard runs
- **THEN** the guard exits non-zero
- **AND** the output includes the seed id, school, department, seed URL, and
  missing resolver state

#### Scenario: Full matrix is emitted

- **GIVEN** `miroflow_real.professor_seed` contains 20 rows
- **WHEN** the coverage guard runs against `miroflow_real`
- **THEN** the output includes all 20 seed rows
- **AND** each row includes a resolver result or blocked reason

### Requirement: Current seed inventory coverage

P4 completion MUST be based on the current real seed inventory, not only on
generic school families. Every current `miroflow_real.professor_seed` row MUST
be one of:

- runnable through a named school-specific roster adapter or registered API
  path with row-level E2E evidence; or
- explicitly classified as approved blocked, such as `fetch_blocked`, with
  structured `pipeline_issue` evidence.

A seed with a generic parser success but no named resolver result MUST NOT count
as covered.

#### Scenario: Generic parser success is not enough

- **GIVEN** a seed URL can be parsed by generic roster extraction
- **AND** `resolve_seed_adapter_name()` returns `None` for that seed
- **WHEN** the coverage guard evaluates the seed
- **THEN** the seed is reported as not covered
- **AND** P4 completion evidence cannot count the seed as successful

#### Scenario: Existing adapters still require E2E

- **GIVEN** a seed resolves to an existing adapter such as `szu-teacher-family`
- **WHEN** P4 completion evidence is assembled
- **THEN** the seed still requires row-level preview or sample E2E evidence
- **AND** the resolver name alone is insufficient completion evidence

### Requirement: SUIT/SZIIT named adapter coverage

The system MUST provide a named school-specific adapter or crawler path for the
SUIT/SZIIT seed URL `https://zd.suit-sz.edu.cn/jyjx/jsfc.htm`. The resolver
MUST return a stable adapter name for that URL family, and the adapter MUST
produce professor seed entries from the roster page when direct no-env fetching
returns the page body.

#### Scenario: SUIT seed resolves to a named adapter

- **GIVEN** a seed row for school `深圳信息职业技术大学`
- **AND** seed URL `https://zd.suit-sz.edu.cn/jyjx/jsfc.htm`
- **WHEN** `resolve_seed_adapter_name()` evaluates the seed
- **THEN** it returns a non-null named adapter
- **AND** the adapter name is included in the coverage guard output

#### Scenario: SUIT sample E2E produces professor candidates

- **GIVEN** the SUIT/SZIIT seed has a registered adapter
- **WHEN** a preview or bounded sample run is executed for seed id 24
- **THEN** the run produces professor candidate diagnostics from the roster
- **AND** the run evidence records the adapter name, candidate count, terminal
  status, and any issue outcome

### Requirement: UESTC/SIAS approved outcome

The four UESTC/SIAS seeds under `https://sias.uestc.edu.cn/rcpy/dsjs1/` MUST
not remain `adapter_missing` after this change. Each seed MUST either run
through a durable named adapter/fetch/parser path, or end as an approved
`fetch_blocked` outcome with structured evidence showing the challenge or
transport behavior.

Challenge pages with status 202, tokenized XHTML, 0 Chinese characters, and 0
anchors MUST NOT be treated as successful roster pages.

#### Scenario: UESTC challenge page is fetch blocked

- **GIVEN** a UESTC/SIAS seed returns a status 202 tokenized page with 0 Chinese
  characters and 0 anchors
- **WHEN** a preview or sample run evaluates the seed
- **THEN** the run is classified as `fetch_blocked`
- **AND** compatibility `last_run_status` is `failure`
- **AND** `pipeline_issue.evidence_snapshot` records seed id, school,
  department, seed URL, HTTP status, response shape, and fetch method

#### Scenario: UESTC durable fetch path is accepted

- **GIVEN** a UESTC/SIAS fetch strategy obtains a usable roster body
- **WHEN** the registered adapter parses the roster
- **THEN** the seed can be counted as runnable coverage
- **AND** E2E evidence records candidate count and terminal status for that
  seed

### Requirement: P4 E2E evidence matrix

P4 MUST NOT be marked complete until `acceptance.md` and
`.agents/runs/prof-seed-adapter-coverage/verification.md` contain a row-level
E2E matrix for every current real seed.

Each evidence row MUST include seed id, resolver result, trigger mode, command,
terminal status, items processed, items failed, pipeline run status, and
pipeline issue outcome.

#### Scenario: Completion requires all current rows

- **GIVEN** any current `miroflow_real.professor_seed` row is missing from the
  E2E evidence matrix
- **WHEN** P4 completion is evaluated
- **THEN** P4 is not complete

#### Scenario: Blocked seeds remain visible

- **GIVEN** a seed is classified as approved `fetch_blocked`
- **WHEN** P4 completion evidence is reviewed
- **THEN** the seed appears in the E2E matrix
- **AND** the row records the blocked classification and issue evidence rather
  than disappearing from successful coverage counts
