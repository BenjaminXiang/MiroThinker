# Change Log: prof-paper-patent-from-page-flow

## 2026-05-21 — close-out refresh and WIP completion

- Refreshed T8.3 evidence against the current `miroflow_real` state:
  43 paper rows, 31 non-empty `summary_zh` rows, 31 `ready` papers,
  and 43 `professor_paper_link` rows.
- Recorded the measured summary distribution for the current bounded
  sample: 23/31 summaries within 200-400 chars, min 172, max 490,
  avg 350.3. The exact 50-row distribution remains unavailable
  because the current DB has only 31 summaries.
- Re-ran the focused paper/patent homepage ingest and summary-backfill
  regression suite; result was `56 passed`.
- Backfilled all 43 live papers into the real Milvus Lite paper
  collection, inserting 78 chunks with 0 paper errors, then confirmed
  direct vector search returns relevant mass-spectrometry paper chunks.
- Confirmed the current cached source-page table has no usable live
  Patents-section sample (`pages_scanned=0`), so live patent-section
  rates and title-only patent canonical behavior remain assigned to
  `patent-page-only-canonical`.
- Marked T8.3 and T8.5 complete as a tasks-complete-not-archived state:
  core implementation and close-out evidence are recorded; strict
  carry-overs remain explicitly assigned to follow-up changes.

## 2026-05-13 — SUSTech profile and paper recovery follow-up

- Investigated the three persisted SUSTech sample professors and confirmed
  that official pages were linked but key profile fields were missing:
  `profile_raw_text`, `profile_summary`, department, and title were absent.
- Added SUSTech official profile layout extraction for `.message-left` /
  `.message-right`, carried `profile_raw_text` through the professor profile
  dataclasses and seed-runner enrichment bridge, and persisted
  `profile_raw_text` plus `profile_summary` in the canonical writer.
- Hardened professor canonical writeback so official profile URL can reuse an
  existing `professor_id` when newly parsed fields change the natural key
  (for example, department changing from missing to present). This prevented
  duplicate professor rows during real SUSTech backfill.
- Repaired homepage publication parsing for SUSTech-style author-list
  fragments and correspondence tails, added commit/rollback handling to the
  homepage paper ingest CLI, and added DOI metadata enrichment plus proxy-safe
  LLM client construction to the paper `summary_zh` backfill CLI.
- Real DB backfill `3899267b-a8d1-4806-a9a4-777282b85788` updated the three
  existing SUSTech professor IDs in place: `3/3` rows now have official raw
  text, profile summaries, department, and title; no duplicate professor rows
  were created for the three official profile URLs.
- Follow-up cleanup demoted three stale empty primary affiliation rows. Each
  repaired SUSTech professor now has exactly one primary affiliation, and that
  primary row carries department and title.
- Real paper recovery moved the SUSTech sample from all verified papers being
  `needs_enrichment` to `26 ready`, `3 partial`, and `1 needs_enrichment`
  across verified links. Seven previously accepted false title fragments were
  marked `rejected`.

## 2026-05-14 — professor profile summary boilerplate repair

- Reclassified `profile_summary` as both user-visible text and professor
  retrieval input. It must be a factual professor profile, not an operator
  note about evidence coverage, retrieval usage, or manual review.
- Added a shared professor summary contract that rejects operator/meta
  boilerplate, extracts factual sentences from official profile text, and lets
  sparse fallback summaries stay short rather than padding with system prose.
- Review follow-up: added a fallback-level meta-language guard for structured
  summary fragments and documented the Milvus scalar metric fallback where
  canonical `NULL` metrics are stored as `0` because Milvus Lite does not
  support nullable scalar fields.
- Updated the professor Milvus backfill path to support repeatable
  `--id <professor_id>` targeting and fixed the professor collection schema for
  real Milvus Lite by removing unsupported nullable integer fields.
- Rewrote the three SUSTech sample professor summaries in `miroflow_real` and
  backfilled those three professor vectors into the real Milvus Lite database.

## 2026-05-13 — verification close-out and follow-up registration

- Updated `openspec/change-ledger.md` from `proposed` to
  `in-verification; carry-over documented` for this change.
- Registered proposed follow-up rows for `paper-pipeline-cleanup`,
  `prof-summary-fields`, `prof-double-milvus-collection`,
  `prof-lifecycle-state`, and `patent-page-only-canonical`.
- Aligned the identity-gate spec text with the implemented module
  locations under `src.data_agents.professor`.
- Attempted the 50-paper `summary_zh` char-distribution check against
  `miroflow_real`; at that point the `paper` table had 0 rows. A later
  real seed sample below wrote paper rows, but `summary_zh` remains 0/31.

## 2026-05-13 — real seed sample E2E + V024 schema alignment

- Ran a bounded real seed sample against `miroflow_real` using SUSTech seed
  `professor_seed.id=9`, selecting 3 professor profiles instead of triggering
  the full 988-profile roster.
- Sample wrote 3 professor rows, 31 paper rows, 31 `professor_paper_link` rows,
  and 31 `paper_full_text` rows. The selected sample had no patent sections, so
  no patent canonical rows or patent links were expected.
- Real paper ingest exposed a V004 check-constraint drift:
  `paper.canonical_source='prof_page_only'` was rejected by
  `ck_paper_canonical_source`.
- Added V024 migration
  `apps/miroflow-agent/alembic/versions/V024_extend_paper_canonical_source_page_flow.py`
  to allow `prof_page_only`, `arxiv`, and `web_search` canonical sources, plus
  `tests/storage/test_v024_migration.py`.
- Applied V024 to `miroflow_real`; verified `alembic_version='V024'`.
- `summary_zh` remains unverified in real data (`31` papers, `0` summaries)
  because LLM credentials were not present in the shell and summary backfill was
  not run.

## 2026-05-12 — quality_status runtime wiring

- Wired paper insert-time `quality_status` initialization through
  `paper.canonical_writer.upsert_paper` and `paper.homepage_ingest`.
- Wired summary backfill to call the boilerplate judge, reject
  boilerplate summaries, and run `evaluate_paper_promotion` for
  informative summaries.
- Wired patent xlsx release/exact-backfill quality status through
  `evaluate_patent_promotion` semantics, producing `ready` for
  complete xlsx rows and `partial` for xlsx rows with gaps.
- Added red/green fixture-level regression tests. Real seed E2E remains
  environment-gated by missing Milvus/LLM/provider credentials in the
  current shell.
