# Review: correct-paper-tier2-overmerge-view-b

- **change-id:** `correct-paper-tier2-overmerge-view-b` (OpenSpec Lite, spec-driven, Standard)
- **date:** 2026-06-30
- **reviewer:** Claude (designer/reviewer)
- **implementer:** Codex (tasks 1.1–1.3, 2.1); Claude (operational apply #1, #7 review, governance)
- **verdict:** ✅ **ACCEPT** — #1 flipped & verified end-to-end (online retrieval confirms journal now
  retrievable, conference hidden, attribution preserved); #7 resolved as a correct same-work merge
  (no flip); #13 deferred with rationale; Tier-3 DOI-conflict exclusion added (prospective); 14 unit
  tests green; `openspec validate --strict` clean.

## What was done

A post-acceptance audit of `merge-paper-exact-title-duplicates` (applied 2026-06-29, 921 groups /
936 merges) found the title-similarity pilot gate was tautological (candidate SQL groups by exact
title) and missed 13 DOI-conflict groups, of which 7 were conference↔journal over-merges. User
decision: **View B** — a conf/journal-extension pair is one work; keep the journal version as the
visible canonical record, hide the conference version.

DB-grounded re-scan (2026-06-30) narrowed the work to:
- **#1 flipped** (real retrieval gain): conf `PAPER-3E13FAE7D789` (LNCS 2019, was canonical/ready)
  ↔ journal `PAPER-64D7A39FC25B` (JLAMP 2021, was merged/hidden, has arXiv). Journal is now
  canonical/ready/retrievable; conference is hidden.
- **#7 resolved (no flip):** DB abstracts for NYAS 2007 vs CTO 2008 are near-identical (same opening
  sentence, same content, same 5 authors) → same review article published twice → the current merge
  is a correct View-B keep-one. No action.
- **#13 deferred:** neither version ready; journal version lacks abstract → flip has zero retrieval
  impact. Deferred until enriched.
- **#2/#3/#6/#9 no-op:** canonical already the journal `ready` version, conference already hidden.
- **Tier-3 criterion (prospective):** candidate SQL now excludes groups with ≥2 distinct publisher
  DOIs (whitelisting arxiv/ssrn/egusphere preprint prefixes) → future conf↔journal over-merges route
  to Tier-3 review, not auto-merge. Does NOT alter the 921 already-merged groups.

## Acceptance evaluation

### Flip correctness (#1)
- ✅ alias reversed: `PAPER-3E13FAE7D789 → PAPER-64D7A39FC25B`, reason
  `exact_title_dedup_canonical_correction` (wrong-direction alias deleted).
- ✅ journal `confirmed/ready`; conference `merged/rejected`.
- ✅ `prof→journal` link `verified`, `match_reason='homepage_title_resolution'` (**clean, no
  migration suffix** — the contaminated suffix stays on the hidden conference link). **Attribution
  preserved; the "link-contamination hard bone" dissolved under View B as designed.**
- ✅ `_is_indexable_paper`: journal True, conference False.
- ✅ Retrieval candidate SQL includes journal, excludes conference.
- ✅ **Online retrieval spot-check** (`/api/chat`, port 18188): query routed `A_paper_profile` →
  journal returned ×3; conference absent. Confirms journal's Milvus chunks are present (pre-merge
  indexing; the merge change did no Milvus delete) and conference is hidden by the Postgres
  `quality_status='rejected'` filter. **No Milvus refresh required.**

### Tier-3 criterion
- ✅ Candidate SQL excludes publisher-DOI-conflict groups; whitelists preprint DOIs. Unit tests:
  conflict group excluded; preprint↔published pair stays eligible. Existing dedup tests still green.

### #7 / #13
- ✅ #7: same-work dual-publication verified (near-identical abstracts + identical 5-author list) →
  current merge correct; no flip.
- ✅ #13: deferral rationale recorded.

### Invariants
- ✅ No schema/enum/`_is_indexable_paper`/A–G/`_VALID_DOMAINS`/evidence-shape change.
- ✅ `uv run pytest … -n0` → 14 passed (independent Claude re-run); `ruff` clean.
- ✅ `openspec validate correct-paper-tier2-overmerge-view-b --strict` exits 0.

## Codex build review (reconciliation — all met)
- ✅ `flip_paper_canonical`: correct order (delete wrong alias → write corrected → promote journal →
  demote conf → restore journal links → reject conf links); idempotent detect-and-skip; reuses
  `upsert_paper_merge_alias` / `require_real_run_id`.
- ✅ `run_paper_overmerge_flip.py`: stricter `--confirm-real-db` gate (blocks ANY `miroflow_real`
  access); `--group` repeatable; dry-run prints 4-step plan + link disposition; apply calls
  `flip_paper_canonical` + `backfill_paper_chunks`; `run_id` via `open_pipeline_run`/`close_pipeline_run`.
- ✅ Tier-3 SQL clause correct (publisher-DOI count minus preprint whitelist ≤ 1).
- ✅ Milvus client construction copied from `run_milvus_backfill.py` (not invented).

## Operational deviations (acceptable, recorded in evidence.md)
- The apply was run via `flip_paper_canonical` directly (not `run_paper_overmerge_flip.py --apply`),
  because the script's bundled Milvus refresh targets `apps/miroflow-agent/milvus.db`, which is held
  exclusively by the running admin-console backend's milvus-lite subprocess (single-writer). The DB
  flip was applied non-disruptively; the Milvus refresh was **unnecessary** (online spot-check
  confirmed J's chunks present + C hidden). If a future flip's target lacks pre-merge chunks, stop
  the backend and run the script's `--apply`.
- Non-blocking note: `run_paper_overmerge_flip.py` `_resolve_group` uses `LIMIT 1` (assumes 1:1
  conf↔journal per group). Fine for #1; multi-member over-merges (e.g. #2's 3-member group) would
  need extension before flipping them.

## Risks / reversibility
- Flip is reversible (re-run flips back; alias/status/link UPDATEs idempotent). `run_id`-traced.
- Tier-3 clause is prospective (921 merged groups untouched).
- Bounded to 1 group (#1); #7 needs no change; #13 deferred.

## Files
- EDIT `apps/miroflow-agent/src/data_agents/paper/dedup_merge.py` (`flip_paper_canonical` + helpers)
- NEW `apps/miroflow-agent/scripts/run_paper_overmerge_flip.py`
- NEW `apps/miroflow-agent/tests/scripts/test_run_paper_overmerge_flip.py`
- EDIT `apps/miroflow-agent/scripts/run_paper_exact_title_dedup.py` (Tier-3 DOI-conflict exclusion)
- NEW `openspec/changes/correct-paper-tier2-overmerge-view-b/{proposal,specs/paper-dedup/spec,tasks,acceptance}.md`
- NEW `.agents/runs/correct-paper-tier2-overmerge-view-b/{verification-contract,evidence}.md`
- UPDATED `openspec/change-ledger.md` (status → in-verification)
- REVIEW this file
