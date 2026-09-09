## 1. P8 Baseline And Schema Confirmation

- [x] 1.1 Confirm active OpenSpec state and record that P8 is the active change.
- [x] 1.2 Re-read P7 full-run handoff evidence and record the 19 selected seed ids plus blocked seed 5.
- [x] 1.3 Query the current `miroflow_real` Professor schema surfaces used for traceability and confirm the audit does not depend on a `professor.evidence` column.
- [x] 1.4 Inspect the known CUHK(SZ) SDS BRESAR, Miha row and record its current title/source-page status as a P8 remediation candidate.
- [x] 1.5 Add baseline evidence to `acceptance.md` and `.agents/runs/prof-post-full-quality-audit/verification.md`.

## 2. Read-Only Audit Report

- [x] 2.1 Add a deterministic read-only P8 audit helper or script for post-full Professor data.
- [x] 2.2 Ensure the audit validates P7 full-run coverage for the selected seed ids and reports missing/failed rows.
- [x] 2.3 Ensure the audit reports canonical totals, quality-status distribution, run-id coverage, official source-page coverage, primary affiliation coverage, fact coverage, duplicate identity risk, open pipeline issue counts, blocked seed carryover, and P9 readiness classification.
- [x] 2.4 Ensure the audit records known profile-field extraction defects, including the CUHK(SZ) SDS BRESAR, Miha title contamination candidate, without mutating data.
- [x] 2.5 Add tests for report formatting, P7 coverage validation, read-only classification, blocked seed carryover, and known defect tracking.

## 3. P8 Real E2E Execution

- [x] 3.1 Run the P8 audit against `miroflow_real`.
- [x] 3.2 Record the report summary, P7 coverage matrix, quality/source/traceability distributions, open issues, duplicate-risk groups, known defect list, and P9 readiness classification.
- [x] 3.3 Record skipped operations: cleanup, deletion, publish refresh, RAG index refresh, automatic quality-status writes, canonical merges, and seed 5 unblock attempts.
- [x] 3.4 If the audit identifies P9 blockers or remediation candidates, record them without broadening P8 into publish/index work.

## 4. Verification And Artifact Updates

- [x] 4.1 Run targeted tests for the P8 audit helper and existing relevant Professor quality/seed contracts.
- [x] 4.2 Run lint for touched runtime, script, and test files.
- [x] 4.3 Update `acceptance.md` with per-requirement evidence and final P8 E2E results.
- [x] 4.4 Update `.agents/runs/prof-post-full-quality-audit/verification.md` with exact commands, results, skipped checks, and confidence impact.
- [x] 4.5 Mark completed task checkboxes only after their evidence is recorded.
- [x] 4.6 Run `openspec validate prof-post-full-quality-audit --strict` and `openspec instructions apply --change prof-post-full-quality-audit --json`.

## 5. P9 Handoff

- [x] 5.1 Produce the P9 publish/index readiness handoff from the P8 audit.
- [x] 5.2 Record rows or seed groups that require remediation before publish/index work, including unresolved profile-field extraction defects.
