## 1. P7 Baseline And Candidate Gate

- [x] 1.1 Confirm active OpenSpec state and record that P7 is the only active change.
- [x] 1.2 Run the latest P6 readiness planner against `miroflow_real` and record the full-ready candidate set plus blocked exclusions.
- [x] 1.3 Verify seed 5 is excluded from P7 full execution and record the exclusion reason.
- [x] 1.4 Add baseline/candidate evidence to `acceptance.md` and `.agents/runs/prof-seed-controlled-full-recollection/verification.md`.

## 2. Controlled Full Runner

- [x] 2.1 Add a deterministic P7 controlled full-run helper or script that reads readiness rows and selects only `full_recollection_allowed=true` candidates.
- [x] 2.2 Ensure the helper runs selected seeds in stable seed-id order and emits a tab-separated E2E matrix.
- [x] 2.3 Ensure the helper records excluded non-ready rows, including seed 5, without running them.
- [x] 2.4 Add tests for candidate selection, blocked-row exclusion, stable ordering, and E2E matrix formatting.

## 3. P7 Full E2E Execution

- [x] 3.1 Run the controlled full runner against `miroflow_real`.
- [x] 3.2 Record a row-level matrix for every selected full-run candidate with seed id, adapter, run id, terminal status, failure class, items processed, items failed, issue outcome, and P8 readiness.
- [x] 3.3 Re-run the P6 readiness planner and Professor seed coverage guard after full execution.
- [x] 3.4 Record skipped operations: cleanup, deletion, publish refresh, RAG index refresh, and blocked seed 5 full execution.

## 4. Verification And Artifact Updates

- [x] 4.1 Run targeted tests for P7 helper and existing seed-runner contracts.
- [x] 4.2 Run lint for touched runtime, script, and test files.
- [x] 4.3 Update `acceptance.md` with final P7 E2E matrix and per-requirement evidence.
- [x] 4.4 Update `.agents/runs/prof-seed-controlled-full-recollection/verification.md` with exact commands, results, skipped checks, and confidence impact.
- [x] 4.5 Mark completed task checkboxes only after their evidence is recorded.
- [x] 4.6 Run `openspec validate prof-seed-controlled-full-recollection --strict` and `openspec instructions apply --change prof-seed-controlled-full-recollection --json`.

## 5. P8 Handoff

- [x] 5.1 Produce the P8 post-full quality-validation handoff from the P7 matrix.
- [x] 5.2 Record which full-run rows are ready for P8 quality audit and which rows require remediation.
