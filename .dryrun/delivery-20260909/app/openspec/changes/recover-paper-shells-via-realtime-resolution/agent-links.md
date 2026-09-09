# Agent Links — recover-paper-shells-via-realtime-resolution

> Per CLAUDE.md §14.4.

## Roles (CLAUDE.md §1)
- **Claude (designer/reviewer):** the 2026-06-28 brainstorming + grounding
  (cache_only root cause, 77% empirical test, web research), this OpenSpec
  change, and the operational recovery stages (A/B/C/D — localhost DB + external
  APIs, which Codex sandbox cannot reach) + per-stage review.
- **Codex (implementer):** the small new-code slices — ingest default fix (task
  1.x) + residual marker (task 2.x) + their tests. Sandbox-safe (no network).

## Related changes
- `merge-exact-title-paper-duplicates` (proposed, complementary) — dedup collapses
  46,809 duplicate shells first; recommended order: dedup → recovery (reduces
  Stage A candidates). Recovery also works standalone.
- `unify-data-quality-gating` (landed) — the `ready` gate Stage C uses.
- `infer-patent-type-from-patent-number` (landed) — same "collected but not
  retrievable" pattern; this is the paper analogue at larger scale.

## Skills used
- `superpowers:brainstorming` — drove this change (the user invoked it to
  pressure-test the "shells unrecoverable" conclusion → grounded it to "77%
  recoverable").
- `openspec-propose` — generated this change's artifacts.
- (Stage A operational) — pattern from `infer-patent-type` backfill + retrieval
  spot-check.

## Verification boundary (CLAUDE.md §14.7)
- `.agents/runs/recover-paper-shells-via-realtime-resolution/verification-contract.md`
  (task 0.1): new-code surface deterministic (ingest default + residual marker →
  unit RED); recovery stages operational, verified by pilot yield + dry-run
  counts + retrieval spot-check. Stage A pilot is the yield gate (confirm ~77%
  before full run).

## Dispatch
- Codex: tasks 1.x + 2.x (sandbox-safe new code + tests).
- Claude: tasks 3.x–6.x (operational stages — pilot, full resolution, summary_zh,
  ready+index, residual, retrieval spot-check) + review per stage.
