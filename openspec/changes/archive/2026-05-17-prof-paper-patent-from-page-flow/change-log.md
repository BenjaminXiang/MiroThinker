# Change Log: prof-paper-patent-from-page-flow

## 2026-05-15 — bounded E2E close-out and operational hardening

- Completed the T8.3 bounded live smoke against `miroflow_real`, local
  Postgres, local Milvus, local Ollama, and the existing embedding
  endpoint. Smoke professor `PROF-7816DD90CFF6` produced 6 paper links,
  5 full-text fetches, 5 summary promotions to `ready`, a successful
  zero-patent branch, and a targeted Milvus refresh with vector-search
  sanity.
- Added V027 to repair drifted real-database
  `professor_paper_link.evidence_source_type` constraints that missed
  the V024 tier evidence labels despite `alembic_version='V024'`.
- Fixed `scripts/run_homepage_paper_ingest.py` to commit successful
  non-dry-run writes and roll back on exceptions.
- Added `scripts/run_homepage_patent_ingest.py` so the patent homepage
  flow has an operator-facing CLI parallel to paper homepage ingest.
- Added targeted `--paper-id` support to
  `scripts/run_paper_summary_zh_backfill.py` for bounded verification
  and repair runs.
- Made the local-LLM summary client proxy-free (`httpx.Client(
  trust_env=False)`) so ambient proxy variables do not break local
  OpenAI-compatible endpoints.
- Loaded the Milvus `paper_chunks` collection before targeted
  delete/insert refreshes to satisfy real Milvus behavior.
- Clarified the cross-domain link `match_reason` contract to include
  `homepage_title_resolution`, which is the implemented reason for
  prof-page declarations that are resolved through title metadata.
- De-scoped the fixed 50-paper summary distribution gate for this
  completion pass because current database rows are disposable
  verification data from earlier collection flows; large-sample
  distribution should run after recollection through the fixed flow.

## 2026-05-13 — verification close-out and follow-up registration

- Updated `openspec/change-ledger.md` from `proposed` to
  `in-verification; carry-over documented` for this change.
- Registered proposed follow-up rows for `paper-pipeline-cleanup`,
  `prof-summary-fields`, `prof-double-milvus-collection`,
  `prof-lifecycle-state`, and `patent-page-only-canonical`. The
  `patent-page-only-canonical` carry-over was later resolved inside
  this change via V026.
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
