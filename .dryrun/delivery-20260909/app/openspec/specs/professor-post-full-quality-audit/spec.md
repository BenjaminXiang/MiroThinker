# professor-post-full-quality-audit Specification

## Purpose
TBD - created by archiving change prof-post-full-quality-audit. Update Purpose after archive.
## Requirements
### Requirement: P8 audit report covers post-full Professor data

P8 MUST produce a deterministic audit report after P7 full recollection. The
report MUST include total Professor canonical rows, P7 full-run row coverage,
quality-status distribution, run-id coverage, official source-page coverage,
primary affiliation coverage, fact coverage, duplicate identity risk, open
pipeline issue counts, blocked seed carryover, and P9 readiness classification.

#### Scenario: Report includes core distributions

- **WHEN** the P8 audit runs against `miroflow_real`
- **THEN** the report includes canonical row totals, quality-status
  distribution, run-id coverage, source-page coverage, affiliation coverage,
  fact coverage, and open issue counts

#### Scenario: Blocked seed carryover remains visible

- **WHEN** seed 5 remains blocked after P7
- **THEN** the P8 report records seed 5 as a blocked-source carryover item
- **AND** seed 5 is not counted as P9 publish-ready full-run coverage

### Requirement: P8 validates P7 full-run coverage

P8 MUST validate that every P7 selected seed has a latest successful full
`pipeline_run` with `trigger_mode='full'`, `failure_class='success'`, and
positive item counts. Missing or failed rows MUST be reported as P9 blockers or
remediation candidates.

#### Scenario: All P7 rows have successful full runs

- **WHEN** every P7 selected seed has a latest successful full run
- **THEN** the P8 report records those seed ids as full-run covered
- **AND** the report includes run ids and item counts for each row

#### Scenario: Missing full run blocks P9 readiness

- **WHEN** a P7 selected seed has no successful full run
- **THEN** the P8 report records the seed as not ready for P9
- **AND** the report includes the missing or failed run reason

### Requirement: P8 stays read-only unless re-evaluation is explicit

The default P8 audit MUST be read-only. If quality-status re-evaluation is
executed, it MUST be recorded as an explicit task with before/after
distribution, command, and write count.

#### Scenario: Read-only audit does not mutate data

- **WHEN** the default P8 audit command runs
- **THEN** it does not update Professor rows, source pages, pipeline issues, or
  publish/index collections

#### Scenario: Quality re-evaluation is separately evidenced

- **WHEN** P8 runs quality-status re-evaluation
- **THEN** the command, dry-run or write mode, before distribution, after
  distribution, evaluated count, and written count are recorded

### Requirement: P8 tracks profile-field extraction defects

P8 MUST record and classify profile-field extraction defects found during
post-full spot checks. A known case MUST be included for the CUHK(SZ) SDS
BRESAR, Miha profile page at `https://sds.cuhk.edu.cn/teacher/2238`, where the
current title value is suspected to be contaminated. The expected extracted
title is `助理教授`. The title MUST NOT include reader metadata, navigation
text, education content, research fields, profile summary text, publication
text, or any other non-title section.

#### Scenario: Known CUHK(SZ) SDS title contamination is tracked

- **WHEN** the P8 audit runs against post-P7 Professor data
- **THEN** the report includes the BRESAR, Miha CUHK(SZ) SDS page as a known
  extraction-defect remediation candidate until it is fixed and re-verified
- **AND** P8 does not classify that record as publish-ready while the title
  contamination remains unresolved

#### Scenario: Title contamination repair has regression coverage

- **WHEN** the CUHK(SZ) SDS title extraction defect is repaired
- **THEN** a regression test asserts that the extracted title is exactly
  `助理教授`
- **AND** the test asserts that the title excludes reader metadata, navigation
  text, education content, research fields, profile summary text, and
  publication text

### Requirement: P8 completion updates required artifacts

P8 MUST NOT be marked complete until `tasks.md`, `acceptance.md`, and
`.agents/runs/prof-post-full-quality-audit/verification.md` contain the audit
command, report summary, P7 coverage matrix, skipped operations, verification
commands, and P9 handoff.

#### Scenario: Artifact evidence is complete

- **WHEN** P8 audit and verification finish
- **THEN** the exact commands and results are recorded in the run verification
  file
- **AND** `acceptance.md` records the report summary and P9 handoff
- **AND** `tasks.md` is updated only after evidence exists

### Requirement: P8 known field defects can be rechecked after remediation

The P8 post-full quality audit MUST support rechecking known field-extraction
defects after a remediation change. A known defect MUST remain a P9 blocker
while unresolved and MUST be removed from P9 blockers only when the current
real value matches the expected value and contamination markers are absent.

#### Scenario: Remediated BRESAR title no longer blocks P9

- **WHEN** the P8 audit runs after the BRESAR, Miha title remediation
- **AND** the current title value is exactly `助理教授`
- **AND** no contamination markers are present
- **THEN** the audit marks `cuhk-sds-bresar-title` as resolved
- **AND** the audit no longer includes `field_defect:cuhk-sds-bresar-title`
  in `p9_blockers`

### Requirement: P9 consumes P8 readiness as a preflight gate

Any P9 Professor publish, index, or RAG refresh stage MUST consume the current
P8 post-full quality audit as a preflight gate. The P9 stage MUST preserve the
P8 audit evidence and MUST stop before refresh when P8 reports P9 blockers.

#### Scenario: P9 records the current P8 gate result

- **WHEN** P9 begins
- **THEN** it runs the current P8 post-full audit command
- **AND** it records `p9_readiness`, `p9_blockers`, known field defects, and
  residual risk summaries in P9 acceptance evidence

#### Scenario: P9 stops on P8 blockers

- **WHEN** the current P8 audit reports a non-empty `p9_blockers` list
- **THEN** P9 does not execute publish, index, or RAG refresh commands
- **AND** P9 records the blocking items for remediation

