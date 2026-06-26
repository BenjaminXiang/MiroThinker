# Tasks: unify-data-quality-gating

> Re-scoped 2026-06-26 (Standard; company cut; patent out of scope). Slice
> order follows groups 1 → 6. One active writer (Codex) per slice.

## 1. Verification contract & shared primitive

- [ ] 1.1 Create `.agents/runs/unify-data-quality-gating/verification-contract.md`
      — behavior-affecting but deterministic at the new-code surface; RED =
      unit/contract/parity tests + read-only dry-run; GREEN = tests pass +
      dry-run "0 ready degraded" + catch-up rebackfill; Superpowers TDD may
      drive deterministic slices, MUST NOT alter ready criteria/enum/thresholds.
- [x] 1.2 NEW `src/data_agents/quality/gating_contract.py`:
      `normalize_quality_status` (reuse `QUALITY_STATUS_CANONICAL_MAP`),
      `promote_monotonic(current, proposed, *, admin_action=None)`,
      `is_indexable(quality_status, identity_status=None)`. Pure, no DB.
- [x] 1.3 Unit tests for 1.2 (RED→GREEN): legacy normalization; forward-monotonic
      hold/promote; ready-not-auto-degraded; `is_indexable` parity with
      `_is_indexable_*`.

## 2. Paper write-path gate (Defect P)

- [x] 2.1 Replace the inline `CASE` in `paper/canonical_writer.py:113-123` with
      an `evaluate_paper_promotion(...)` call. Remove the `CASE`.
- [x] 2.2 Contract test: writer calls `evaluate_paper_promotion` and persists
      its return; a `rejected` row stays `rejected`.
- [x] 2.3 Grep gate: no `quality_status` inline `CASE` remains in the paper
      canonical writer.

## 3. Batch reconciliation (Defect R)

- [x] 3.1 Refactor `quality/promotion_rules.py` to delegate
      `evaluate_professor/paper/company` to the per-domain state machines; add
      `evaluate_patent` delegating to `patent/quality_promotion.py`.
- [x] 3.2 Parity test: batch path and write path return identical
      `quality_status` for representative fixtures across all four domains.

## 4. Retrieval-readiness contract + rebackfill coupling (Defect M)

- [x] 4.1 Contract test: on a ready / needs_enrichment / rejected / merged
      fixture, `_is_indexable_*` == `is_indexable(quality_status,
      identity_status)`.
- [ ] 4.2 Add a rebackfill hook entry point invoked after a write-path
      `quality_status` transition into/out of `ready` (reuses
      `run_milvus_backfill.py`); document that `_is_indexable_*` is the sole
      indexability signal.

## 5. Real-data dry-run + catch-up rebackfill

- [ ] 5.1 Read-only dry-run on `miroflow_real` (proxy unset): compute the
      `quality_status` each paper row *would* receive under the unified gate;
      emit `paper-dryrun-<date>.jsonl` with `id / old_status / new_status` for
      every change. Save under `.agents/runs/unify-data-quality-gating/`.
- [ ] 5.2 Hard gate: assert **0 `ready` papers are degraded**. Expected delta:
      ~66 `needs_enrichment` → `ready`. If any `ready` degrades, STOP.
- [ ] 5.3 Bounded `--apply` (promotion-only transitions; each carries
      `run_id`); re-assert 0 ready degraded post-apply.
- [ ] 5.4 Catch-up Milvus rebackfill of `paper_chunks`; spot-check ≥10
      newly-`ready` papers are retrievable via the retrieval service; spot-check
      a demoted/excluded row no longer returns.

## 6. Acceptance, ledger, validate

- [ ] 6.1 Collect evidence: pytest (unit + contract + parity), grep proof,
      `paper-dryrun-<date>.jsonl` + "0 ready degraded", rebackfill log,
      retrieval spot-check.
- [ ] 6.2 Update `openspec/change-ledger.md` status → `in-verification`.
- [ ] 6.3 `openspec validate unify-data-quality-gating --strict` exits 0.
- [ ] 6.4 Claude review against `acceptance.md`; accept / revise / reject.
