## 1. P9 Preflight And Residual-Risk Decision

- [x] 1.1 Confirm `prof-publish-index-refresh` is the active OpenSpec change and no other active change conflicts.
- [x] 1.2 Re-run the P8 post-full quality audit against `miroflow_real`.
- [x] 1.3 Record `p9_readiness`, `p9_blockers`, known field defects, duplicate-risk groups, quality-status distribution, and open issue counts.
- [x] 1.4 Explicitly classify duplicate-risk groups and quality-gate issue counts as P9 blockers or accepted residual risks for this refresh.
- [x] 1.5 Update `acceptance.md` and `.agents/runs/prof-publish-index-refresh/verification.md` with preflight evidence before any refresh.

## 2. Refresh Preflight

- [x] 2.1 Run a dry-run/schema inspection for the Professor split Milvus collections.
- [x] 2.2 Select and record the exact Milvus URI for the P9 refreshed artifact.
- [x] 2.3 Query `miroflow_real` for the canonical Professor rows that the backfill will read.
- [x] 2.4 Record the expected row count and BRESAR Professor id/title baseline.

## 3. P9 Publish/Index E2E

- [x] 3.1 Run the Professor split-index backfill from `miroflow_real` with rebuild enabled.
- [x] 3.2 Record row counts, processed counts, skipped counts, error counts, duration, and per-collection counts.
- [x] 3.3 Verify the refreshed Milvus artifact contains the expected Professor split collections and counts.
- [x] 3.4 Verify BRESAR, Miha is present in the refreshed index with visible title `助理教授`.
- [x] 3.5 Record skipped operations: canonical duplicate merge, quality-status mass promotion, seed 5 unblock attempt, deletion, schema migration, legacy enriched-jsonl publish, and online RAG domain expansion.

## 4. Retrieval Smoke And P10 Handoff

- [x] 4.1 Run at least one Professor identity retrieval smoke query against the refreshed index.
- [x] 4.2 Run at least one Professor research retrieval smoke query against the refreshed index.
- [x] 4.3 Record whether quality-status filtering is enabled or disabled for each smoke query.
- [x] 4.4 Produce the P10 final validation handoff with remaining risks and required user-facing checks.

## 5. Verification And Archive Readiness

- [x] 5.1 Run targeted tests for Milvus collection definitions, Professor vector text builders, Milvus backfill, and retrieval routing.
- [x] 5.2 Run lint for touched scripts, runtime modules, and tests.
- [x] 5.3 Update `acceptance.md` with per-requirement evidence and final P9 E2E results.
- [x] 5.4 Update `.agents/runs/prof-publish-index-refresh/verification.md` with exact commands, results, skipped checks, and confidence impact.
- [x] 5.5 Mark completed task checkboxes only after their evidence is recorded.
- [x] 5.6 Run `openspec validate prof-publish-index-refresh --strict` and `openspec instructions apply --change prof-publish-index-refresh --json`.
