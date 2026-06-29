# Design: merge-paper-exact-title-duplicates

> Per `openspec/config.yaml` design rules. Reuses the Stage-A-proven merge
> pattern (`upsert_migrated_link` → `upsert_paper_merge_alias` →
> `_reject_old_links` → `_mark_page_only_merged`). Verification = pilot
> dry-run + adversarial title-match + bounded apply.

## 1. Candidate selection (Tier 2)

```sql
-- exact-title groups, single author-list across members, not rejected/merged
WITH g AS (
  SELECT lower(nullif(trim(title_clean::text),'')) t
  FROM paper
  WHERE nullif(trim(title_clean::text),'') IS NOT NULL
    AND coalesce(identity_status,'unverified') NOT IN ('rejected','merged')
  GROUP BY t HAVING count(*) > 1)
SELECT g.t, array_agg(p.paper_id ORDER BY p.paper_id) pids
FROM g JOIN paper p ON lower(trim(p.title_clean)) = g.t
GROUP BY g.t
HAVING count(DISTINCT lower(coalesce(p.authors_display,''))) = 1;
```
Grounded (2026-06-29): **804 groups, 2,135 rows**; sizes {2:326, 3:431, 4:46, 6:1};
**725/804 have ≥1 identifier-bearing member** (canonical pick).

## 2. Canonical pick (deterministic)

For each group, canonical = the member with:
1. a non-null DOI/arXiv/OpenAlex ID (725 groups have one); tie-break:
2. the most populated fields (abstract/summary_zh/venue/year); tie-break:
3. lowest `paper_id` (stable).

## 3. Merge per non-canonical member (reuse Stage-A pattern)

1. **`upsert_migrated_link`** — upsert each `professor_paper_link` of the old
   member onto the canonical (`ON CONFLICT (professor_id, paper_id)` do update;
   preserve `link_status`/evidence; carry `run_id`).
2. **`upsert_paper_merge_alias(old→canonical, reason='exact_title_dedup',
   evidence_source='exact_title+author_list', run_id)`** (public, in
   `storage/postgres/paper_merge_alias.py`).
3. **reject old links** — `UPDATE professor_paper_link SET link_status='rejected',
   rejected_reason='merged_into_canonical:<canonical>', run_id=… WHERE
   paper_id=old AND link_status!='rejected'`.
4. **mark merged** — `UPDATE paper SET identity_status='merged',
   quality_status='rejected', run_id=… WHERE paper_id=old`.

Step 1 BEFORE step 3 (migrate then reject) — preserves attribution.

## 4. Verification surface

| Surface | What it proves | RED/oracle |
|---|---|---|
| Pilot dry-run (50 groups) | group selection + canonical pick + **adversarial title-match** (member title ≈ canonical, sim≥0.99) | 0 false-merges in sample; else STOP |
| Full apply | merge_aliases written + links migrated + 0 ready degraded | exact counts; idempotent via `uq_paper_merge_alias_old_paper` |
| Retrieval | merged rows excluded; canonical links present | spot-check a merged group's links on the canonical |

Deterministic (SQL + the existing merge primitives). The pilot's adversarial
title-match is the false-merge guard (the main risk).

## 5. Risk and mitigation

- **False merge** (two different papers share exact title + author list — rare
  for specific titles, possible for generic). Mitigation: Tier 2 requires
  identical AUTHOR LIST (strong signal) + pilot adversarial title-match +
  `paper_merge_alias` reversible.
- **Attribution loss** (links not migrated before reject). Mitigation: step 1
  (migrate) strictly before step 3 (reject); verify link count on canonical.
- **Re-merge of already-merged** — the candidate SQL excludes
  `identity_status in {rejected,merged}`; `upsert_paper_merge_alias` is
  idempotent (`uq_paper_merge_alias_old_paper`).

## 6. Out of scope (restated)

Tier 3 review (7,923 divergent-author groups — `duplicate-paper-review-workflow`);
enum/`_is_indexable_paper` change; re-resolution; A–G; `_VALID_DOMAINS`; evidence shape.
