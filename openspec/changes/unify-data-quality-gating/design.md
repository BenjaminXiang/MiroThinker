# Design: unify-data-quality-gating

> **2026-06-26 re-scope** (read-only `miroflow_real` grounding). Downgraded
> Epic → Standard. Company cut (0 delta). Patent out of scope (source-data
> defect, not gate logic). Deterministic gating modules → unit/contract RED
> (CLAUDE.md §14.7); persisted-status mutation validated by a read-only
> dry-run.

## 1. Measured problem

| Defect | Measured delta | Fix |
|---|---|---|
| **P — paper write-path bypass**: `paper/canonical_writer.py:113-123` uses an inline SQL `CASE`; the real `evaluate_paper_promotion` runs only in `run_paper_summary_zh_backfill.py` | **66** ready-worthy-but-not-`ready` rows (all have `summary_zh` ≥ 150 → backfill ran, bypass bit) | wire `evaluate_paper_promotion` into the writer; remove the `CASE` |
| **R — batch/write divergence**: `quality/promotion_rules.py` re-computes `quality_status` independently; no `evaluate_patent` | latent divergence risk | delegate batch → per-domain state machines; add `evaluate_patent` |
| **M — Milvus freshness**: status changes (the 66, future Phase-3 output) are not reflected in Milvus without a manual rebackfill | the "cleaned but not retrievable" freshness gap | couple write-path `ready` transitions to a rebackfill hook + one-time catch-up |

**Not in scope (grounded):** company (6,514/6,514 already `ready`, 0 delta —
no write-time gate needed); patent (11,408/11,408 `partial` because
`patent_type` is NULL on every row — a source-data defect; the patent gate
`evaluate_patent_promotion` is already wired at `patent/release.py:251` and
returns `partial` correctly given the missing field). These are recorded as
non-goals; a separate patent-sourcing change owns the 0-ready gap.

## 2. Verification surface

| Surface | What it proves | RED artifact |
|---|---|---|
| Unit (pure) | `gating_contract` enum normalization + forward-monotonic + `is_indexable` | unit tests |
| Contract | paper writer calls `evaluate_paper_promotion`; no inline `CASE` (grep) | contract test + grep gate |
| Parity | batch `promotion_rules.py` and write path agree; `evaluate_patent` exists | parity test |
| Retrieval | `_is_indexable_*` == `is_indexable(quality_status, identity_status)` on a fixture | contract test |
| Integration (read-only dry-run) | on `miroflow_real`: 66-row paper delta; **0 `ready` degraded** | dry-run JSONL |
| Operational | catch-up Milvus rebackfill; the 66 promoted papers are retrievable | rebackfill log + retrieval spot-check |

Deterministic at the new-code surface (pure functions; no LLM, no network).
Per §14.7, Superpowers TDD may drive the unit/contract slices; it MUST NOT
alter ready criteria, the enum, or thresholds.

## 3. Oracle strength

- **Strong** for unit/contract/parity/retrieval: pure functions → exact values.
- **Strong** for non-regression: "0 `ready` degraded" is an exact queryable
  invariant.
- **Weaker** for the apply's retrieval effect: spot-check N (≥10) newly-`ready`
  papers are retrievable.

## 4. Affected context / dependencies

- `data_agents/contracts.py::QualityStatus` — enum source of truth (reused).
- `paper/quality_promotion.py::evaluate_paper_promotion` — reused unchanged;
  its signature must accept the writer's row fields.
- `storage/milvus_backfill.py::_is_indexable_*` — unchanged in logic; the
  retrieval invariant asserts they remain the sole indexability signal.
- `scripts/run_quality_promote.py` — batch orchestrator; delegates after
  refactor.
- `professor/quality_gate.py`, `patent/quality_promotion.py` — reused
  unchanged; only their invocation is unified in the batch path.

Mock boundaries: gates are pure → no DB/network mocks at unit level. Dry-run
reads `miroflow_real` read-only (proxy unset); the catch-up rebackfill is the
only mutating step, behind the dry-run's "0 ready degraded" gate.

## 5. Risk and mitigation

- **Risk: paper status mutation changes retrievability.** Mitigation:
  forward-monotonic guard (no `ready` auto-degraded); dry-run-first with the
  "0 ready degraded" hard gate; catch-up rebackfill so retrieval reflects the
  new status. The 66 rows all promote *upward* (`needs_enrichment` → `ready`),
  so degradation risk is near-zero.
- **Risk: removing the inline `CASE` changes `rejected` handling.** Mitigation:
  `evaluate_paper_promotion` already treats `rejected` as terminal; contract
  test asserts `rejected` rows stay `rejected`.

## 6. Retrieval coupling (the core concern)

The change does not auto-rebackfill on every write (separate operational
change, non-goal). It (a) makes the write-path gate the single source of
`quality_status` so indexability is derivable from it, and (b) provides a
rebackfill hook + one-time catch-up so the 66 promoted rows (and the broader
ready set) are actually in the index. This structurally closes "cleaned but
not retrievable" for paper; the operational rebackfill cadence is owned by the
existing `run_milvus_backfill.py` flow.

## 7. Out of scope (restated)

Company write-time gate (0 delta); patent `patent_type` / 0-ready fix
(source-data); enum values; threshold calibration; professor/patent
ready-criteria re-tuning; `apply_identity_gate_reevaluation` dead-code removal;
automated per-write rebackfill; classification A–G; `_VALID_DOMAINS`;
evidence shape.
