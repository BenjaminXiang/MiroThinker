# Verification Contract — unify-data-quality-gating

> Per CLAUDE.md §14.7. Claude-owned. Defines the RED/GREEN boundary before any
> production-code edit. Codex/Superpowers must not independently change the RED
> artifact, the ready criteria, or the enum.
> Re-scoped 2026-06-26 (Epic → Standard) against a fresh read-only
> `miroflow_real` scan. Company cut (0 delta); patent out-of-scope (source-data).

## Change
- **OpenSpec change:** `unify-data-quality-gating` (Standard, behavior-affecting).
- **Capability:** `data-quality-gating` (new).
- **Specs:** `openspec/changes/unify-data-quality-gating/specs/data-quality-gating/spec.md`.
- **Tasks:** `openspec/changes/unify-data-quality-gating/tasks.md`.
- **Grounding:** paper ready-worthy-but-not-`ready` = **66** (write-path `CASE` bypass; all have `summary_zh` ≥ 150 → backfill ran); company 0 (6,514/6,514 already ready); patent 0 ready but out-of-scope (`patent_type` NULL source-data defect, owned by `infer-patent-type-from-patent-number`).

## Change Type
- `deterministic_module`

Behavior-affecting **at the retrieval boundary** (paper write-path `quality_status` → Milvus indexability), but the **new code surface is deterministic**: a pure `gating_contract` module, a paper-writer rewire (replace inline `CASE` with `evaluate_paper_promotion`), and a batch-module refactor (delegate + add `evaluate_patent`). No LLM, no network. The paper ready criteria, the enum, and thresholds are **reused unchanged**.

## Superpowers Mode
- `full_tdd_allowed`

Per §14.7: deterministic module → full Superpowers TDD, RED = unit/contract tests. NOT agentic-RAG/badcase work. TDD must NOT alter the ready criteria, the enum, or threshold values.

## RED artifact (must fail before implementation)
Unit/contract tests, written first, all failing:

1. `tests/data_agents/quality/test_gating_contract.py::test_normalize_quality_status` — legacy `incomplete`/`shallow_summary` → `needs_review`; no value outside the 6-value enum is producible.
2. `test_promote_monotonic` — `ready` held at `ready` unless `admin_action` degrades; promotes upward otherwise; never auto-degrades `ready`.
3. `test_is_indexable_parity` — `is_indexable(quality_status, identity_status)` agrees with `_is_indexable_paper` (and per-domain `_is_indexable_*`) on a ready / needs_enrichment / rejected / merged fixture.
4. `tests/data_agents/paper/test_canonical_writer.py` (extend) — contract: the writer computes `quality_status` via `evaluate_paper_promotion` (not an inline `CASE`); a ready-worthy paper (title+year+venue+authors+abstract+non-boilerplate summary_zh) → `ready`; a `rejected` row stays `rejected`.
5. `tests/data_agents/quality/test_promotion_rules.py` (extend) — parity: batch `promotion_rules` and the write path return identical `quality_status` for representative fixtures across all four domains; `evaluate_patent` exists and delegates to `patent/quality_promotion.py`.

#1–#3 are the live RED (new `gating_contract.py`). #4–#5 are the contract RED (paper rewire + batch reconcile).

## Oracle Strength
- Observable: exact enum normalization; exact forward-monotonic verdicts; exact `is_indexable` parity; the contract end-states (`ready`-worthy → `ready`; `rejected` stays `rejected`; batch==write).
- Stronger than a snapshot: the monotonic guard covers the ready-degradation invariant; the parity test guards the load-bearing "single source of truth" invariant.
- Complementary real check: the `miroflow_real` dry-run (66-row delta; 0 ready degraded) + catch-up Milvus rebackfill retrieval spot-check.

## GREEN
Minimal implementation that turns RED green, no weakening:
- NEW `src/data_agents/quality/gating_contract.py` — `normalize_quality_status`, `promote_monotonic(current, proposed, *, admin_action=None)`, `is_indexable(quality_status, identity_status=None)`.
- UPGRADE `paper/canonical_writer.py` — replace the inline `CASE` (`:113-123`) with `evaluate_paper_promotion(...)`; remove the `CASE`.
- REFACTOR `quality/promotion_rules.py` — delegate to per-domain state machines; add `evaluate_patent`.
- ADD a rebackfill hook entry point (reuses `run_milvus_backfill.py`) invoked after a write-path `ready` transition.
- No migration; no change to ready criteria, enum, thresholds, `_is_indexable_*` logic, A–G, `_VALID_DOMAINS`, or evidence shape.

