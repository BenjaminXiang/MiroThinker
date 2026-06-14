## 1. Baseline And Root-Cause Evidence

- [x] 1.1 Confirm active OpenSpec state and record that this repair change is active.
- [x] 1.2 Inspect the BRESAR, Miha `miroflow_real` row and record the contaminated title baseline.
- [x] 1.3 Inspect the title extraction and canonical write path to identify where reader metadata enters `profile.title`.
- [x] 1.4 Run targeted sibling searches for title contamination markers in code, tests, and real title values.
- [x] 1.5 Record baseline/root-cause evidence in `acceptance.md` and `.agents/runs/prof-title-contamination-repair/verification.md`.

## 2. Regression Tests

- [x] 2.1 Add a CUHK(SZ) SDS BRESAR fixture regression test that fails while the title is contaminated.
- [x] 2.2 Add title-boundary guard tests for reader metadata markers and profile-section labels.
- [x] 2.3 Add a positive regression test proving bounded compound titles such as `教授，博士生导师` still pass.
- [x] 2.4 Run RED tests and record expected failures before implementation.

## 3. Title Boundary Repair

- [x] 3.1 Implement the smallest shared Professor title guard needed to reject contaminated title candidates.
- [x] 3.2 Update the profile extraction path so reader metadata `Title:` does not bypass the academic-role boundary.
- [x] 3.3 Preserve existing valid extraction behavior for bounded Chinese and English academic titles.
- [x] 3.4 Re-run GREEN tests and record results.
- [x] 3.5 Supersede stale current affiliation variants from the same official source page when a corrected primary title is written.

## 4. Real Data Remediation And E2E

- [x] 4.1 Run the smallest targeted rerun or repair command that updates the BRESAR, Miha real row after the parser fix.
- [x] 4.2 Verify `miroflow_real.professor_affiliation.title` for BRESAR, Miha is exactly `助理教授`.
- [x] 4.3 Re-run the P8 post-full audit and verify `cuhk-sds-bresar-title` is resolved.
- [x] 4.4 Record skipped operations: publish refresh, RAG index refresh, duplicate merge, broad cleanup, deletion, and schema migration.

## 5. Verification And Archive Readiness

- [x] 5.1 Run targeted Professor profile extraction, seed-runner, and P8 audit tests.
- [x] 5.2 Run lint for touched runtime, script, and test files.
- [x] 5.3 Update `acceptance.md` with per-requirement evidence and final E2E results.
- [x] 5.4 Update `.agents/runs/prof-title-contamination-repair/verification.md` with exact commands, results, skipped checks, and confidence impact.
- [x] 5.5 Mark completed task checkboxes only after their evidence is recorded.
- [x] 5.6 Run `openspec validate prof-title-contamination-repair --strict` and `openspec instructions apply --change prof-title-contamination-repair --json`.
