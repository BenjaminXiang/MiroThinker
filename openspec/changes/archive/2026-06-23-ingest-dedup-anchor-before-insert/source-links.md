# Source Links — ingest-dedup-anchor-before-insert

Investigated (2026-06-23):
- `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py` — `_find_existing_canonical_homepage_paper` (line 2482, the global dedup with the author-overlap gate at 2510-2519); `_find_existing_linked_paper_for_page_only` (2433, same-prof dedup); the link-attach cascade (2154-2208); `_page_only_reuse_title_key` (2581, the title normalization); `_synthesize_page_only_resolution` (358, the per-prof "ProfName et al." author synthesis).
- `apps/miroflow-agent/src/data_agents/paper/canonical_writer.py` — `upsert_paper` (70-76, idempotent on `paper_id` via ON CONFLICT); `_build_paper_id` (151, the title fallback normalization).
- `apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py` — existing dedup tests (same-prof + mocked canonical; gap: no cross-prof co-authored test).

Extracted: the root cause (author-overlap gate miss for cross-prof co-authored papers); the fix (title+year-only content-anchor path in `_find_existing_canonical_homepage_paper`); the link-attach machinery (already in place, just needs the lookup to hit).
