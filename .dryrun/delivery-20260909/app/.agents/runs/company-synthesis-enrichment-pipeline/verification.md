## Verification Log

### 2026-05-28

Commands run:

- `cd apps/miroflow-agent && uv run pytest tests/data_agents/professor/test_llm_profiles.py -q`
  - Historical result: passed, 13 tests with the `deepseek-v4-flash` baseline.
  - Current result after switching to `deepseek-v4-pro`: passed, 14 tests.

- `cd apps/miroflow-agent && uv run python <hydra-compose-smoke>`
  - Result: passed.
  - Observed provider: `openai`.
  - Observed model: `deepseek-v4-pro`.
  - Observed base URL: `https://api.deepseek.com`.
  - Observed API-key status: not loaded by bare Hydra compose unless `.env` is loaded by the runtime entrypoint; value not logged.

- `openspec validate company-synthesis-enrichment-pipeline --strict`
  - Result: passed.

- `cd apps/miroflow-agent && uv run python <deepseek-openai-sdk-smoke>`
  - First attempt: blocked before API call by inherited SOCKS proxy without `socksio`.
  - Historical retry with `httpx.Client(trust_env=False)`: passed for `deepseek-v4-flash`.
  - Current retry with `httpx.Client(trust_env=False)` and non-thinking mode: passed for `deepseek-v4-pro`.
  - Observed requested model: `deepseek-v4-pro`.
  - Observed response model: `deepseek-v4-pro`.
  - Observed finish reason: `stop`.
  - Observed reasoning output: absent.
  - Observed response excerpt: `DeepSeek V4 Pro OK`.

Skipped:

- Full company enrichment tests and 100-company validation are not part of this documentation/configuration slice yet. They remain listed in `tasks.md` for implementation.

### 2026-05-28 - DeepSeek V4 Pro runtime hardening

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/professor/test_llm_profiles.py tests/llm/test_openai_client_extra_body.py tests/scripts/test_run_company_signal_extract.py -q`
  - Result: passed, 26 tests.
  - Coverage: shared default profile, provider-specific non-thinking extra body, core OpenAI-compatible DeepSeek v4 request body, and company signal LLM client wiring.

- `cd apps/admin-console && uv run --no-sync pytest tests/test_chat_v1.py tests/test_chat_classifier_c_type.py tests/test_chat_classifier_b_g_tune.py -q`
  - Result: passed, 37 tests.
  - Coverage: admin chat synthesis and classifier now use the configured default profile and DeepSeek-compatible non-thinking extra body.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_narrative_backfill.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_source_product_quality_audit.py -q`
  - Result: passed, 55 tests.
  - Coverage: current company enrichment scripts still parse and dispatch after removing hardcoded `gemma4` from their LLM client setup.

- `cd apps/miroflow-agent && uv run python <deepseek-openai-sdk-smoke-via-shared-resolver>`
  - First current run resolved `deepseekv4flash`, revealing an ignored local `.env` override.
  - After correcting local `LLM_PROFILE`, `LOCAL_LLM_MODEL`, and `ONLINE_LLM_MODEL` to `deepseek-v4-pro`, the retry passed.
  - Observed resolved profile: `deepseekv4pro`.
  - Observed requested model: `deepseek-v4-pro`.
  - Observed response model: `deepseek-v4-pro`.
  - Observed base URL: `https://api.deepseek.com`.
  - Observed finish reason: `stop`.
  - Observed reasoning output: absent.
  - Observed response excerpt: `DeepSeek V4 Pro OK`.

Notes:

- Credential values were not printed in any command output.

### 2026-05-28 - Base readiness and detail contract slice

Commands run:

- `cd apps/admin-console && uv run --no-sync pytest tests/test_data_api_quality_status.py -q`
  - RED result before implementation: failed because company detail returned latest snapshot `description` instead of `company.profile_summary`.
  - GREEN result after implementation: passed, 6 tests.

