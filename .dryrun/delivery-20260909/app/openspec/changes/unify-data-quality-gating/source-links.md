# Source Links — unify-data-quality-gating

> Per CLAUDE.md §14.3 (touch-to-promote). Legacy docs / code consulted and what
> was extracted into the new `data-quality-gating` capability spec. Quality
> gating behavior previously lived only in code + legacy docs; this change
> baselines it into OpenSpec.

## Consulted legacy sources

- **`docs/Data-Agent-Shared-Spec.md`** — extracted the `quality_status` enum
  contract and the "every row carries structured evidence + run_id" stance; the
  enum values and the evidence/run_id traceability requirements are codified
  here unchanged.
- **`docs/quality-status-compatibility.md`** — extracted the legacy → canonical
  mapping (`incomplete`/`shallow_summary` → `needs_review`); reused verbatim by
  `gating_contract.normalize_quality_status`.
- **`docs/index.md` (术语表 + 2026-06-22 re-baseline)** — extracted the
  retrieval-readiness framing: `quality_status` is the gate that decides whether
  a row is served; the 2026-06-22 counts (professor 1,801/3,387; company
  1,013/1,024; paper 23,183/97,774; patent 1,931/1,931) anchor the
  non-regression claims.
- **`docs/plans/2026-06-22-professor-paper-gap-closure-portfolio.md`** —
  extracted the "collected + cleaned but not retrievable" gap framing (paper
  `ready` 23,183 vs `unverified` 53,165; company write-time gate absent).
- **`docs/audits/company-requirement-code-reconciliation-2026-05-10.md`** —
  extracted the company under-gating finding (no write-time state machine; only
  batch + narrative length).

## Code anchors extracted into the design

- `data_agents/contracts.py:9-20` — `QualityStatus` enum +
  `QUALITY_STATUS_CANONICAL_MAP` (source of truth; reused, not duplicated).
- `data_agents/quality/promotion_rules.py:25-67` — the batch evaluators
  (`evaluate_professor/company/paper`; **no `evaluate_patent`**) to be
  refactored into delegates.
- `data_agents/paper/quality_promotion.py:87` — `evaluate_paper_promotion`
  (6-value, forward-monotonic, boilerplate-aware) reused unchanged in the write
  path.
- `data_agents/paper/canonical_writer.py:113-123` — the inline SQL `CASE` to be
  removed.
- `data_agents/patent/quality_promotion.py:73` — `evaluate_patent_promotion`
  (already called at `patent/release.py:251`); reused, and surfaced in the batch
  system.
- `data_agents/professor/quality_gate.py` — `evaluate_professor_quality`
  (L1/L2/L3, STEM/HSS-aware) reused unchanged.
- `storage/milvus_backfill.py:178-181` — `_is_indexable_paper`
  (`quality_status=='ready'` ∧ `identity_status not in {rejected, merged}`) +
  per-domain `_is_indexable_*` siblings; the retrieval-readiness consumer,
  unchanged in logic.
- `data_agents/quality/threshold_config.py:8-10` — calibration debt note
  (≥200 samples, precision ≥0.95); explicitly a non-goal here.

## What was NOT migrated

- Threshold calibration (stays a separate change).
- `apply_identity_gate_reevaluation` dead-code removal
  (`paper/quality_promotion.py:212-238`, Gap A from the archived W0b change) —
  separate cleanup.
- Professor `PROFESSOR_READY_REQUIRED_RULES` and patent ready criteria — reused
  unchanged, not re-specified.
