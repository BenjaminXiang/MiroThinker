# Proposal: thin-decision-persist (Stage 2 pipeline repair, R16 follow-up)

> Implements R15 推论一 as ruled 2026-08-23 and recorded in the p4 data
> rebuild log: split "列值哈希" (cheap storage consistency) from "重建等价"
> (expensive object round-trip). Grounded in the run 9/10 post-mortem:
> 13h freeze inside `canonical_decision_postgres.persist` (55/88 stack
> dumps), no completion path at full volume (~190k decisions for the paper
> batch alone).

## Why

Three over-designed layers in the decision persist path, all audit-grade
leftovers from before the 8-21 出处弱化 ruling:

1. **Per-decision recursive-CTE supersession check**
   (`_require_exact_supersession_heads`): one or two recursive lineage
   queries per decision → 190k-380k recursive queries per batch.
2. **In-transaction full read-back + whole-tree equality** (persist tail):
   `_load_result` rebuilds the entire DecisionBatchResult object graph —
   including `_derive_projections` — inside the write transaction, twice
   (once for the idempotent-replay path, once post-insert), then compares.
3. The same full rebuild runs again on every restart (idempotent replay),
   which is why killed runs could never make forward progress.

## What Changes

1. **Raw-tuple column verification** (R15 ①): after the executemany inserts,
   read back the written tables as RAW tuples (same WHERE scoping the loader
   uses: decisions by release+run, assertions by id set, roles/outcomes by
   decision-id set) and compare as order-insensitive multisets against the
   written rows (Jsonb/datetime normalized). No object construction, no
   Pydantic rebuild. Failure raises with the first differing row as
   evidence (可解释性契约).
2. **Idempotent replay short-circuit**: existing batch → the same raw-tuple
   comparison; equal → return the validated input (equivalent by proof);
   mismatch → replay-conflict error (unchanged semantics, no full load).
3. **Set-based supersession check**: the per-decision recursive CTE becomes
   two batch queries (no-predecessor anti-join + predecessor validation),
   same error conditions, first violating decision named.
4. **Post-commit canary rebuild** (R15 ②): the expensive object-graph
   round-trip moves OUT of the write transaction to a post-commit check on
   a bounded sample (first N=64 decisions; env
   `CANONICAL_V2_DECISION_REBUILD_CHECK=full|canary|off`, default canary)
   — detection stays, rollback-blocking does not.

## Impact

- persist wall time at full volume drops from hours to minutes (read-back
  is raw tuples; supersession is 2 queries).
- `load()`/`load_history()` unchanged (full rebuild stays for readers).
- Semantics preserved: every integrity condition that existed still raises
  the same error classes; only the verification mechanism changes
  (column-multiset compare instead of object-tree equality, inside the
  transaction) and the rebuild-equivalence moves post-commit + sampled.
- Non-goal: decision density reduction (8/object → 1/object) — separate
  data-contract change if needed; run-10 restart itself.

## Evidence hooks

`.agents/runs/thin-decision-persist/verification.md` — PG-backed tests
(46-test baseline file + new thin-persist tests) + a synthetic large-batch
timing comparison.
