# Acceptance: unify-data-quality-gating

> Re-scoped 2026-06-26 (Standard; company cut; patent out of scope).

A change is accepted only when ALL of the following hold.

## Spec contract

- [x] `gating_contract.normalize_quality_status` maps legacy values to
      `needs_review`; only the 6-value enum is producible.
- [x] `gating_contract.promote_monotonic` holds `ready` unless admin degrades;
      never auto-degrades `ready`.
- [x] `gating_contract.is_indexable` agrees with every `_is_indexable_*` on a
      ready / needs_enrichment / rejected / merged fixture.

## Writer contract (paper)

- [x] `paper/canonical_writer.py` computes `quality_status` via
      `evaluate_paper_promotion`; the inline `CASE` is gone (grep proof).
- [x] A `rejected` paper row stays `rejected` through the writer.
- [ ] professor and patent writers are unchanged in behavior (patent gate
      already wired at `release.py:251`).

## Batch / parity contract

- [x] `quality/promotion_rules.py` delegates to per-domain state machines;
      `evaluate_patent` exists.
- [x] Parity test passes: batch and write return identical `quality_status`
      across all four domains.

## Retrieval-readiness (the core concern)

- [ ] Dry-run on `miroflow_real`: every paper `quality_status` change recorded
      in `paper-dryrun-<date>.jsonl`.
- [ ] **Hard gate: 0 `ready` papers degraded.** Expected delta: ~66
      `needs_enrichment` → `ready`.
- [ ] After bounded apply + catch-up Milvus rebackfill: ≥10 sampled
      newly-`ready` papers are retrievable; a demoted/excluded row no longer
      returns.

## Code quality / invariants

- [ ] No schema migration; `quality_status` column unchanged.
- [ ] No threshold values changed; no enum change.
- [ ] No secrets logged; no public API / serialized-format change; A–G and
      `_VALID_DOMAINS` untouched; evidence shape unchanged.
- [ ] `uv run pytest` green; `just lint` clean.

## Evidence to report

- Pytest output (unit + contract + parity).
- Grep proof the paper inline `CASE` is removed.
- `paper-dryrun-<date>.jsonl` + "0 ready degraded" assertion output.
- Catch-up rebackfill log + retrieval spot-check results.

## Local sandbox evidence (Codex 2026-06-26)

- `cd apps/miroflow-agent && UV_CACHE_DIR=/home/longxiang/MiroThinker/.uv-cache uv run pytest tests/data_agents/quality/ tests/data_agents/paper/test_canonical_writer.py -n0`
  — 27 passed.
- `cd apps/miroflow-agent && UV_CACHE_DIR=/home/longxiang/MiroThinker/.uv-cache uv run ruff check src/data_agents/quality/ src/data_agents/paper/canonical_writer.py`
  — passed.
- `grep -Rn "CASE WHEN\|quality_status[[:space:]]*=[[:space:]]*CASE" apps/miroflow-agent/src/data_agents/paper/canonical_writer.py`
  — no matches.
- `openspec validate unify-data-quality-gating --strict`
  — exit 0.
