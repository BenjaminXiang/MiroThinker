# Checkpoint: SIGS Paper Collection Slice

Date: 2026-06-09

## Purpose

This checkpoint isolates the current version slice for SIGS official-page
publication collection, parsing, paper-domain ingest, title resolution,
metadata and summary follow-up, rollout reporting, and the DBLP canonical-source
migration.

It is not a full SIGS rollout completion marker. Random-sample write validation,
full SIGS ingest, frontend display validation, and backend retrieval/chat recall
validation remain pending.

## Current External State

- Branch inspected: `main`
- Real database Alembic version: `V040 (head)`
- Full SIGS professor/paper rerun after V040: not run
- Random SIGS sample write rollout after V040: not run
- Read-only SIGS rollout report after V040:
  - Professors: 254 total, 174 ready, 254 with primary page
  - Paper links: 4768 links, 4768 verified, 4768 officially listed
  - Linked papers: 4669 total, 2148 with English abstract, 4 with `summary_zh`
  - Current summary gap: 2144 abstract-bearing linked papers without `summary_zh`
  - Canonical sources: 3299 OpenAlex, 1369 `prof_page_only`, 1 arXiv, 0 DBLP

Because the real DB is already at `V040`, the code checkpoint must include the
linear Alembic migration chain through `V040`. `V040` alone is not standalone:
it depends on `V039`, and the recent chain in this workspace spans `V024` to
`V040`.

## Included Slice

### OpenSpec and run records

- `.agents/runs/sigs-official-publications-to-paper-domain/verification-contract.md`
- `.agents/runs/sigs-official-publications-to-paper-domain/verification.md`
- `.agents/runs/sigs-official-publications-to-paper-domain/checkpoint-sigs-paper-slice.md`
- `openspec/changes/sigs-official-publications-to-paper-domain/.openspec.yaml`
- `openspec/changes/sigs-official-publications-to-paper-domain/proposal.md`
- `openspec/changes/sigs-official-publications-to-paper-domain/design.md`
- `openspec/changes/sigs-official-publications-to-paper-domain/tasks.md`
- `openspec/changes/sigs-official-publications-to-paper-domain/acceptance.md`
- `openspec/changes/sigs-official-publications-to-paper-domain/specs/paper-fulltext-from-prof-page/spec.md`
- `openspec/changes/sigs-official-publications-to-paper-domain/specs/paper-homepage-enrichment-completion/spec.md`
- `openspec/changes/sigs-official-publications-to-paper-domain/specs/sigs-official-publications-to-paper-domain/spec.md`

### SIGS official publication parser and homepage paper bridge

- `apps/miroflow-agent/src/data_agents/professor/homepage_publications.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications_sigs.py`
- `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py`
- `apps/miroflow-agent/scripts/run_homepage_paper_ingest.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest_preprint.py`
- `apps/miroflow-agent/tests/scripts/test_run_homepage_paper_ingest.py`

### Title resolver and provider controls

- `apps/miroflow-agent/src/data_agents/providers/openalex.py`
- `apps/miroflow-agent/tests/data_agents/providers/test_openalex.py`
- `apps/miroflow-agent/src/data_agents/paper/title_resolver.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_title_resolver.py`
- `apps/miroflow-agent/src/data_agents/canonical/paper.py`

### Paper metadata, full-text, summary, and index follow-up