- `cd apps/admin-console/frontend && npm test -- --run src/pages/RecordDetail.test.tsx`
  - RED result before implementation: failed because Products rendered before Basic Information.
  - GREEN result after implementation: passed, 3 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_canonical_import_readiness.py tests/data_agents/company/test_serper_news_connector.py -q`
  - RED result before implementation: canonical readiness helper was missing, and the ordinary Serper query still appended the funding/news tail.
  - GREEN result after implementation: passed, 24 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_import_xlsx.py tests/data_agents/company/test_release.py -q`
  - Result: passed, 8 tests.

- `openspec validate company-synthesis-enrichment-pipeline --strict`
  - Result: passed.

Skipped:

- The full focused company test set, 100-company upload validation, live web stages, touched-company Milvus refresh, and 5180 browser inspection remain pending because this slice only completed the baseline readiness/detail contract groundwork.

### 2026-05-28 - Generic identity query and site adapter slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_serper_news_connector.py::test_build_generic_identity_queries_uses_trusted_names_without_keyword_tails -q`
  - RED result before implementation: failed because `build_generic_identity_queries` was missing.
  - GREEN result after implementation: passed.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_news_ingest.py::test_build_company_select_sql_top200_limits_rank tests/scripts/test_run_company_news_ingest.py::test_fetch_generic_serper_uses_identity_queries_and_records_diagnostics -q`
  - RED result before implementation: failed because company select did not include registered name, aliases, or latest XLSX company name, and `_fetch_generic_serper_identity_records` was missing.
  - GREEN result after implementation: passed, 2 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_serper_news_connector.py tests/scripts/test_run_company_news_ingest.py -q`
  - Result: passed, 49 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_yiou_adapter.py -q`
  - Result: passed, 12 tests.

Skipped:

- Generic ReAct source judgment, generic source-material persistence, and trusted LLM alias extraction remain pending.

### 2026-05-28 - Generic ReAct source judgment slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_generic_source_judgment.py -q`
  - RED result before implementation: failed because `src.data_agents.company.generic_source_judgment` was missing.
  - GREEN result after implementation: passed, 4 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_generic_source_judgment.py tests/data_agents/company/test_serper_news_connector.py tests/scripts/test_run_company_news_ingest.py -q`
  - Result: passed, 53 tests.

Skipped:

- Upload-batch wiring for generic ReAct source material, multi-source fact extraction, and persistence remain pending.

### 2026-05-28 - XLSX product and scenario synthesis slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_source_product_extractor.py::test_xlsx_synthesis_uses_description_business_and_project_as_source_material tests/data_agents/company/test_source_product_extractor.py::test_xlsx_synthesis_does_not_invent_target_customers_from_industry_only -q`
  - RED result before implementation: failed because `synthesize_products_and_scenarios_from_xlsx` was missing.
  - GREEN result after implementation: passed, 2 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_source_product_extractor.py tests/data_agents/company/test_structured_business_models.py -q`
  - Result: passed, 12 tests.

Skipped:

- Upload-batch wiring for the source-material persistence helper remains pending.

### 2026-05-28 - Product, scenario, and source-tier evidence slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_source_product_extractor.py::test_persist_synthesized_products_and_scenarios_uses_upsert_paths_and_quality_gate tests/data_agents/company/test_source_product_extractor.py::test_generic_web_only_products_remain_review_gated_without_strong_judgment -q`
  - RED result before implementation: failed because the persistence helper did not pass `source_tier` to the upsert writers.
  - GREEN result after implementation: passed, 2 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_official_product_capture.py::test_product_evidence_preserves_source_tier tests/data_agents/company/test_official_product_capture.py::test_application_scenario_evidence_preserves_source_tier tests/storage/test_v037_migration.py tests/storage/test_alembic_revision_lineage.py -q`
  - RED result before implementation: failed because upsert writers did not accept `source_tier` and V037 did not exist.
  - GREEN result after implementation: passed, 5 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_source_product_extractor.py tests/data_agents/company/test_structured_business_models.py tests/data_agents/company/test_official_product_capture.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_official_product_capture.py -q`
  - Result: passed, 38 tests.

- `python -m compileall -q apps/miroflow-agent/src/data_agents/company/source_product_extractor.py apps/miroflow-agent/src/data_agents/company/official_product_capture.py apps/miroflow-agent/alembic/versions/V037_add_company_evidence_source_tier.py`
  - Result: passed.

