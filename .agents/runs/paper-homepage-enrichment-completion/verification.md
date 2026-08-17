# Verification: paper-homepage-enrichment-completion

Date: 2026-05-15

## TDD Red Checks

- `pytest -n0 apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_happy_path_evidence_source_type_preserves_homepage_tier apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_missing_page_tier_files_pipeline_issue_without_link_write -q`
  failed before implementation because the ingest path emitted the old
  generic page evidence source and did not diagnose missing tier.
- `pytest -n0 apps/miroflow-agent/tests/data_agents/paper/test_enrichment.py apps/miroflow-agent/tests/data_agents/paper/test_quality_promotion.py::test_identifier_contradiction_blocks_ready_promotion apps/miroflow-agent/tests/data_agents/paper/test_quality_promotion.py::test_identifier_contradiction_degrades_ready_to_review -q`
  failed before implementation because identifier contradiction writer
  and quality signals were missing.
- `pytest -n0 apps/miroflow-agent/tests/data_agents/paper/test_milvus_backfill.py::test_backfill_targets_explicit_paper_ids_for_summary_refresh apps/miroflow-agent/tests/scripts/test_run_milvus_backfill.py::test_cli_forwards_target_paper_ids apps/miroflow-agent/tests/scripts/test_run_paper_summary_zh_backfill.py::test_cli_successful_summary_promotes_paper_status -q`
  failed before implementation because targeted paper refresh and
  checkpoint refresh signals were missing.
- `pytest -n0 apps/miroflow-agent/tests/data_agents/paper/test_openalex.py::test_enrich_paper_with_openalex_preserves_doi_and_orcid_authors apps/miroflow-agent/tests/data_agents/paper/test_crossref.py::test_enrich_paper_metadata_from_crossref_by_doi apps/miroflow-agent/tests/data_agents/paper/test_semantic_scholar.py::test_enrich_paper_metadata_from_semantic_scholar_by_doi -q`
  failed before implementation because per-source enrichment helpers did
  not populate structured author and identifier fields.

## Green Checks

- `pytest -n0 apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_happy_path_evidence_source_type_preserves_homepage_tier apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_missing_page_tier_files_pipeline_issue_without_link_write -q`
  returned `5 passed`.
- `pytest -n0 apps/miroflow-agent/tests/data_agents/paper/test_enrichment.py apps/miroflow-agent/tests/data_agents/paper/test_quality_promotion.py -q`
  returned `36 passed`.
- `pytest -n0 apps/miroflow-agent/tests/data_agents/paper/test_milvus_backfill.py::test_backfill_targets_explicit_paper_ids_for_summary_refresh apps/miroflow-agent/tests/scripts/test_run_milvus_backfill.py::test_cli_forwards_target_paper_ids apps/miroflow-agent/tests/scripts/test_run_paper_summary_zh_backfill.py::test_cli_successful_summary_promotes_paper_status -q`
  returned `3 passed`.
- `pytest -n0 apps/miroflow-agent/tests/data_agents/paper/test_openalex.py::test_enrich_paper_with_openalex_preserves_doi_and_orcid_authors apps/miroflow-agent/tests/data_agents/paper/test_crossref.py::test_enrich_paper_metadata_from_crossref_by_doi apps/miroflow-agent/tests/data_agents/paper/test_semantic_scholar.py::test_enrich_paper_metadata_from_semantic_scholar_by_doi -q`
  returned `3 passed`.
- `pytest -n0 apps/miroflow-agent/tests/data_agents/paper apps/miroflow-agent/tests/scripts/test_run_paper_summary_zh_backfill.py apps/miroflow-agent/tests/scripts/test_run_milvus_backfill.py -q`
  returned `330 passed, 1 warning`.
- `pytest -n0 apps/miroflow-agent/tests/data_agents/professor/test_paper_collector.py -q`
  returned `21 passed`.

## Bounded Refresh Sample

The unit path proves the bounded sample without touching a real Milvus
collection:

1. `run_paper_summary_zh_backfill.py` persists `summary_zh` and writes a
   checkpoint row with `milvus_refresh.paper_id`.
2. `run_milvus_backfill.py --domain paper --paper-id PAPER-1` forwards
   `paper_ids={"PAPER-1"}` to `backfill_paper_chunks`.
3. `backfill_paper_chunks(..., paper_ids={"p_target"})` selects only the
   targeted row, deletes prior chunks for that paper id, and inserts a
   refreshed abstract chunk whose `content_text` is the new
   `summary_zh`.
