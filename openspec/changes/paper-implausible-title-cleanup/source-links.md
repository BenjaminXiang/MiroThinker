# Source Links — paper-implausible-title-cleanup

Legacy/source-of-truth docs consulted for this change:

- `docs/plans/2026-06-16-professor-paper-cleanup-gap-analysis.md` — root cause C2/C3
  (homepage parser capturing non-title text); the "92% garbage title" finding on the
  6/16 sample.
- `docs/plans/2026-06-22-professor-paper-gap-closure-portfolio.md` — Phase 5 / W1b
  (`homepage-parser-boundary-guards`) is the PREVENTION; this change is the REMEDIATION
  of existing garbage.
- `openspec/changes/wire-paper-identity-gate-rejection/` (W0b) — introduces
  `paper-identity-status` + the `is_plausible_paper_title` guard; its
  `decide_identity_status_rejection` defers garbage titles (`no_change` /
  `implausible_title`) to this cleanup step.
- `apps/miroflow-agent/src/data_agents/paper/title_quality.py` —
  `is_plausible_paper_title` (reused unchanged).
- `apps/admin-console/backend/api/domains.py` `PAPER_SELECT_SQL` — the `/paper` list
  query (currently no identity_status filter; not even SELECTed).

Extracted: the `is_plausible_paper_title` guard + the `rejected` identity_status + the
Milvus `{rejected, merged}` exclusion are reused from W0b; this change adds the cleanup
scan (no LLM) + the admin display default-exclusion.