Skipped:

- Upload-batch wiring for this persistence helper remains pending.

### 2026-05-28 - Official-site source material capture slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_official_product_capture.py::test_select_candidate_material_urls_covers_core_official_sections tests/data_agents/company/test_official_product_capture.py::test_extract_official_source_materials_filters_noise_and_marks_high_trust -q`
  - RED result before implementation: failed because official material URL selection and official source-material extraction were missing.
  - GREEN result after implementation: passed, 2 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_official_product_capture.py::test_capture_official_materials_for_record_fetches_core_sections -q`
  - RED result before implementation: failed because `_capture_official_materials_for_record` was missing.
  - GREEN result after implementation: passed, 1 test.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_official_product_capture.py::test_cli_dry_run_report_includes_official_source_materials -q`
  - Result: passed, 1 test.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_official_product_capture.py tests/data_agents/company/test_yiou_adapter.py tests/scripts/test_run_company_official_product_capture.py -q`
  - Result: passed, 31 tests.

- `python -m compileall -q apps/miroflow-agent/src/data_agents/company/source_material.py apps/miroflow-agent/src/data_agents/company/source_product_extractor.py apps/miroflow-agent/src/data_agents/company/official_product_capture.py apps/miroflow-agent/scripts/run_company_official_product_capture.py`
  - Result: passed.

Skipped:

- Upload-batch wiring for official source materials into multi-source synthesis and per-company audit remains pending.

### 2026-05-28 - Team raw LLM structuring slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/company/test_team_parser.py::test_structure_team_raw_with_llm_preserves_raw_and_extracts_evidence_fields tests/company/test_team_parser.py::test_structure_team_raw_without_llm_returns_source_grounded_fallback -q`
  - RED result before implementation: failed because `structure_team_raw_with_llm` was missing.
  - GREEN result after implementation: covered by full team parser run below.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/company/test_team_parser.py -q`
  - Result: passed, 14 tests.

Skipped:

- Persistence of structured team background/highlights/evidence into database fields remains pending.

### 2026-05-28 - Company vector text enrichment slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_vectorizer.py::test_compose_company_text_includes_team_highlights_and_funding_details -q`
  - RED result before implementation: failed because composed vector text omitted team highlights and normalized funding details.
  - GREEN result after implementation: passed.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_vectorizer.py tests/scripts/test_run_milvus_backfill_company.py tests/data_agents/service/test_retrieval_company_patent.py -q`
  - Result: passed, 22 tests.

Skipped:

- Touched-company vector refresh from the upload enrichment runner remains pending.

### 2026-05-28 - Baseline blocker persistence and summary serialization slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py -q`
  - RED result before implementation: failed because `record_baseline_readiness_stage` was missing.
  - GREEN result after implementation: passed, 6 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py -q`
  - RED result before implementation: failed because the upload enrichment runner did not expose or run a `baseline_readiness` stage.
  - GREEN result after implementation: passed, 5 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_release.py -q`
  - RED result before implementation: failed because `CompanyImportRecord` had no synthesized summary fields and release generation could not prefer them.
  - GREEN result after implementation: passed, 4 tests.

- `cd apps/admin-console && uv run --no-sync pytest tests/test_domains_postgres.py -q -k "company_summary or company_quality_status"`
  - RED result before implementation: failed because company summary updates wrote into snapshot fields and `technology_route_summary` fell back to XLSX `business`.
  - GREEN result after implementation: passed, 2 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_canonical_import_readiness.py tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_release.py -q`
  - Result: passed, 19 tests.

- `cd apps/admin-console && uv run --no-sync pytest tests/test_data_api_quality_status.py tests/test_domains_postgres.py -q -k "company"`
  - Result: passed, 16 tests.

Skipped:

- Full upload enrichment stages, live web, 100-company validation, touched-company Milvus refresh, and 5180 browser inspection remain pending.

### 2026-05-28 - Long narrative and technology summary slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_narrative_enrichment.py -q`
  - RED result before implementation: failed because `build_user_prompt` and `generate_company_narrative` accepted only `description`, profile validation still targeted 200-300 characters, and sparse input returned `short_input` instead of a blocker.
  - GREEN result after implementation: passed, 9 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_narrative_enrichment.py tests/scripts/test_run_company_narrative_backfill.py -q`
  - Result: passed, 15 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_narrative_enrichment.py tests/company/test_team_parser.py -q`
  - Result: passed, 23 tests.

