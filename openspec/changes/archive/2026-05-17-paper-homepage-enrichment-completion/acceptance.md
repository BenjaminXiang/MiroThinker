# Acceptance: paper-homepage-enrichment-completion

## Spec validation

- [x] `openspec validate paper-homepage-enrichment-completion` exits 0.

## Tier evidence

- [x] Page-declared paper evidence records `prof_homepage_tier2` or
  `prof_homepage_tier3`.
- [x] Missing tier classification is not silently downgraded to a
  generic source label.

## Enrichment

- [x] arXiv participates as the fourth enrichment fallback where
  identifier input is available.
- [x] Author metadata is merged without weakening stronger source
  evidence.
- [x] DOI/arXiv contradictions create open pipeline issues.
- [x] `citation_count` remains OpenAlex-only.

## Summary and Milvus

- [x] `summary_zh` changes are discoverable by the paper Milvus refresh
  path.
- [x] A targeted refresh can re-embed affected paper chunks without
  requiring a full rebuild.
- [x] The clean rebuild order is documented and tested on a bounded
  sample.

## Rebuild order

1. Run page-first ingest to write paper rows and professor-paper links.
2. Run metadata enrichment and paper summary generation.
3. Run paper quality promotion with identifier contradiction signals.
4. Refresh paper vectors with `run_milvus_backfill.py --domain paper
   --paper-id <paper_id>` for checkpointed `milvus_refresh.paper_id`
   values, or run a full paper rebuild when intentionally resetting the
   collection.
5. Run retrieval validation against the refreshed `paper_chunks`
   collection.

## Evidence

- 2026-05-15: Tier evidence RED command failed as expected before
  implementation: `pytest -n0
  apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_happy_path_evidence_source_type_preserves_homepage_tier
  apps/miroflow-agent/tests/data_agents/paper/test_homepage_ingest.py::test_missing_page_tier_files_pipeline_issue_without_link_write
  -q`.
- 2026-05-15: Tier evidence GREEN command passed: same targeted command
  returned `5 passed`.
- 2026-05-15: Enrichment and quality RED command failed as expected
  before implementation: `pytest -n0
  apps/miroflow-agent/tests/data_agents/paper/test_enrichment.py
  apps/miroflow-agent/tests/data_agents/paper/test_quality_promotion.py::test_identifier_contradiction_blocks_ready_promotion
  apps/miroflow-agent/tests/data_agents/paper/test_quality_promotion.py::test_identifier_contradiction_degrades_ready_to_review
  -q`.
- 2026-05-15: Enrichment and quality GREEN command passed: `pytest -n0
  apps/miroflow-agent/tests/data_agents/paper/test_enrichment.py
  apps/miroflow-agent/tests/data_agents/paper/test_quality_promotion.py
  -q` returned `36 passed`.
- 2026-05-15: Summary refresh RED command failed as expected before
  implementation: `pytest -n0
  apps/miroflow-agent/tests/data_agents/paper/test_milvus_backfill.py::test_backfill_targets_explicit_paper_ids_for_summary_refresh
  apps/miroflow-agent/tests/scripts/test_run_milvus_backfill.py::test_cli_forwards_target_paper_ids
  apps/miroflow-agent/tests/scripts/test_run_paper_summary_zh_backfill.py::test_cli_successful_summary_promotes_paper_status
  -q`.
- 2026-05-15: Summary refresh GREEN command passed: same targeted
  command returned `3 passed`.
- 2026-05-15: Source helper completion RED command failed as expected
  before implementation: `pytest -n0
  apps/miroflow-agent/tests/data_agents/paper/test_openalex.py::test_enrich_paper_with_openalex_preserves_doi_and_orcid_authors
  apps/miroflow-agent/tests/data_agents/paper/test_crossref.py::test_enrich_paper_metadata_from_crossref_by_doi
  apps/miroflow-agent/tests/data_agents/paper/test_semantic_scholar.py::test_enrich_paper_metadata_from_semantic_scholar_by_doi
  -q`.
- 2026-05-15: Source helper completion GREEN command passed: same
  targeted command returned `3 passed`.
- 2026-05-15: Paper-domain regression command passed: `pytest -n0
  apps/miroflow-agent/tests/data_agents/paper
  apps/miroflow-agent/tests/scripts/test_run_paper_summary_zh_backfill.py
  apps/miroflow-agent/tests/scripts/test_run_milvus_backfill.py -q`
  returned `330 passed, 1 warning`.
- 2026-05-15: Professor paper collector regression command passed:
  `pytest -n0
  apps/miroflow-agent/tests/data_agents/professor/test_paper_collector.py
  -q` returned `21 passed`.
