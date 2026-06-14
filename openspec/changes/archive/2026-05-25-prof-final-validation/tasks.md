## 1. P10 Preflight

- [x] 1.1 Confirm `prof-final-validation` is the only active OpenSpec change.
- [x] 1.2 Re-run the P8 Professor post-full quality audit against `miroflow_real`.
- [x] 1.3 Record `p9_readiness`, `p9_blockers`, BRESAR known defect status, duplicate-risk groups, quality-status distribution, and open issue counts.
- [x] 1.4 Stop before final validation if the audit reports P9 blockers.
- [x] 1.5 Update `acceptance.md` and `.agents/runs/prof-final-validation/verification.md` with preflight evidence.

## 2. P9 Artifact Verification

- [x] 2.1 Verify `/tmp/p9prof25.db` exists and is opened with `MILVUS_USE_REAL_CLIENT=1`.
- [x] 2.2 Verify `professor_identity_profiles` and `professor_research_profiles` exist and record row counts.
- [x] 2.3 Verify BRESAR identity payload contains `title=助理教授` and `quality_status=needs_enrichment`.
- [x] 2.4 Record that P10 does not rebuild the P9 index unless the artifact is invalid.

## 3. Final Retrieval Validation

- [x] 3.1 Run a BRESAR identity RetrievalService smoke with quality filtering disabled.
- [x] 3.2 Run a BRESAR identity RetrievalService smoke with default quality filtering and record whether BRESAR is hidden.
- [x] 3.3 Run a Professor research RetrievalService smoke and verify it uses `professor_research_profiles`.
- [x] 3.4 Inspect representative returned Professor names for dirty canonical names such as `面包屑`.
- [x] 3.5 Record query text, quality-filter setting, object ids, collection names, retrieval-index labels, titles, and quality statuses.

## 4. API Or Chat Validation

- [x] 4.1 Inspect current admin/API runtime configuration for the Milvus URI and quality-filter settings.
- [x] 4.2 Start or reuse a safe local runtime only if it will not disturb unrelated user processes.
- [x] 4.3 Run a Professor API or chat smoke against the refreshed retrieval configuration, or record why it cannot run.
- [x] 4.4 Record command, URL, response summary, source traceability, blocker, confidence impact, and next command.

## 5. Residual-Risk Decision

- [x] 5.1 Classify duplicate-risk groups as launch blockers or accepted residual risks.
- [x] 5.2 Classify quality-gate issue counts and `needs_enrichment` visibility behavior as launch blockers or accepted residual risks.
- [x] 5.3 Classify dirty canonical names such as `面包屑` as launch blockers or accepted residual risks.
- [x] 5.4 Classify seed 5 carryover and skipped cleanup operations as launch blockers or accepted residual risks.
- [x] 5.5 Produce the final decision table in `acceptance.md`.

## 6. Verification And Archive Readiness

- [x] 6.1 Run targeted tests for any code touched during P10.
- [x] 6.2 Run lint for any Python files touched during P10.
- [x] 6.3 Update `.agents/runs/prof-final-validation/verification.md` with exact commands, results, skipped checks, and confidence impact.
- [x] 6.4 Mark completed task checkboxes only after their evidence is recorded.
- [x] 6.5 Run `openspec validate prof-final-validation --strict` and `openspec instructions apply --change prof-final-validation --json`.