- `cd apps/miroflow-agent && python -m compileall -q src/data_agents/company/narrative_enrichment.py`
  - Result: passed.

Skipped:

- Persisting generated narrative/team synthesis into upload-batch stages remains pending.

### 2026-05-28 - Structured team persistence slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/storage/test_v036_migration.py tests/storage/test_alembic_revision_lineage.py -q`
  - RED result before implementation: failed because V036 did not exist and the revision chain stopped at V035.
  - GREEN result after implementation: passed, 3 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_structured_business_models.py tests/data_agents/company/test_team_persistence.py tests/company/test_team_parser.py -q`
  - RED result before implementation: failed because `team_persistence` did not exist and `CompanyTeamMember` rejected structured LLM fields.
  - GREEN result after implementation: passed, 18 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_canonical_import_readiness.py tests/data_agents/company/test_import_xlsx.py tests/postgres/test_canonical_import_xlsx.py -q`
  - Result: passed, 9 tests; skipped 3 Postgres integration tests because neither `DATABASE_URL_TEST` nor `DATABASE_URL` was set.

Skipped:

- Live database migration execution remains pending for the later bounded validation run.

### 2026-05-28 - Generic Serper trusted identity-alias slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_yiou_adapter.py::test_yiou_llm_hint_extraction_parses_alias_founder_and_keywords -q`
  - RED result before implementation: failed because `YiouSearchHints` did not expose `identity_aliases`.
  - GREEN result after implementation: passed, 1 test.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_news_ingest.py::test_fetch_generic_serper_includes_only_llm_trusted_identity_aliases -q`
  - RED result before implementation: failed because `_fetch_generic_serper_identity_records` did not accept LLM search hints and `YiouSearchHints` did not accept `identity_aliases`.
  - GREEN result after implementation: passed, 1 test.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_serper_news_connector.py tests/data_agents/company/test_yiou_adapter.py tests/scripts/test_run_company_news_ingest.py tests/data_agents/company/test_enrichment_batch.py -q`
  - Result: passed, 68 tests.

- `python -m compileall -q apps/miroflow-agent/src/data_agents/company/news_connectors/serper.py apps/miroflow-agent/src/data_agents/company/news_connectors/iyiou.py apps/miroflow-agent/scripts/run_company_news_ingest.py apps/miroflow-agent/src/data_agents/company/enrichment_batch.py`
  - Result: passed.

Skipped:

- Live Serper requests and upload-batch E2E remain pending for the bounded 100-company validation stage.

### 2026-05-28 - Financing signals and recent dynamics slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_signal_event_extractor.py::test_extract_signal_events_normalizes_source_backed_funding_fields tests/data_agents/company/test_signal_event_extractor.py::test_extract_signal_events_review_gates_conflicting_funding_baseline -q`
  - RED result before implementation: failed because `extract_signal_events_from_news` did not accept XLSX funding baseline arguments and funding subject fields were not normalized.
  - GREEN result after implementation: passed, 2 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_signal_extract.py::test_insert_signal_events_uses_dedup_conflict -q`
  - RED result before implementation: failed because `SignalEventExtraction` did not carry event status and inserts always used `active`.
  - GREEN result after implementation: passed, 1 test.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/storage/test_v038_migration.py tests/storage/test_alembic_revision_lineage.py -q`
  - RED result before implementation: failed because V038 did not exist and the recent Alembic chain stopped at V037.
  - GREEN result after implementation: passed, 3 tests.

