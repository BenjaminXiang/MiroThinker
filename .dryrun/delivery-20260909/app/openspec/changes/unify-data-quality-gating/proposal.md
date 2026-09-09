# Proposal: unify-data-quality-gating

> **2026-06-26 re-scope.** Grounded in a read-only `miroflow_real` scan, this
> change is **downgraded from Epic to Standard** and narrowed to where the
> real, measured delta is: the **paper write-path gate** (66 ready-worthy rows
> stuck below `ready`) + **Milvus rebackfill coupling** (so status changes
> become retrievable) + **batch-system reconciliation**. The company write-time
> state machine is **cut** (0 delta: 6,514/6,514 companies are already
> `ready`). Patent is **out of scope** — its 0/11,408 `ready` is a
> `patent_type` source-data defect, not a gate-logic defect (the patent gate
> is already wired and correct). See `change-log.md` for the grounding.

## Why

Quality gating is the **retrieval-readiness switch**: Milvus indexability
filters admit a row iff `quality_status == 'ready'` (plus, for paper,
`identity_status not in {rejected, merged}`). So a row collected + cleaned but
not promoted to `ready` is invisible to `/api/chat`.

A read-only scan of `miroflow_real` (2026-06-26) measured the actual gaps:

| Domain | Ready-worthy but NOT `ready` (gating delta) | Notes |
|---|---|---|
| paper | **66** (all have summary_zh ≥ 150 → backfill ran, write-path bypass bit) | canonical writer uses an inline SQL `CASE`, not `evaluate_paper_promotion` |
| company | **0** | 6,514/6,514 already `ready`; no write-time gate needed now |
| patent | 0 (but 11,408/11,408 are `partial`) | root cause is `patent_type` NULL (source data), **not** the gate — out of scope here |
| professor | n/a | already gated via `quality_gate.py` |

So the gating change's **measured** retrieval delta is **66 paper rows** — a
latent correctness bug, not a mass unlock. The change is worth doing as a
**Standard correctness + retrieval-freshness fix**: it (1) wires the paper
write path to the real state machine so the 66 (and future Phase-3-filled
shells) are promoted at write time, (2) couples status changes to a Milvus
rebackfill so "cleaned → retrievable" actually holds, and (3) reconciles the
two parallel batch/write gating systems so they cannot diverge.

This change is **behavior-affecting** (paper write-path `quality_status`,
hence Milvus indexability) and **Standard** weight.

## What Changes

1. **ADD** capability `data-quality-gating` (baseline + contract in `specs/`):
   the canonical `quality_status` enum, forward-monotonic promotion, the
   write-time-gating invariant, and the **retrieval-readiness invariant**
   (indexable == gate-promoted-`ready`, modulo identity/merge exclusions).

2. **MODIFY** the paper write path: `paper/canonical_writer.py` MUST call
   `evaluate_paper_promotion` instead of the inline SQL `CASE` (the `CASE` is
   removed). This promotes the 66 ready-worthy rows and future Phase-3 output
   at write time.

3. **ADD** Milvus rebackfill coupling: a write-path `quality_status` change to
   `ready` (or out of `ready`) MUST be followed by a Milvus rebackfill so the
   change is retrievable. The change provides the operational hook + a one-time
   catch-up rebackfill for the 66 rows (and confirms the broader ready set is
   indexed). This closes the "cleaned but not retrievable" freshness gap.

4. **RECONCILE** the batch system: `quality/promotion_rules.py` (W13-D2) MUST
   delegate to the per-domain state machines and add `evaluate_patent`, so the
   batch path and write path cannot diverge.

Non-goals (deferred):

- **Company write-time state machine** — cut (0 delta; 6,514/6,514 already
  `ready`). Re-open only if a future ingest produces non-ready companies.
- **Patent `patent_type` / 0-ready fix** — out of scope; that is a source-data
  defect (11,408 rows have NULL `patent_type`), not a gate-logic defect. The
  patent gate (`evaluate_patent_promotion`) is already wired and correct; it
  returns `partial` correctly given the missing `patent_type`. A separate
  patent-sourcing change owns the 0-ready gap.
- **No change to the `quality_status` enum**; no threshold calibration; no
  professor/patent ready-criteria re-tuning; no `apply_identity_gate_reevaluation`
  dead-code removal; no classification A–G / `_VALID_DOMAINS` / evidence-shape
  change.

## Capabilities

### New Capabilities
- `data-quality-gating` — unified write-time quality gating +
  retrieval-readiness invariant (baseline + contract in `specs/`).

### Modified Capabilities
<!-- none — quality gating behavior was not previously in openspec/specs/. -->

## Impact

- **Affected code** (all under `apps/miroflow-agent/`):
  - NEW `src/data_agents/quality/gating_contract.py` — shared enum +
    forward-monotonic primitive + `is_indexable` retrieval-readiness primitive
    (pure, unit-tested).
  - UPGRADE `src/data_agents/paper/canonical_writer.py` — replace inline
    `CASE` with `evaluate_paper_promotion(...)`.
  - REFACTOR `src/data_agents/quality/promotion_rules.py` — delegate to
    per-domain state machines; add `evaluate_patent`.
  - NEW operational hook: a rebackfill entry point invoked after a write-path
    `quality_status` transition (reuses `run_milvus_backfill.py`); a one-time
    catch-up rebackfill for paper `paper_chunks`.
- **Storage**: no migration. Forward-monotonic guard ensures no `ready` paper
  is auto-degraded.
- **Retrieval impact**: after the catch-up rebackfill, the 66 ready-worthy
  papers become retrievable; future Phase-3-filled shells are retrievable at
  write time without waiting for a separate batch promote. A dry-run reports
  the 66-row delta before apply.
- **Rollback**: revert code; `quality_status` reverts on next write or via the
  batch `run_quality_promote.py`. Dry-run → apply artifacts under
  `.agents/runs/unify-data-quality-gating/`.