- `apps/miroflow-agent/src/data_agents/paper/models.py`
- `apps/miroflow-agent/src/data_agents/paper/arxiv.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_arxiv.py`
- `apps/miroflow-agent/src/data_agents/paper/crossref.py`
- `apps/miroflow-agent/src/data_agents/paper/semantic_scholar.py`
- `apps/miroflow-agent/src/data_agents/paper/openalex.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_openalex.py`
- `apps/miroflow-agent/src/data_agents/paper/enrichment.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_enrichment.py`
- `apps/miroflow-agent/src/data_agents/paper/full_text_fetcher.py`
- `apps/miroflow-agent/src/data_agents/paper/raw_pdf_store.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_full_text_fetcher.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_raw_pdf_store.py`
- `apps/miroflow-agent/src/data_agents/storage/postgres/paper_full_text.py`
- `apps/miroflow-agent/tests/storage/test_paper_full_text_writer.py`
- `apps/miroflow-agent/scripts/run_paper_summary_zh_backfill.py`
- `apps/miroflow-agent/tests/scripts/test_run_paper_summary_zh_backfill.py`
- `apps/miroflow-agent/src/data_agents/paper/milvus_backfill.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_milvus_backfill.py`
- `apps/miroflow-agent/scripts/run_milvus_backfill.py`
- `apps/miroflow-agent/tests/scripts/test_run_milvus_backfill.py`
- `apps/miroflow-agent/src/data_agents/storage/milvus_collections.py`
- `apps/miroflow-agent/tests/storage/test_milvus_collections.py`
- `apps/miroflow-agent/src/data_agents/professor/vectorizer.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_vectorizer_metrics.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_vectorizer_text_builders.py`

### SIGS rollout report

- `apps/miroflow-agent/scripts/run_sigs_rollout_report.py`
- `apps/miroflow-agent/tests/scripts/test_run_sigs_rollout_report.py`

### Migration baseline required by V040

- `apps/miroflow-agent/alembic/versions/V024_extend_professor_paper_link_tier_evidence.py`
- `apps/miroflow-agent/alembic/versions/V025_add_professor_admin_action.py`
- `apps/miroflow-agent/alembic/versions/V026_allow_page_only_patent_number.py`
- `apps/miroflow-agent/alembic/versions/V027_repair_professor_paper_link_tier_constraint.py`
- `apps/miroflow-agent/alembic/versions/V028_extend_paper_canonical_source_page_flow.py`
- `apps/miroflow-agent/alembic/versions/V029_add_professor_output_summary_fields.py`
- `apps/miroflow-agent/alembic/versions/V030_add_professor_lifecycle_state.py`
- `apps/miroflow-agent/alembic/versions/V031_add_paper_full_text_raw_pdf_provenance.py`
- `apps/miroflow-agent/alembic/versions/V032_add_professor_patent_link_evidence_url.py`
- `apps/miroflow-agent/alembic/versions/V033_add_company_enrichment_product_tables.py`
- `apps/miroflow-agent/alembic/versions/V034_add_company_structured_business_fields.py`
- `apps/miroflow-agent/alembic/versions/V035_add_company_enrichment_batch_ops.py`
- `apps/miroflow-agent/alembic/versions/V036_add_company_team_member_structured_fields.py`
- `apps/miroflow-agent/alembic/versions/V037_add_company_evidence_source_tier.py`
- `apps/miroflow-agent/alembic/versions/V038_allow_company_signal_event_needs_review.py`
- `apps/miroflow-agent/alembic/versions/V039_add_company_upload_hardening_fields.py`
- `apps/miroflow-agent/alembic/versions/V040_allow_dblp_paper_canonical_source.py`
- `apps/miroflow-agent/tests/storage/test_alembic_revision_lineage.py`
- `apps/miroflow-agent/tests/storage/test_v025_migration.py`
- `apps/miroflow-agent/tests/storage/test_v026_migration.py`
- `apps/miroflow-agent/tests/storage/test_v028_migration.py`
- `apps/miroflow-agent/tests/storage/test_v029_migration.py`
- `apps/miroflow-agent/tests/storage/test_v030_migration.py`
- `apps/miroflow-agent/tests/storage/test_v031_migration.py`
- `apps/miroflow-agent/tests/storage/test_v032_migration.py`
- `apps/miroflow-agent/tests/storage/test_v033_migration.py`
- `apps/miroflow-agent/tests/storage/test_v034_migration.py`
- `apps/miroflow-agent/tests/storage/test_v035_migration.py`
- `apps/miroflow-agent/tests/storage/test_v036_migration.py`
- `apps/miroflow-agent/tests/storage/test_v037_migration.py`
- `apps/miroflow-agent/tests/storage/test_v038_migration.py`
- `apps/miroflow-agent/tests/storage/test_v039_migration.py`