- `cd apps/admin-console && uv run --no-sync pytest tests/test_domains_postgres.py::test_company_released_object_exposes_products_events_and_source_evidence -q`
  - RED result before implementation: failed because the company domain recent-events SQL did not include `status`.
  - GREEN result after implementation: passed, 1 test.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_signal_event_extractor.py tests/scripts/test_run_company_signal_extract.py tests/storage/test_v038_migration.py tests/storage/test_alembic_revision_lineage.py -q`
  - Result: passed, 24 tests.

- `cd apps/admin-console && uv run --no-sync pytest tests/test_domains_postgres.py::test_company_released_object_exposes_products_events_and_source_evidence tests/test_data_api.py -q`
  - Result: passed, 2 tests and 7 skips.

- `python -m compileall -q apps/miroflow-agent/src/data_agents/company/signal_event_extractor.py apps/miroflow-agent/scripts/run_company_signal_extract.py apps/miroflow-agent/alembic/versions/V038_allow_company_signal_event_needs_review.py apps/admin-console/backend/api/domains.py`
  - Result: passed.

Skipped:

- Live financing extraction over uploaded companies remains pending until the upload-batch orchestration slice.

### 2026-05-28 - Upload batch flags and stale-run cleanup slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py::test_close_stale_running_enrichment_batches_fails_abandoned_rows -q`
  - RED result before implementation: failed because `close_stale_running_enrichment_batches` did not exist.
  - GREEN result after implementation: passed, 1 test.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py::test_parse_args_accepts_dry_run_skip_flags tests/scripts/test_run_company_upload_enrichment_batch.py::test_build_stage_commands_respects_dry_run_and_skip_flags -q`
  - RED result before implementation: failed because runner CLI did not accept dry-run/skip/stale flags and `_build_stage_commands` had no corresponding parameters.
  - GREEN result after implementation: passed, 2 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py -q`
  - Result: passed, 14 tests.

- `cd apps/admin-console && uv run --no-sync pytest tests/test_upload_pipeline_trigger.py -q`
  - Result: passed, 13 tests.

- `python -m compileall -q apps/miroflow-agent/src/data_agents/company/enrichment_batch.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/admin-console/backend/api/upload.py`
  - Result: passed.

Skipped:

- Full upload-stage rewiring, generic judged-material persistence, full miss-reason enum, and live/bounded 100-company validation remain pending.

### 2026-05-28 - Upload batch miss-reason closure slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py::test_infer_miss_reason_covers_operational_reason_enum -q`
  - RED result before implementation: failed because source errors returned `source_fetch_error` and the required miss-reason enum values were not all handled.
  - GREEN result after implementation: passed, 1 test.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py::test_miss_reason_by_company_covers_non_search_stage_failures -q`
  - RED result before implementation: failed because non-search stages returned no per-company miss reason.
  - GREEN result after implementation: passed, 1 test.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py -q`
  - Result: passed, 16 tests.

- `python -m compileall -q apps/miroflow-agent/src/data_agents/company/enrichment_batch.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py`
  - Result: passed.

Skipped:

- Upload integration for generic judged material and full multi-source synthesis audit remains pending.

### 2026-05-28 - Touched-company Milvus refresh slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_milvus_backfill_company.py tests/scripts/test_run_company_upload_enrichment_batch.py::test_build_stage_commands_scope_every_stage_to_company_ids tests/scripts/test_run_company_upload_enrichment_batch.py::test_build_stage_commands_passes_local_milvus_uri_as_cli_arg -q`
  - Result: passed, 11 tests.

- `python -m compileall -q apps/miroflow-agent/scripts/run_milvus_backfill.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py`
  - Result: passed.

Skipped:

- Live touched-company Milvus refresh remains pending for bounded upload validation.

### 2026-05-28 - Stage-level synthesis audit partial slice

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py::test_stage_details_capture_synthesis_and_persistence_audit -q`
  - RED result before implementation: failed because `_stage_details` did not exist.
  - GREEN result after implementation: passed, 1 test.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py -q`
  - Result: passed, 17 tests.

- `python -m compileall -q apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py`
  - Result: passed.

Skipped:

- Generic ReAct snippet/fetch/source-judgment audit remains pending, so task 8.4 remains open.

