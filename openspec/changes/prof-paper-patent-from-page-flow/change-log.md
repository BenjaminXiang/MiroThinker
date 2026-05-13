# Change Log: prof-paper-patent-from-page-flow

## 2026-05-13 — verification close-out and follow-up registration

- Updated `openspec/change-ledger.md` from `proposed` to
  `in-verification; carry-over documented` for this change.
- Registered proposed follow-up rows for `paper-pipeline-cleanup`,
  `prof-summary-fields`, `prof-double-milvus-collection`,
  `prof-lifecycle-state`, and `patent-page-only-canonical`.
- Aligned the identity-gate spec text with the implemented module
  locations under `src.data_agents.professor`.
- Attempted the 50-paper `summary_zh` char-distribution check against
  `miroflow_real`; the `paper` table currently has 0 rows, so this
  acceptance item remains data-gated rather than credential-gated.

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
