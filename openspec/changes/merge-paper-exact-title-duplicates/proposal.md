# Proposal: merge-paper-exact-title-duplicates

## Why

Post-Stage-A, the paper table still has **804 high-confidence duplicate groups
(2,135 rows)** — groups where all members share an **exact (case-insensitive)
title AND a single author list** (the crawl-loop / pre-Phase-2 co-authored
cases, e.g. the 162×/114× groups). These are very likely the same real paper
collected as N rows; they should be **1 canonical paper + N
professor_paper_links**. (Tier 1 identifier-anchored dedup is empty — the DB
constraint + Phase-2 ingest-dedup already enforce identifier uniqueness.)

Leaving them split means: split professor attribution (a co-authored paper's
links are spread across N rows), and retrieval/billing counts N rows for one
paper. Merging collapses each group to one canonical with all links re-pointed.

This change is **behavior-affecting** (merges 2,135 rows into 804 canonicals,
mutates `identity_status`/`paper_merge_alias`/`professor_paper_link`) and
**Standard** weight, but **reuses the existing merge primitives** proven in
Stage A (`upsert_paper_merge_alias` + link-migration + `_mark_page_only_merged`
pattern) and is **high-confidence by construction** (exact title + identical
author list).

## What Changes

1. **ADD** a new capability `paper-dedup` (baseline + contract in `specs/`):
   the tiered duplicate-merge strategy (identifier-anchored = Tier 1 [empty,
   enforced by constraint]; exact-title+author-list = Tier 2 [auto-merge];
   exact-title+divergent-authors = Tier 3 [review-gated, owned by the existing
   `duplicate-paper-review-workflow` change]).

2. **Tier 2 auto-merge** (this change): for each of the 804 groups, pick the
   **canonical** = the identifier-bearing member (DOI/OpenAlex/arXiv) if any
   (725/804 groups have one), else the richest (most fields); for every
   non-canonical member: **migrate its `professor_paper_link`s to the
   canonical** (upsert, preserve `link_status`/evidence), then
   `upsert_paper_merge_alias(old→canonical)`, reject the old member's links,
   mark the old member `identity_status='merged'`/`quality_status='rejected'`.

3. **Pilot-first gate**: dry-run on a sample (e.g. 50 groups) → confirm
   group selection + canonical pick + 0 false-merges (adversarial title-match
   check) before the full apply.

Non-goals (deferred):
- **Tier 3** (7,923 exact-title groups with divergent authors) — ambiguous
  (could be same paper with incomplete data OR different papers sharing a
  title); owned by the existing `duplicate-paper-review-workflow` (review-gated,
  not auto-merge).
- No change to the `quality_status` enum, `_is_indexable_paper`, A–G,
  `_VALID_DOMAINS`, evidence shape, or any serialized public format.
- No re-resolution (Stage A already resolved identifier-bearing shells).

## Capabilities

### New Capabilities
- `paper-dedup` — tiered paper duplicate-merge strategy (Tier 1 empty/enforced;
  Tier 2 auto-merge; Tier 3 review-gated).

### Modified Capabilities
<!-- none -->

## Impact

- **Affected code** (under `apps/miroflow-agent/`):
  - NEW `scripts/run_paper_exact_title_dedup.py` — Tier 2 merge backfill
    (candidate SQL + canonical pick + link-migration + merge_alias + mark_merged;
    `--dry-run`/`--apply`/`--limit`/`--json-output`; `run_id`). Reuses
    `storage/postgres/paper_merge_alias.upsert_paper_merge_alias` (public) +
    the link-migration pattern from `run_paper_title_enrichment_backfill`.
  - NEW `src/data_agents/paper/dedup_merge.py` (optional shared helper) —
    `merge_paper_into_canonical(conn, old, canonical, *, run_id, reason)` if
    factoring the link-migration out of the script is cleaner (avoids
    duplicating the upsert-migrated-link SQL).
- **Storage**: no migration. `paper`/`paper_merge_alias`/`professor_paper_link`
  reused.
- **Retrieval**: merged members → `identity_status='merged'` → auto-excluded
  by `_is_indexable_paper` + alias joins; canonical (if ready) already indexed
  — no re-index needed. Net: cleaner professor attribution (links consolidated
  on the canonical); no NEW retrievable papers (these were already in the DB).
- **Rollback**: `paper_merge_alias` is reversible (un-merge: clear alias +
  un-reject links + restore `identity_status`); per-stage bounded apply.