### 2026-05-28 - DeepSeek V4 Pro ambient-proxy runtime smoke

Commands run:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/llm/test_openai_client_extra_body.py::test_openai_client_ignores_ambient_proxy_env -q`
  - RED result before implementation: failed because `DefaultHttpxClient` read ambient `ALL_PROXY=socks5://...` and raised `ImportError: Using SOCKS proxy, but the 'socksio' package is not installed.`
  - GREEN result after implementation: passed, 1 test.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/professor/test_llm_profiles.py tests/llm/test_openai_client_extra_body.py -q`
  - Result: passed, 18 tests.

- `set -a; source apps/miroflow-agent/.env; set +a; timeout 45s uv run python <deepseek-openai-client-smoke>`
  - Result: passed.
  - Observed response model: `deepseek-v4-pro`.
  - Observed finish reason: `stop`.
  - Observed response excerpt: `OK`.
  - Observed reasoning output: absent.
  - Observed token usage: prompt tokens `19`, completion tokens `1`.

Notes:

- The local `.env` line `DEEPSEEK_MODEL` was aligned from `deepseek-v4-flash` to `deepseek-v4-pro`; credential values were not logged.
- The successful live smoke used the repository `OpenAIClient`, not only the raw SDK, and ran with the current shell proxy variables still present.

### 2026-05-28 - Bounded validation cleanup before rerun

Scope:

- Prior validation noise was cleaned only by validation time/source markers:
  `company_news_item.fetched_at >= 2026-05-28 05:55:00Z AND < 2026-05-28 06:10:00Z`
  for `source_adapter IN ('iyiou', 'pitchhub_36kr', 'generic_web')`, plus
  product/scenario evidence from `source_product_extractor.v1` with NULL
  `source_tier` in `2026-05-28 05:55:00Z..10:00:00Z`.
- The interrupted live validation rerun was cleaned only by batch/sample marker:
  `company_enrichment_batch.batch_id =
  b854d0e0-1bcc-4ea8-968c-b4b4dab1f45c`, its 100 sampled company IDs, and rows
  created after the batch `started_at = 2026-05-28 23:09:32.846351Z`.
- The cleanup did not delete all company data or all source rows.

Dry-run counts before applying:

```json
{
  "mode": "dry_run_restricted",
  "live_batch": "b854d0e0-1bcc-4ea8-968c-b4b4dab1f45c",
  "live_started_at": "2026-05-28 23:09:32.846351+00:00",
  "sample_companies": 100,
  "prior_news": 44,
  "live_news": 44,
  "signal_by_prior_or_live_news": 17,
  "signal_live_window": 0,
  "prior_product_evidence": 22,
  "live_product_evidence": 152,
  "prior_scenario_evidence": 6,
  "live_scenario_evidence": 20,
  "live_search_audit": 128,
  "state_rows_reset": 100
}
```

Applied cleanup counts:

```json
{
  "mode": "applied",
  "live_batch": "b854d0e0-1bcc-4ea8-968c-b4b4dab1f45c",
  "live_started_at": "2026-05-28 23:09:32.846351+00:00",
  "sample_companies": 100,
  "prior_product_ids": 10,
  "live_product_ids": 46,
  "prior_scenario_ids": 3,
  "live_scenario_ids": 20,
  "news_ids": 88,
  "signal_events_deleted": 17,
  "prior_product_evidence_deleted": 22,
  "live_product_evidence_deleted": 152,
  "products_deleted_when_orphaned": 55,
  "prior_scenario_evidence_deleted": 6,
  "live_scenario_evidence_deleted": 20,
  "scenarios_deleted_when_orphaned": 23,
  "news_deleted": 88,
  "search_audit_deleted": 128,
  "states_reset": 100,
  "batch_reset": 1
}
```

Post-cleanup verification:

- `company_enrichment_batch` for
  `b854d0e0-1bcc-4ea8-968c-b4b4dab1f45c`: `status='queued'`,
  `current_stage='queued'`, processed/succeeded/failed all `0`, started and
  finished timestamps cleared.
- All 100 `company_enrichment_company_state` rows for that batch are queued with
  product/scenario/event counters reset to `0`.
- Residual checks returned `0` for live-batch search audit, live-batch news
  since the old start time, live-batch product evidence since the old start
  time, prior NULL-tier product evidence, prior NULL-tier scenario evidence,
  and prior validation-window news.

### 2026-05-28 - Source-product LLM fallback tightening during live validation

Observed during the first rerun chunk:

- `generic_web` source judgment accepted 39 source rows for the first 10
  companies.
- `source_product_extract` produced 12 distinct `generic_web` products and 56
  `generic_web` evidence rows for that first chunk.
- Manual DB inspection showed duplicated product variants for the same source
  family, e.g. multiple KidoAI camera names and multiple PowerArena/HOP names.

Root cause:

- `scripts/run_company_source_product_extract.py` called
  `extract_products_and_scenarios_with_llm_fallback(...)` with
  `existing_products=[]` and `existing_scenarios=[]` even after deterministic
  extraction had already found source-grounded candidates. The fallback
  therefore behaved as a second parallel extractor and could emit alternate
  names for the same product.

Code/test change:

- `run_company_source_product_extract.py` now skips the LLM extraction fallback
  when deterministic candidates contain a strong product/scenario signal.
- Weak deterministic candidates such as bare ASCII brand names still fall
  through to the LLM so `PowerArena` can be corrected to
  `PowerArena HOP 人因作业平台`.
- Added/updated regression coverage in
  `tests/scripts/test_run_company_source_product_extract.py`.

Verification:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_source_product_extract.py -q`
  - Result: passed, 13 tests.

