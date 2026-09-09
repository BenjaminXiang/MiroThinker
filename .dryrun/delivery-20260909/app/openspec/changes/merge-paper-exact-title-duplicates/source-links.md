# Source Links — merge-paper-exact-title-duplicates

> Per CLAUDE.md §14.3. Grounded 2026-06-29 (post-Stage-A dedup state).

## Grounded counts (2026-06-29)
- Tier 1 (identifier dup groups): **0** (DOI/arXiv/OpenAlex) — DB constraint +
  Phase-2 ingest-dedup enforce identifier uniqueness; no active merge needed.
- Tier 2 (exact-title + single author-list): **804 groups / 2,135 rows**;
  sizes {2:326, 3:431, 4:46, 6:1}; **725/804 have ≥1 identifier-bearing member**.
- Tier 3 (exact-title + divergent authors): ~7,923 groups — ambiguous, review-gated
  (`duplicate-paper-review-workflow`).

## Code anchors (reused)
- `storage/postgres/paper_merge_alias.py:22` — `upsert_paper_merge_alias` (public;
  idempotent via `uq_paper_merge_alias_old_paper`); `:77 resolve_canonical_paper_id`.
- `scripts/run_paper_title_enrichment_backfill.py` — the Stage-A merge pattern:
  `_upsert_migrated_link` (link copy to canonical) → `_write_merge_alias` →
  `_reject_old_links` (`link_status='rejected'`, reason `merged_into_…`) →
  `_mark_page_only_merged` (`identity_status='merged'`, `quality_status='rejected'`).
- `paper/milvus_backfill.py:178-181` — `_is_indexable_paper` excludes
  `identity_status in {rejected,merged}`; alias LEFT JOIN exclusion in candidate SQL.

## What was NOT migrated
- Tier 3 review workflow — `duplicate-paper-review-workflow` (separate, proposed).
- The shell-recovery merges (Stage A, 1,902) — already done by
  `recover-paper-shells-via-realtime-resolution`; this change handles the
  remaining non-shell title-duplicates.
