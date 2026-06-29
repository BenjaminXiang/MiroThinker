# Source Links — recover-paper-shells-via-realtime-resolution

> Per CLAUDE.md §14.3. Grounded 2026-06-28; this change OVERTURNS the earlier
> "shells unrecoverable (URLs lost)" conclusion with empirical evidence.

## Consulted sources
- **2026-06-28 brainstorming + grounding** (this session) — the cache_only root
  cause + 77% empirical recovery (30-shell sample, Crossref). The decisive
  evidence that shells are recoverable, not lost.
- **`docs/plans/2026-06-22-professor-paper-gap-closure-portfolio.md`** — the
  prior (now-corrected) framing of shells as Phase 3 source-acquisition; this
  change supersedes the "W2a fills shells" premise (W2a needs `pdf_url` which
  shells lack; the real lever is realtime re-resolution).
- **Web research (2026-06-28)** — Crossref `query.bibliographic` fuzzy matching
  (gold standard for title→DOI); OpenAlex polite pool + author/institution
  filters; CNKI/Wanfang/CQVIP have **no open API** (so Chinese-not-in-OpenAlex
  papers are the genuine residual).

## Code anchors extracted into the design
- `paper/homepage_ingest.py:2082-2104` — `allow_realtime_resolution` /
  `cache_only` gate; the budget-cap → shell root cause.
- `paper/title_resolver.py:198` — `resolve_paper_by_title(clean_title, *,
  author_hint, ...)` — accepts the professor `author_hint` (already wired at
  `homepage_ingest.py:2096`); the resolver is correct, just was skipped.
- `paper/title_resolver.py:_title_cache_key` / `_normalize_title_for_match` — the
  `paper_title_resolution_cache` key (idempotent re-runs).
- `scripts/run_paper_title_enrichment_backfill.py` — Stage A tool: `--paper-id-file`,
  `--cache-only`, `--worker-count`, `--disable-*-title-search`, imports
  `upsert_paper_merge_alias` (does the merge).
- `scripts/run_paper_summary_zh_backfill.py` — Stage B tool (summary_zh from
  abstracts; derives `pdf_url` from DOI).
- `storage/postgres/paper_merge_alias.py` — merge writer + `resolve_canonical_paper_id`.
- `paper/milvus_backfill.py:178-181` — `_is_indexable_paper` (`ready` ∧
  `identity_status not in {rejected,merged}`); Stage C indexing gate.

## What was NOT migrated
- The ~23% residual recovery (re-crawl/web-search) — separate change.
- The dedup change (`merge-exact-title-paper-duplicates`) — complementary, separate.
- Any gate/enum change or `summary_zh` fabrication — explicitly forbidden.