Second interrupted-rerun cleanup before restarting validation:

```json
{
  "mode": "applied_second_live_cleanup",
  "live_started_at": "2026-05-28 23:31:19.524525+00:00",
  "sample_companies": 100,
  "product_ids": 28,
  "scenario_ids": 13,
  "news_ids": 47,
  "signals_deleted": 0,
  "product_evidence_deleted": 105,
  "products_deleted_when_orphaned": 28,
  "scenario_evidence_deleted": 14,
  "scenarios_deleted_when_orphaned": 13,
  "news_deleted": 47,
  "search_audit_deleted": 128,
  "states_reset": 100,
  "batch_reset": 1
}
```

### 2026-05-28 - Generic-web candidate-level gate during live validation

Observed during the next first-chunk rerun:

- The LLM fallback tightening reduced `generic_web` distinct products in the
  first chunk, but DB inspection still found generic-web candidates that were
  not concrete products: SEO page titles and generic category names such as
  `智能硬件产品`.

Root cause:

- The source-level gate confirms a generic web page may contain useful product
  facts, but it did not verify each extracted product/scenario candidate. A
  page can be relevant while a specific candidate is still only a company name,
  project name, SEO title, generic category, broad capability, or company
  profile phrase.

Code/test change:

- Added a generic-web candidate-level DeepSeek gate in
  `scripts/run_company_source_product_extract.py`.
- The candidate gate keeps only concrete products, named platforms, devices,
  services, solutions, systems, or productized offerings attributable to the
  target company.
- It rejects company names, project names, brand-only names, SEO titles,
  investment/funding names, generic categories, broad capabilities, and
  candidates whose evidence only says the target is a company/provider/developer.

