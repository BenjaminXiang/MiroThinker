# Proposal: correct-paper-tier2-overmerge-view-b

## Why

The Tier-2 auto-merge (`merge-paper-exact-title-duplicates`, applied 2026-06-29, 921 groups / 936
merges) merged exact-title + identical-author-list groups. A post-acceptance content-level audit
found **13 DOI-conflict groups** the title-similarity pilot gate could not catch — the gate was
tautological (candidate SQL groups by exact title, so titles match by construction). Of these,
**7 are conference↔journal over-merges**: two distinct publications (a conference paper and its
journal extension, or two distinct proceedings) sharing an exact title + author list but with
distinct DOIs / years / venues. The merge hid the journal version and left the conference version
as canonical.

User decision (2026-06-30): a conference/journal-extension pair is **one work** (View B) — keep the
**journal** version as the visible canonical record, hide the conference version; retrieval only
needs the journal version. A DB-grounded re-scan narrows the work to **1 flip (group #1, real
retrieval gain)**, **1 human review (#7, may not be an over-merge)**, and a **prospective Tier-3
criterion** that excludes DOI-conflict groups from future Tier-2 auto-merge.

This change is **behavior-affecting** (narrows the Tier-2 candidate criterion; mutates production
`paper` / `paper_merge_alias` / `professor_paper_link` for group #1) and **Standard** weight, but
**bounded** (1 group flip) and **reversible** (alias + status + link UPDATEs are idempotent;
`run_id`-traced). It reuses existing primitives (`upsert_paper_merge_alias`, `require_real_run_id`,
`backfill_paper_chunks`).

## What Changes

1. **ADD** a Tier-2 exclusion: the candidate SQL excludes groups whose live members carry ≥2
   distinct non-null **publisher** DOIs (DOI-conflict). Preprint DOI prefixes
   (`10.48550/arxiv.`, `10.2139/ssrn.`, `10.5194/egusphere-`) are whitelisted so legit
   preprint↔published pairs remain Tier-2. DOI-conflict groups route to Tier-3 review
   (`duplicate-paper-review-workflow`). **Prospective only** — does not alter the 921 already-merged
   groups.

2. **ADD** a canonical-correction (View B) operation: for a confirmed conference↔journal over-merge,
   flip the canonical from conference to journal — reverse the alias, promote the journal
   (`confirmed/ready`), demote the conference (`merged/rejected`), un-reject the journal's intact
   link, reject the conference's (contaminated) link, refresh Milvus. Applied to group #1 only.

3. **DEFER** group #13 (no retrieval impact — neither version ready; journal lacks abstract).
   **HUMAN-REVIEW** group #7 (both journals, different publishers — may be dual-publication vs two
   distinct papers).

Non-goals: no schema/enum/`_is_indexable_paper`/A–G/`_VALID_DOMAINS`/evidence-shape change; no
re-touching of the 921 merged groups; no Tier-3 review implementation (owned by
`duplicate-paper-review-workflow`); no year-span criterion (noisy, deferred).

## Capabilities

### Modified Capabilities
- `paper-dedup` — Tier-2 candidate criterion narrowed (DOI-conflict → Tier-3); canonical-correction flip added.

## Impact

- **Affected code** (`apps/miroflow-agent/`):
  - EDIT `src/data_agents/paper/dedup_merge.py` — add `flip_paper_canonical(...)`.
  - NEW `scripts/run_paper_overmerge_flip.py` — `--dry-run`/`--apply`/`--confirm-real-db`/`--group`.
  - NEW `tests/scripts/test_run_paper_overmerge_flip.py` — fake-conn unit tests.
  - EDIT `scripts/run_paper_exact_title_dedup.py` — Tier-3 DOI-conflict exclusion in candidate SQL.
- **Storage**: no migration. Reuses `paper` / `paper_merge_alias` / `professor_paper_link`.
- **Retrieval**: group #1 journal version becomes retrievable (rank 0), conference hidden. Driven by
  paper status + Milvus chunks (retrieval filters `quality_status='rejected'`).
- **Rollback**: flip is reversible (re-run flips back); alias/status/link UPDATEs idempotent.
