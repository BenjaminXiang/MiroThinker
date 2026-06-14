## 1. Current State Baseline

- [x] 1.1 Confirm there are no active OpenSpec changes blocking P6 execution and record the command output.
- [x] 1.2 Run the existing Professor seed adapter coverage guard against `miroflow_real` and record the observed seed ids, coverage states, resolver results, and approved blocked rows.
- [x] 1.3 Query the latest relevant `pipeline_run` and `pipeline_issue` evidence for every observed seed and record the current post-P5 baseline.
- [x] 1.4 Add the initial P6 baseline evidence to `acceptance.md` and `.agents/runs/prof-seed-recollection-readiness/verification.md`.

## 2. Readiness Planner

- [x] 2.1 Implement a deterministic P6 readiness planner/report command that reads the configured database without modifying canonical Professor rows.
- [x] 2.2 Make the planner emit one row per observed `professor_seed` row with seed id, school, department, seed URL, last run status, resolver result, coverage state, latest run/issue reference, recommended next mode, full recollection allowance, and decision reason.
- [x] 2.3 Implement the recommendation rules for `blocked`, `preview`, `sample`, and `full` exactly as specified.
- [x] 2.4 Add unit tests for complete inventory coverage, missing-row failure, blocked seed recommendations, resolver-covered bounded recommendations, and full promotion only after successful sample evidence.

## 3. Bounded E2E Matrix

- [x] 3.1 Run the P6 readiness planner against `miroflow_real` and capture the full row-level matrix.
- [x] 3.2 Run bounded preview E2E for all rows that the planner recommends as `preview`, unless a row has a recorded blocker; capture run id, terminal status, candidate count, items processed/failed, and issue outcome.
- [x] 3.3 Run bounded sample E2E for rows that the planner recommends as `sample` and that are safe to sample; capture run id, terminal status, candidate count, items processed/failed, and issue outcome.
- [x] 3.4 Re-run the P6 readiness planner after bounded E2E and capture the final P6 matrix.

## 4. Verification And Artifact Updates

- [x] 4.1 Run targeted pytest coverage for the planner and existing seed runner contracts.
- [x] 4.2 Run lint for touched scripts, runtime modules, and tests.
- [x] 4.3 Update `acceptance.md` with the final P6 row-level matrix and per-requirement evidence.
- [x] 4.4 Update `.agents/runs/prof-seed-recollection-readiness/verification.md` with exact commands, results, skipped unsafe operations, and confidence impact.
- [x] 4.5 Mark completed task checkboxes only after their evidence is recorded.
- [x] 4.6 Run `openspec validate prof-seed-recollection-readiness --strict` and `openspec instructions apply --change prof-seed-recollection-readiness --json`.

## 5. P7 Handoff

- [x] 5.1 Produce a P7 candidate list from the final P6 matrix: sample candidates, blocked remediation candidates, and any rows eligible for later full confirmation.
- [x] 5.2 Record that destructive cleanup and unbounded full recollection remain skipped in P6 and require a later explicit approval point.