Verification:

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_source_product_extract.py -q`
  - Result: passed, 14 tests.

Third interrupted-rerun cleanup before restarting validation:

```json
{
  "mode": "applied_third_live_cleanup",
  "live_started_at": "2026-05-28 23:40:35.887030+00:00",
  "sample_companies": 100,
  "product_ids": 28,
  "scenario_ids": 19,
  "news_ids": 49,
  "signals_deleted": 0,
  "product_evidence_deleted": 91,
  "products_deleted_when_orphaned": 28,
  "scenario_evidence_deleted": 19,
  "scenarios_deleted_when_orphaned": 19,
  "news_deleted": 49,
  "search_audit_deleted": 130,
  "states_reset": 100,
  "batch_reset": 1
}
```

### 2026-05-29 - Bounded 100-company upload validation closure

Commands and evidence:

- `cd apps/miroflow-agent && .venv/bin/python <final-batch-aggregate-query>`
  - Result: passed.
  - Dry-run batch `2f157839-aab2-469f-b09c-122e21c4f8b8`: `succeeded`,
    100 selected, 100 processed, 100 succeeded, 0 failed.
  - Live batch `b854d0e0-1bcc-4ea8-968c-b4b4dab1f45c`: `succeeded`,
    100 selected, 100 processed, 100 succeeded, 0 failed.
  - Company base records ready: 100/100.
  - Profiles length >= 500: 99/100.
  - Technology-route summaries length >= 80: 99/100.
  - Touched-company vectors refreshed: 100/100.
  - Products: 336 total, 152 ready, 87 companies with any product, 82 companies
    with ready product.
  - Application scenarios: 227 total, 146 ready, 55 companies with scenarios,
    50 companies with ready scenarios.
  - Funding events: 97 total, 55 companies with funding event, 42 source-backed
    signal events.
  - Structured team: 290 structured members across 86 companies.
  - Current miss reasons: `synthesis_no_facts` 72 companies, `llm_rejected` 14,
    `all_results_rejected` 3, `no_results` 1.
  - Escaped pollution check for `COMP-10047ff88d61`: 0 Arabica/coffee news rows
    and 0 Arabica/coffee product rows.

- `agent-browser --session mt-5180-check open http://127.0.0.1:5180/company/COMP-37013bba3132`
  and `agent-browser --session mt-5180-check get text body`
  - Result: passed.
  - Observed Basic Information, Products, Application Scenarios, Recent Events,
    Summary, and Sources in the required order.
  - Product, scenarios, funding history, long company profile, technology route,
    and source links were visible.

- `agent-browser --session mt-5180-lens open http://127.0.0.1:5180/company/COMP-54fd4dd036ff`
  and `agent-browser --session mt-5180-lens get text body`
  - Result: passed.
  - Observed six-field product display, application scenarios, recent financing,
    long company profile, technology route, and source links.

- `agent-browser --session mt-5180-qiduo open http://127.0.0.1:5180/company/COMP-10047ff88d61`
  and `agent-browser --session mt-5180-qiduo get text body`
  - Result: passed.
  - Observed product and funding data; no unrelated Arabica/coffee pollution was
    visible. No publishable application scenario was shown for this company.

- `agent-browser --session mt-5180-sparse open http://127.0.0.1:5180/company/COMP-7a89e82e6329`
  and `agent-browser --session mt-5180-sparse get text body`
  - Result: passed.
  - Observed company base record ready with XLSX fallback company profile and
    technology-route text. Product, application scenario, recent dynamics, and
    source links were empty because current source material is sparse.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_source_product_extractor.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/scripts/test_run_company_source_product_extract.py tests/data_agents/company/test_yiou_adapter.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_generic_source_judgment.py tests/data_agents/company/test_vectorizer.py tests/scripts/test_run_milvus_backfill_company.py tests/data_agents/company/test_narrative_enrichment.py -q`
  - Result: passed, 128 tests.

- `cd apps/admin-console && .venv/bin/python -m pytest tests/test_upload_pipeline_trigger.py tests/test_data_api_quality_status.py -q`
  - Result: passed, 20 tests with 4 deprecation warnings from FastAPI
    `on_event` usage.

- `cd apps/admin-console/frontend && npm test -- --run src/pages/RecordDetail.test.tsx`
  - Result: passed, 1 file and 3 tests.

- `cd apps/miroflow-agent && uv run python <deepseek-v4-pro-non-thinking-smoke>`
  - Result: passed.
  - Observed response model: `deepseek-v4-pro`.
  - Observed finish reason: `stop`.
  - Observed reasoning output: absent.
  - Observed response excerpt: `{"ok":true,"mode":"non-thinking"}`.

Report:

- `.agents/runs/company-synthesis-enrichment-pipeline/validation-100.md`
  records batch IDs, cleanup scope, aggregate counts, source audit, product and
  scenario evidence tiers, manual 5180 inspection, DeepSeek runtime status, LLM
  usage inventory, and residual risks.
