# Proposal: recover-paper-shells-via-realtime-resolution

## Why

The paper domain has **66,578 "shells"** — `prof_page_only` rows with a title but
no abstract/source text → not `ready` → not in Milvus → **not retrievable**. They
are the single largest "collected but not retrievable" gap.

A 2026-06-28 grounding **overturns the earlier "URLs lost / unrecoverable"
conclusion**. The shells are NOT "APIs don't have them"; they are a
**`cache_only` / budget-capped artifact**:

- At ingest, `allow_realtime_resolution` is gated by
  `external_resolution_max_per_professor`; once the per-professor budget is
  exhausted, remaining publications resolve with `cache_only=True`
  (`paper/homepage_ingest.py:2082-2104`). A title not already in the
  `paper_title_resolution_cache` → `resolve_paper_by_title` returns `None` → a
  shell is synthesized **without any realtime API call**.
- Confirmed three ways: (1) **0 shells have a `resolved=False` cache entry**
  (resolution was not tried-and-failed); (2) the budget-cap → `cache_only` path;
  (3) **empirical test**: realtime `resolve_paper_by_title` on a 30-shell sample
  with the professor `author_hint` → **23/30 = 77% hit rate (all via Crossref)**.

So ~77% of shells (≈51k) are recoverable by **running the already-built realtime
resolver at scale** — the resolver is fine; it was just skipped. Extrapolated:
~51k shells → real papers → `ready` → retrievable.

This change is **behavior-affecting** (resolves ~51k shells, generates
`summary_zh`, mutates quality/identity, indexes into Milvus, changes ingest
default) and **Epic** weight (multi-stage, 51k-scale), but **mostly orchestration
of existing, tested scripts** + a small ingest default fix + a residual marker.

## What Changes

1. **Stage A — Realtime re-resolution backfill** (the core): run
   `run_paper_title_enrichment_backfill` over the 66,578 shell `paper_id`s in
   **realtime** mode (not `--cache-only`), Crossref/OpenAlex-polite-pool primary,
   S2/DBLP disabled on rate-limit (429), with a **pilot-first gate** (500-shell
   sample to confirm yield + tune rate-limits). Resolved shells get
   DOI/abstract/identifiers and merge into canonical papers via
   `paper_merge_alias` (the script already does this).

2. **Stage B — `summary_zh`** for the newly-resolved: run
   `run_paper_summary_zh_backfill` (existing) over the new-abstract papers →
   non-boilerplate `summary_zh` (the gate requires it for `ready`).

3. **Stage C — Ready + index**: recovered papers now meet the full `ready`
   criteria → promote via the unified gate; targeted `run_milvus_backfill
   --paper-id-file` for the newly-ready → retrievable.

4. **Stage D — Residual**: the ~23% unresolved shells **stay not-ready** (already
   excluded from retrieval by `_is_indexable_paper`'s `ready` requirement) — a
   bounded, documented residual; **no `summary_zh` fabrication**.

5. **Ingest fix (prevent recurrence)**: make **realtime resolution the default**
   — the per-professor budget cap becomes a safety valve, not the default. When
   `external_resolution_max_per_professor is None`, ingest resolves in realtime
   (no silent `cache_only`), so future ingests don't recreate shells.

Non-goals (deferred):

- **Chase the ~23% residual** (re-crawl homepages for links, web-search→fetch,
  OpenAlex Chinese re-resolution) — separate change; this change accepts the
  residual as bounded.
- **No change to the `quality_status` enum or the paper `ready` criteria** (the
  patent-style gate relaxation is NOT applied here; `summary_zh` stays required).
- **No `summary_zh` fabrication** for shells without source text.
- **The paper duplicate-merge change** (`merge-exact-title-paper-duplicates`) is
  separate and complementary (dedup collapses duplicate shells; this recovers
  the unique shells).
- No change to classification A–G, `_VALID_DOMAINS`, evidence shape, or any
  serialized public format.

## Capabilities

### New Capabilities
- `paper-shell-recovery` — recover `prof_page_only` title-only shells to real,
  retrievable papers via realtime resolution (+ ingest default + residual
  handling).

### Modified Capabilities
<!-- none — shell-recovery behavior not previously in openspec/specs/. -->

## Impact

- **Affected code** (all under `apps/miroflow-agent/`):
  - UPGRADE `src/data_agents/paper/homepage_ingest.py` — realtime-resolution
    default (None-safe): when the cap is `None`, resolve in realtime (do not
    fall through to `cache_only`); the cap is a safety valve.
  - NEW small residual-marker script (e.g. `scripts/run_paper_shell_residual_mark.py`)
    — for shells still `prof_page_only` after Stage A, record them as a bounded
    residual (no fabrication; they remain not-ready).
  - The recovery itself is **orchestration of existing scripts**:
    `run_paper_title_enrichment_backfill`, `run_paper_summary_zh_backfill`,
    `run_quality_promote`, `run_milvus_backfill` — no new resolution/summary logic.
- **Storage**: no migration. `paper`/`paper_merge_alias`/`paper_full_text` reused.
- **Retrieval impact**: ~51k shells → `ready` → indexed in `paper_chunks` →
  retrievable (was 0). Paper `ready` count 23,208 → ~74k.
- **Rollback**: per-stage bounded applies; Stage A writes via
  `paper_merge_alias` (reversible — un-merge); `summary_zh`/`ready` reverts on
  re-evaluation. The ingest default change is a code revert.
