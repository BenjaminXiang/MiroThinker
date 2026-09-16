# Verification evidence: thin-decision-persist (Stage 2, R15-推论一)

## ① New tests (3, `test_thin_decision_persist.py`, PG-backed)

- `test_replay_returns_without_full_rebuild` — idempotent replay returns a
  result equal to the input with **zero `_load_result` invocations** (spy).
- `test_tampered_durable_row_fails_replay_closed` — changed content under
  the same release/run raises the replay-conflict error, again **without**
  the object-graph rebuild (the property this slice adds). Physical-row
  corruption is blocked upstream by append-only triggers + FK + terminal-role
  uniqueness (discovered during test design — the schema itself is
  tamper-resistant).
- `test_post_commit_rebuild_check_env_gate` — `CANONICAL_V2_DECISION_REBUILD_CHECK=off`
  skips the post-commit rebuild; `=always` runs it (load-count spy: 0 vs 1).

## ② Pre-existing suites

- `test_canonical_decision_postgres.py` — **46/46 PASS** with the thin path
  (same fixtures, same error contracts; the suite's round-trip/replay/
  rollback tests all exercise the new verification).
- Combined: **49/49 PASS**.
- Lint clean on new code; 2 pre-existing F821s untouched (verified by stash).

## ③ Performance (honest, recorded not gated)

Supersession sub-path A/B on the real candidate DB
(miroflow_candidate_v2_20260819_r1, 2000-decision sample):
- legacy per-decision recursive CTE: 0.19 ms/decision → ~1 min per 190k
- new set-based: 11x faster on that sub-path
- **Negative finding recorded**: supersession was NOT the 13h-freeze
  dominator on current data. The freeze's dominant cost is the
  in-transaction `_load_result` rebuild (full object graph + Pydantic +
  `_derive_projections` over ~190k decisions) — consistent with the
  watchdog signature (write-bytes frozen, CPU in R, stacks in psycopg
  waits inside persist). That code path no longer runs before commit.

Mechanism deltas per batch: 2 full object-graph rebuilds + compares → 0
in-transaction (replaced by raw-tuple multiset verification, O(rows));
1 post-commit rebuild for batches ≤ 5,000 decisions (canary bound);
supersession N+1 recursive queries → 2 batched queries.

## Ops notes

- `CANONICAL_V2_DECISION_REBUILD_CHECK`: `auto` (default; full rebuild
  post-commit for batches ≤ 5,000 decisions) | `always` | `off`.
- PG tests need the four CANONICAL_V2_TEST_* env vars (sibling DB per test);
  baseline DB `miroflow_candidate_v2_pgtest_r1` on :55458.
