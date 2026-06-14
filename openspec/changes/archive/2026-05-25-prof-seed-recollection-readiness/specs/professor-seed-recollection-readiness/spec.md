## ADDED Requirements

### Requirement: P6 readiness matrix covers the current Professor seed inventory

P6 MUST produce a deterministic readiness matrix for every current row in the
configured `professor_seed` table before any broad Professor recollection is
started.

Each matrix row MUST include seed id, school, department, seed URL, latest
`last_run_status`, resolver result, coverage state, latest relevant run id when
available, latest relevant issue id or reason when available, recommended next
mode, whether full recollection is allowed, and a decision reason.

The matrix MUST fail P6 completion if any observed seed row is missing from the
matrix or if any row has an unknown recommendation.

#### Scenario: All observed rows are represented

- **WHEN** the P6 readiness planner reads 20 rows from
  `miroflow_real.professor_seed`
- **THEN** the generated matrix contains exactly those 20 seed ids
- **AND** every row includes a deterministic recommendation and decision reason

#### Scenario: Missing row blocks completion

- **WHEN** acceptance evidence omits any seed id observed by the P6 planner
- **THEN** P6 is incomplete
- **AND** `tasks.md`, `acceptance.md`, and
  `.agents/runs/prof-seed-recollection-readiness/verification.md` are not
  allowed to mark the readiness matrix task complete

### Requirement: P6 recommendations use bounded safety rules

The P6 readiness planner MUST assign exactly one recommended next mode for each
seed: `blocked`, `preview`, `sample`, or `full`.

Recommendation rules:

- `blocked`: the seed has approved blocked evidence and no accepted official
  replacement source, or the latest bounded run ended in `fetch_blocked` with no
  accepted remediation.
- `preview`: the seed has a resolver result or registered source path but lacks
  current post-P5 bounded E2E evidence.
- `sample`: the seed has a current successful preview or equivalent diagnostic
  candidate result but lacks post-P5 successful sample evidence.
- `full`: the seed has a named resolver or registered source path and a
  post-P5 successful bounded sample run with no fatal issue.

`full_recollection_allowed` MUST be true only for rows recommended as `full`.

#### Scenario: Approved blocked seed is not promoted

- **WHEN** seed id 5 has approved `fetch_blocked` evidence and no accepted
  official replacement source
- **THEN** its P6 recommendation is `blocked`
- **AND** `full_recollection_allowed` is false
- **AND** the row records the issue id or blocked reason

#### Scenario: Resolver-covered seed starts with bounded mode

- **WHEN** a seed has a resolver result but no post-P5 successful sample run
- **THEN** its P6 recommendation is either `preview` or `sample`
- **AND** `full_recollection_allowed` is false

#### Scenario: Full requires successful sample

- **WHEN** a seed has a post-P5 successful sample run with a named resolver and
  no fatal issue
- **THEN** its P6 recommendation may be `full`
- **AND** the row records the sample run id used as promotion evidence

### Requirement: P6 completion requires bounded E2E evidence and artifact updates

P6 MUST NOT be marked complete until bounded E2E verification has been recorded
for the readiness planner and for the observed seed matrix.

Completion evidence MUST include the exact commands run, the database DSN target
or redacted equivalent, observed seed count, row-level matrix, and any skipped
checks with blocker and confidence impact.

The evidence MUST be recorded in all of:

- `openspec/changes/prof-seed-recollection-readiness/tasks.md`
- `openspec/changes/prof-seed-recollection-readiness/acceptance.md`
- `.agents/runs/prof-seed-recollection-readiness/verification.md`

#### Scenario: Planner command is recorded

- **WHEN** the P6 planner command completes
- **THEN** the command, exit status, observed seed ids, and matrix output are
  recorded in the P6 verification artifacts

#### Scenario: Skipped full run is explicit

- **WHEN** P6 does not execute an unbounded full recollection run
- **THEN** the verification record states that full recollection was skipped
- **AND** the reason is that P6 is a readiness gate and full execution is
  deferred to a later explicit stage

### Requirement: P6 does not perform destructive cleanup or unbounded bulk recollection

P6 MUST NOT truncate tables, delete canonical data, hard-delete seeds, or start
an unbounded bulk recollection run.

Any command that would delete data or run all eligible seeds in `full` mode MUST
require a later explicit OpenSpec change and operator approval.

#### Scenario: Cleanup remains out of scope

- **WHEN** P6 evidence is reviewed
- **THEN** there is no command that truncates, deletes, or bulk-cleans
  Professor data
- **AND** any needed cleanup is listed as a later-stage decision rather than
  executed in P6