## Real-interaction / acceptance evidence (not RED; required for acceptance.md)
- **Dry-run (task 5.1)**: unset the 6 proxy env vars, run a read-only dry-run on `miroflow_real` computing each paper's `quality_status` under the unified gate; save `paper-dryrun-<date>.jsonl` (`id / old_status / new_status`).
- **Hard gate (task 5.2)**: assert **0 `ready` papers degraded**. Expected delta: ~66 `needs_enrichment` → `ready`. If any `ready` degrades, STOP.
- **Bounded apply (task 5.3)**: promotion-only transitions (each with `run_id`); re-assert 0 ready degraded.
- **Catch-up Milvus rebackfill (task 5.4)**: `run_milvus_backfill.py` for `paper_chunks`; spot-check ≥10 newly-`ready` papers retrievable; a demoted/excluded row no longer returns.

## Acceptance contract — maps to `acceptance.md`
- Spec contract: normalize + monotonic + is_indexable parity (RED #1–#3).
- Writer contract (paper): `evaluate_paper_promotion` wired; `CASE` gone (grep); `rejected` stays `rejected`; professor/patent unchanged (RED #4).
- Batch/parity: `promotion_rules` delegates; `evaluate_patent` exists; batch==write (RED #5).
- Retrieval: dry-run 0 ready degraded (~66 → ready); catch-up rebackfill; ≥10 newly-ready retrievable.
- Code quality: no migration; no threshold/enum change; pytest green; lint clean.
- `openspec validate unify-data-quality-gating --strict` exits 0.

## Verification commands
- RED: `cd apps/miroflow-agent && uv run pytest tests/data_agents/quality/test_gating_contract.py -n0` (fail until 1.2).
- GREEN: `cd apps/miroflow-agent && uv run pytest tests/data_agents/quality/ tests/data_agents/paper/test_canonical_writer.py -n0`.
- Regression: `cd apps/miroflow-agent && uv run pytest tests/data_agents/paper/ tests/data_agents/quality/ -n0`.
- Grep gate: `grep -Rn "CASE WHEN" apps/miroflow-agent/src/data_agents/paper/canonical_writer.py` returns no `quality_status` assignment.
- Dry-run (real): `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy no_proxy NO_PROXY && cd apps/miroflow-agent && uv run python scripts/run_quality_gate_dry_run.py --dsn "$DATABASE_URL" --domain paper --json-output .agents/runs/unify-data-quality-gating/paper-dryrun-<date>.jsonl` (script to be created if absent).
- Apply (bounded, post-dry-run): `... --apply` then `SELECT count(*) FROM paper WHERE quality_status='ready' AND updated_at > now()-interval '1 day'` (expect ~66 new) and the 0-ready-degraded audit.
- Milvus: `cd apps/miroflow-agent && uv run python scripts/run_milvus_backfill.py` (paper_chunks).
- Validate: `openspec validate unify-data-quality-gating --strict`.

## Do-not rules (Codex)
- Do not modify the `quality_status` enum, any ready criteria, `quality/threshold_config.py` values, `_is_indexable_*` logic, or any alembic migration.
- Do not add a company write-time state machine (cut — 0 delta; 6,514/6,514 already ready).
- Do not touch patent (`patent_type`/0-ready is owned by `infer-patent-type-from-patent-number`).
- Do not remove `apply_identity_gate_reevaluation` (Gap A, separate cleanup).
- Do not auto-rebackfill on every write (operational change is a non-goal); only the hook + one-time catch-up.
- Do not `--apply` without a prior dry-run artifact whose counts are recorded and reviewed.
- Report back per slice with: files changed, test command + pass count, and artifact paths produced.

## Rollback
Reversible — revert the code; `quality_status` reverts to prior values on next write or via the batch `run_quality_promote.py`; the catch-up Milvus rebackfill can be re-run to restore the prior index state. The 66 rows all promote upward (`needs_enrichment` → `ready`), so degradation risk is near-zero; no irreversible migration.
