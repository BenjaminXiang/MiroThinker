# Design — ingest-dedup-anchor-before-insert

## Root cause (investigated 2026-06-23)

The 162x duplicate is **not** in `canonical_writer.py` (it is idempotent on `paper_id` via `ON CONFLICT`). The gap is in `homepage_ingest.py`'s `_find_existing_canonical_homepage_paper` (line 2482): the global dedup requires **author-overlap** for the title+year path (lines 2510-2519). For a co-authored paper on N professor pages, each page synthesizes a different `"ProfName et al."` author string (via `_synthesize_page_only_resolution`, line 358) → the author-overlap gate fails → no match → `upsert_paper` called per page → N new rows (with divergent `paper_id` hashes from per-page title-normalization differences).

The link-attach-on-dedup-hit machinery (lines 2154-2208) is **already in place** — it just never fires because the lookup misses.

## Fix

Extend `_find_existing_canonical_homepage_paper` (line 2482) to add a **title+year-only content-anchor path** (no author-overlap gate). The existing DOI + arxiv paths are kept. The new path: `WHERE regexp_replace(lower(p.title_clean), '\s+', '', 'g') = %s AND p.year IS NOT DISTINCT FROM %s` (global, no `professor_id` filter, no author-overlap). This reuses the `_page_only_reuse_title_key` normalization (line 2581) — but applied **globally** (not scoped to a professor).

On a hit, the existing cascade (lines 2154-2208) routes to the `elif existing_canonical_paper_id is not None` branch (line 2157) → `_upsert_professor_paper_link` (line 2185) → link-attach, skipping `upsert_paper`. **No new link-attach code needed.**

## Normalization consistency

`canonical_writer._build_paper_id` (line 151) title fallback: `f"title:{_WHITESPACE_RE.sub('', title_clean).lower()}|year:{year or 0}"`. The content-anchor check must use the SAME title normalization. `_page_only_reuse_title_key` (line 2581) uses `regexp_replace(lower(title), '\s+', '', 'g')` — equivalent to whitespace-stripped-lowercased. So the anchor check's title key matches `_build_paper_id`'s title branch. **Verify this equivalence in a test.**

## Test gap (the regression test)

No existing test covers cross-professor co-authored paper reuse (the 162x scenario). The existing tests (`test_homepage_ingest.py`) cover same-professor dedup (Layer A) + mocked canonical hits (Layer B), but NOT the author-overlap-gate miss. The OpenSpec change adds: Prof A's page inserts a page-only row, Prof B's page lists the same paper (slightly different title text), assert Prof B reuses Prof A's `paper_id` via a link instead of INSERTing a new row.

## Risks

- **False-positive dedup**: two different papers with the same title+year (rare for exact title match). Mitigation: the title normalization is exact (whitespace-stripped-lowercased), not fuzzy; + the DOI/arxiv paths take priority.
- **Performance**: the global title+year query (no `professor_id` filter) on 97k rows — should be fast with the existing index; add one if needed.
