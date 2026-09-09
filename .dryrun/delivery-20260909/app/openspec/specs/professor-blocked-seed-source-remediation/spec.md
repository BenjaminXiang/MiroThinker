# professor-blocked-seed-source-remediation Specification

## Purpose
TBD - created by archiving change prof-blocked-seed-source-remediation. Update Purpose after archive.
## Requirements
### Requirement: P5 source audit for blocked professor seeds

P5 MUST audit every professor seed that was approved blocked in the P4 matrix,
plus any resolver-covered seed whose P4 row ended in `fetch_blocked`. The audit
MUST record seed id, school, department, current seed URL, current P4 outcome,
official replacement candidates, fetch status, roster usability, and the final
P5 decision for each audited seed.

The system MUST NOT count a replacement source as successful unless it is an
official school, university, or university-operated source and returns usable
professor roster or mentor detail data.

#### Scenario: P5 audit includes all blocked rows

- **GIVEN** the P4 matrix contains seed 5 with `fetch_blocked`
- **AND** the P4 matrix contains seeds 25, 26, 27, and 28 with `fetch_blocked`
- **WHEN** P5 source audit evidence is assembled
- **THEN** all five seed ids appear in the P5 audit matrix
- **AND** each row records whether an official replacement source is accepted,
  rejected, or unavailable

#### Scenario: Unofficial source is rejected

- **GIVEN** a search result, cached page, or mirror lists teacher names
- **AND** it is not an official school, university, or university-operated
  source
- **WHEN** P5 evaluates the source
- **THEN** the source is rejected as successful crawl evidence
- **AND** the seed remains blocked or requires another official source

### Requirement: UESTC official mentor source coverage

The system MUST provide a named adapter or registered fallback path for UESTC
graduate mentor list pages under
`https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc`. For seed ids 25-28, the adapter
MUST use `yxsh=28` and the program-specific `zydm` filter mapped from the
current seed department.

The adapter MUST produce professor candidates from list links and MUST preserve
the yjsjy mentor detail URL as source evidence for each candidate.

#### Scenario: UESTC seed maps to official yjsjy query

- **GIVEN** seed id 26 has department `计算机技术`
- **WHEN** P5 resolves the UESTC replacement source
- **THEN** the source URL uses `yxsh=28&zydm=085404`
- **AND** the resolver result identifies the named UESTC yjsjy adapter

#### Scenario: UESTC yjsjy preview produces candidates

- **GIVEN** a UESTC yjsjy source URL returns mentor list HTML
- **WHEN** a preview or bounded sample run processes the seed
- **THEN** the run records a positive candidate count
- **AND** each sampled candidate has a source URL under
  `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/`
- **AND** the pipeline run does not end as `fetch_blocked`

### Requirement: SZU CSSE official replacement gate

Seed id 5 MUST be remediated only through an official reachable SZU or CSSE
source that returns usable roster entries. If no such source is found, P5 MUST
refresh the blocked diagnostics for the current CSSE URL and keep the seed out
of successful coverage counts.

#### Scenario: SZU CSSE replacement source succeeds

- **GIVEN** an official reachable SZU or CSSE source returns individual CSSE
  professor roster entries
- **WHEN** P5 registers or maps that source
- **THEN** seed id 5 can run through a named adapter with row-level E2E evidence
- **AND** the P5 matrix records success for seed id 5

#### Scenario: SZU CSSE remains blocked

- **GIVEN** the current CSSE URL still returns HTTP 412, browser connection
  close, or an equivalent challenge response
- **AND** no official reachable replacement roster is found
- **WHEN** P5 evidence is assembled
- **THEN** seed id 5 remains `fetch_blocked`
- **AND** the evidence records the current response shape and rejected
  replacement candidates

### Requirement: P5 E2E evidence matrix

P5 MUST NOT be marked complete until `tasks.md`, `acceptance.md`, and
`.agents/runs/prof-blocked-seed-source-remediation/verification.md` contain a
row-level E2E matrix for seed ids 5 and 25-28.

Each E2E row MUST include seed id, original URL, replacement URL when used,
resolver result, trigger mode, command, terminal status, candidate count,
items processed, items failed, pipeline run status, and pipeline issue outcome.

#### Scenario: Completion requires current P5 rows

- **GIVEN** any of seed ids 5, 25, 26, 27, or 28 is absent from the P5 E2E
  matrix
- **WHEN** P5 completion is evaluated
- **THEN** P5 is incomplete

#### Scenario: Artifact updates are required

- **GIVEN** a P5 seed run has completed
- **WHEN** its outcome is used as completion evidence
- **THEN** the corresponding task checkbox is updated in `tasks.md`
- **AND** the requirement evidence is recorded in `acceptance.md`
- **AND** the exact command and result are recorded in
  `.agents/runs/prof-blocked-seed-source-remediation/verification.md`

