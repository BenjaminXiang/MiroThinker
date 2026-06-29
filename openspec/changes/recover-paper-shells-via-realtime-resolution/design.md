# Design: recover-paper-shells-via-realtime-resolution

> Per `openspec/config.yaml` design rules. The recovery is **mostly orchestration
> of existing, tested scripts**; the new-code surface is small (ingest default +
> residual marker). Verification = per-stage dry-run→bounded-apply + a retrieval
> spot-check (Stage C). Stage A's pilot is the RED/yield-gate.

## 1. Root cause (grounded 2026-06-28)

- Shells are a **`cache_only` / budget-capped artifact**, not "APIs lack them".
- `homepage_ingest.py:2082-2104`: `allow_realtime_resolution = not skip and not
  budget_exhausted`; `resolve_paper_by_title(..., cache_only=not
  allow_realtime_resolution)`. Once the per-professor budget
  (`external_resolution_max_per_professor`) is exhausted, un-cached titles return
  `None` → shell synthesized with **no realtime API call**.
- Confirmed: 0 shells have a `resolved=False` cache entry; empirical realtime
  resolution on a 30-shell sample = **77% hit (Crossref)**.

## 2. Stages (each a dry-run→bounded-apply gate)

| Stage | Tool (existing) | Effect | Gate |
|---|---|---|---|
| **A** re-resolution | `run_paper_title_enrichment_backfill` (`--paper-id-file`, realtime, `--worker-count`, disable S2/DBLP on 429) | ~51k shells → DOI/abstract/identifiers + merge into canonical | **pilot 500 → confirm ~77% yield, tune rate-limits → full run** |
| **B** summary_zh | `run_paper_summary_zh_backfill` (newly-resolved, by Stage-A `run_id` / `--only-missing`) | non-boilerplate `summary_zh` from new abstracts (heavy LLM, ~51k) | spot-check no boilerplate injection |
| **C** ready+index | `run_quality_promote --domain paper` + `run_milvus_backfill --paper-id-file` (targeted) | `ready` → indexed in `paper_chunks` | retrieval spot-check ≥20 self@rank0 |
| **D** residual | (none — they stay not-ready) | ~15k unresolvable shells remain excluded from retrieval | bounded residual documented; no fabrication |

## 3. Verification surface

| Surface | What it proves | RED/oracle |
|---|---|---|
| Pilot (Stage A) | realtime resolution yield on a 500-shell sample; tune rate-limits/workers | yield ≈77% (vs the 30-sample 77%); by-source recorded |
| Stage A dry-run→apply | resolved count, merge_alias writes, 0 ready degraded | exact counts; idempotent re-run via cache |
| Stage B | summary_zh generated only for resolved papers; no boilerplate | sample spot-check |
| Stage C | recovered papers `ready` + retrievable | retrieval spot-check ≥20 |
| Ingest-fix unit | default ingest (cap=None) resolves realtime; explicit cap still honored | fixture: new publication → no shell on default |
| Residual marker | unresolvable shells recorded as bounded residual (not faked) | count + they remain not-ready |

Deterministic at the new-code surface (ingest default + residual marker → unit
tests). The recovery stages are operational (existing scripts) verified by
dry-run yields + retrieval spot-check (the fresh-fetch methodology — real
resolution/summary/indexing, not assumptions).

## 4. Rate-limit / error handling

- Crossref polite pool (`mailto`), OpenAlex polite pool.
- S2/DBLP circuit-breakers: disable on 429 (S2 429'd in the sample); per-source
  retry/backoff.
- `title_resolution_cache` → idempotent; safe to resume.
- Per-stage dry-run→bounded-apply; Stage A pilot before full run.
- 51k-scale: Stage B (summary_zh LLM) is the long pole — batched, rate-limited,
  resumable.

## 5. Sequencing / dependencies

- **Complementary to dedup** (`merge-exact-title-paper-duplicates`): dedup
  collapses 46,809 duplicate shells first → reduces the Stage A candidate set
  (recommended order: dedup → recovery). But recovery also works standalone
  (resolution + merge handles duplicates: identical titles resolve to the same
  canonical, then merge).
- Independent of the gating change (already landed).

## 6. Realistic outcome

- ~51k shells recovered → `ready` → retrievable (was 0). Paper ready 23,208 →
  ~74k.
- ~15k residual accepted (not in APIs) — bounded, documented, not faked.
- Ingest fixed → no new shells.

## 7. Out of scope (restated)

Chase the ~23% residual (re-crawl/web-search); gate/enum change; summary_zh
fabrication; the dedup change (separate); A–G; `_VALID_DOMAINS`; evidence shape.