## Explicitly Excluded From This Checkpoint

- Admin-console frontend/backend display fixes and chat/retrieval changes.
- Company enrichment, company upload, company news, and company signal changes.
- Professor quality-state, lifecycle, recollection, post-full-audit, and admin
  workbench changes not required by the SIGS paper bridge.
- OpenSpec archive churn outside
  `openspec/changes/sigs-official-publications-to-paper-domain/`.
- Root agent guidance files such as `AGENTS.md` and `CLAUDE.md`.

## Fresh Verification

- `uv run --no-sync pytest tests/data_agents/professor/test_homepage_publications_sigs.py tests/data_agents/professor/test_homepage_publications.py tests/data_agents/paper/test_homepage_ingest.py tests/scripts/test_run_homepage_paper_ingest.py tests/scripts/test_run_paper_summary_zh_backfill.py tests/scripts/test_run_sigs_rollout_report.py tests/data_agents/paper/test_title_resolver.py tests/storage/test_alembic_revision_lineage.py -q -n0 --no-cov`
  - Result: 302 passed.
- `uv run --no-sync pytest tests/data_agents/providers/test_openalex.py tests/data_agents/paper/test_arxiv.py tests/data_agents/paper/test_enrichment.py tests/data_agents/paper/test_openalex.py tests/data_agents/paper/test_full_text_fetcher.py tests/data_agents/paper/test_raw_pdf_store.py tests/data_agents/paper/test_milvus_backfill.py tests/scripts/test_run_milvus_backfill.py tests/storage/test_paper_full_text_writer.py tests/storage/test_milvus_collections.py -q -n0 --no-cov`
  - Result: 132 passed, 3 skipped because `DATABASE_URL_TEST` / `DATABASE_URL` was not set for Postgres integration cases.
- `uv run --no-sync pytest tests/storage/test_alembic_revision_lineage.py tests/storage/test_v025_migration.py tests/storage/test_v026_migration.py tests/storage/test_v028_migration.py tests/storage/test_v029_migration.py tests/storage/test_v030_migration.py tests/storage/test_v031_migration.py tests/storage/test_v032_migration.py tests/storage/test_v033_migration.py tests/storage/test_v034_migration.py tests/storage/test_v035_migration.py tests/storage/test_v036_migration.py tests/storage/test_v037_migration.py tests/storage/test_v038_migration.py tests/storage/test_v039_migration.py -q -n0 --no-cov`
  - Result: 23 passed, 14 skipped because `DATABASE_URL_TEST` / `DATABASE_URL` was not set for Postgres integration cases.
- `uv run --no-sync pytest tests/data_agents/professor/test_vectorizer_metrics.py tests/data_agents/professor/test_vectorizer_text_builders.py tests/storage/test_milvus_collections.py tests/scripts/test_run_milvus_backfill.py -q -n0 --no-cov`
  - Result: 29 passed.
- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync python scripts/run_sigs_rollout_report.py --sample-limit 3`
  - Result: read-only report returned `alembic_version=V040`, `v040_applied=true`, `has_sigs_seed=true`, 254 SIGS professors, 4669 linked papers, 2148 papers with English abstracts, 4 papers with `summary_zh`, and 2144 abstract-bearing summary gaps.

## Pending Before Full SIGS Rollout

- Stage and review this checkpoint slice.
- Commit or otherwise persist the checkpoint before additional DB writes.
- Run random SIGS sample write validation.
- Run institution-scoped SIGS summary backfill only after sample acceptance.
- Refresh paper/professor retrieval indexes.
- Validate frontend detail pages and backend retrieval/chat recall for sampled
  professors and papers.
