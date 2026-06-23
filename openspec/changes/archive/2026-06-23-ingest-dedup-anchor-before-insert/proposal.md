## Why

The professor→paper dirty-data scan (2026-06-22) found **25,527 duplicate paper groups** (up to 162 copies of one title). Root cause (investigated 2026-06-23): `homepage_ingest.py`'s global dedup `_find_existing_canonical_homepage_paper` (line 2482) requires **author-overlap** for the title+year path (lines 2510-2519). For a co-authored paper listed on N professor pages, each page synthesizes a different `"ProfName et al."` author string → the author-overlap gate fails → no dedup hit → `upsert_paper` is called per page → N new `paper` rows (with divergent `paper_id` hashes from per-page title-normalization differences). The link-attach-on-dedup-hit machinery (lines 2154-2208) is already in place — it just never fires because the lookup misses.

This is **behavior-affecting** (changes which paper rows get created at ingest). The behavior contract is owned by the new capability `paper-ingest-dedup`.

## What Changes

- **NEW behavior**: `homepage_ingest.py`'s `_find_existing_canonical_homepage_paper` SHALL check a **content anchor** (DOI > arxiv_id > canonical-title+year) **globally** before `upsert_paper`, **without** requiring author-overlap for the title+year path. On a hit, the ingest SHALL link-attach (create a `professor_paper_link`) instead of INSERTing a new `paper` row — the link-attach path (lines 2154-2208) is already in place; the fix makes the lookup hit.
- **Normalization consistency**: the title normalization used by the content-anchor check SHALL match `canonical_writer._build_paper_id`'s title branch (`_WHITESPACE_RE.sub("", title_clean).lower()` + year), so the pre-INSERT check finds rows that INSERT would dedup.

## Capabilities

### New Capabilities
- `paper-ingest-dedup`: the content-anchor dedup contract at ingest (check DOI > arxiv > canonical-title+year globally before INSERT; link-attach on hit).

## Impact

- **Affected code**: `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py` (`_find_existing_canonical_homepage_paper` ~line 2482 — add a title+year-only path without the author-overlap gate).
- **No schema change** (reuses existing `paper`, `professor_paper_link`, `paper_merge_alias`).
- **No public API change**; `run_id` traceability + evidence preserved.

## Non-goals

- Does **not** dedup the existing 25,527 duplicate groups (that is Phase 4 W2e — `duplicate-paper-review-workflow`).
- Does **not** change `canonical_writer.upsert_paper` (already idempotent on `paper_id` via `ON CONFLICT`).
- Does **not** change the same-professor dedup (`_find_existing_linked_paper_for_page_only` — correctly scoped to one professor).
- Does **not** change the title_resolver (that is W1a, Phase 3).
