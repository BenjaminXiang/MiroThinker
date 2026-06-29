# Verification Contract — recover-paper-shells-via-realtime-resolution

> Per CLAUDE.md §14.7. Claude-owned. Grounded 2026-06-28 (77% empirical recovery;
> cache_only root cause).

## Change
- **OpenSpec:** `recover-paper-shells-via-realtime-resolution` (Epic, behavior-affecting, new capability `paper-shell-recovery`).
- **Tasks:** `openspec/changes/recover-paper-shells-via-realtime-resolution/tasks.md`.

## Change Type
- `deterministic_module` (new code) + `operational` (recovery stages).

New-code surface (ingest default fix + residual marker) is **deterministic** → unit tests. The recovery stages (A/B/C/D) are **operational** — orchestration of existing scripts against the real DB + external APIs — verified by per-stage dry-run yields + a retrieval spot-check. NOT agentic-RAG/badcase work.

## Superpowers Mode
- `full_tdd_allowed` for the deterministic slices (ingest default + residual marker). The operational stages use the **fresh-fetch methodology** (real resolution/summary/indexing, not assumptions) — the Stage A pilot is the yield gate.

## RED artifacts
- Ingest-default unit test: cap=None → realtime (no shell on un-cached title); explicit cap=N → cap honored. None-safe.
- Residual-marker unit test: lists exactly post-Stage-A unresolved shells; does not touch quality_status/summary_zh.

## GREEN
- `homepage_ingest.py`: None-safe realtime default (cap = safety valve).
- `scripts/run_paper_shell_residual_mark.py` (new).
- Recovery = orchestration of `run_paper_title_enrichment_backfill` / `run_paper_summary_zh_backfill` / `run_quality_promote` / `run_milvus_backfill` (existing).

## Stage gates (the acceptance evidence)
- **Stage A pilot**: 200-shell bounded realtime resolution → confirm yield ≈77% (vs 30-sample 77%), tune rate-limits/workers (Crossref/OpenAlex primary; S2/DBLP disabled on 429). STOP if yield << 77%.
- **Stage A full**: resolved count + merge_alias writes; 0 ready degraded; idempotent.
- **Stage B**: summary_zh only for resolved papers; no boilerplate injection (sample).
- **Stage C**: ≥20 newly-recovered papers retrievable (self@rank0/1).
- **Stage D**: residual documented; no fabrication.

## Do-not rules (Codex)
- Do not change the `quality_status` enum or the paper `ready` criteria (no patent-style gate relaxation here).
- Do not fabricate `summary_zh` for shells without source text.
- Do not change A–G / `_VALID_DOMAINS` / evidence shape / any alembic migration.
- Do not run the operational stages (those are Claude's — localhost DB + external APIs).
- Report back per slice: files changed, test pass count.

## Rollback
- Stage A writes via `paper_merge_alias` (un-merge to revert); `summary_zh`/`ready` revert on re-evaluation; ingest default = code revert.
