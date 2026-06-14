# Verification - company-scaleout-enrichment-hardening

## 2026-05-30 - Upload Batch Execution Hardening

### Commands

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py -q`
  - Result: passed, 26 tests.
  - RED evidence: before implementation, the same command failed on missing stage policy, CLI flags, retry metadata, checkpoint summary, LLM audit metadata, miss-reason classification, and stale company-state cleanup.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_llm_routing.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_signal_extract.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_official_product_capture.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py -q`
  - Result: passed, 113 tests.

- `python -m compileall -q apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/src/data_agents/company/enrichment_batch.py`
  - Result: passed.

- `openspec validate company-scaleout-enrichment-hardening --strict`
  - Result: passed.

### Covered

- Per-stage upload-batch execution policy.
- LLM/web concurrency overrides and provider max-concurrency caps.
- Stage retry/backoff metadata and final failure reason preservation.
- Structured-output failure classification.
- Per-company stage checkpoint payloads with credential-safe LLM task audit.
- Resume skip reporting for succeeded stage checkpoints.
- Stale running company-state cleanup.
- Batch-level summary counters used by later 200-company validation reports.

### Remaining

- Full child-writer table-level idempotency remains under task 5.3.
- Admin-console diagnostics, 200-company dry-run/live validation, RAG smoke tests, and 5180 inspection remain pending.

## 2026-05-30 - Source Quality Gates And Rejection Diagnostics

### Commands

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_source_product_extract.py -q`
  - Result: passed, 15 tests.
  - RED evidence: before implementation, the same command failed on missing `rejected_candidate_reasons` / `rejected_candidates`; after adding the six-field report assertion, it also failed until source-product report items were narrowed to business-facing fields.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py::test_stage_details_capture_synthesis_and_persistence_audit tests/scripts/test_run_company_upload_enrichment_batch.py::test_stage_details_capture_source_product_rejection_reasons tests/scripts/test_run_company_upload_enrichment_batch.py::test_batch_summary_accumulates_source_product_rejection_reasons -q`
  - Result: passed, 3 tests.
  - RED evidence: before implementation, source-product stage details contained only `llm_rejected_or_empty`, and batch summary lacked rejected-candidate counts and reason aggregation.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_source_product_extractor.py::test_generic_web_products_require_accepted_source_judgment_before_ready tests/data_agents/company/test_source_product_extractor.py::test_generic_web_products_can_be_ready_with_accepted_strong_judgment -q`
  - Result: passed, 2 tests.
  - RED evidence: before implementation, generic-web material with high confidence but no accepted source judgment could become `ready`.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_source_product_extract.py tests/data_agents/company/test_source_product_extractor.py tests/data_agents/company/test_generic_source_judgment.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_upload_enrichment_batch.py -q`
  - Result: passed, 60 tests.

- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_llm_routing.py tests/data_agents/company/test_generic_source_judgment.py tests/data_agents/company/test_source_product_extractor.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_signal_extract.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_official_product_capture.py tests/data_agents/company/test_official_product_capture.py -q`
  - Result: passed, 126 tests.

- `python -m compileall -q apps/miroflow-agent/scripts/run_company_source_product_extract.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/src/data_agents/company/source_product_extractor.py`
  - Result: passed.

- `cd apps/miroflow-agent && uv run ruff check scripts/run_company_source_product_extract.py scripts/run_company_upload_enrichment_batch.py src/data_agents/company/source_product_extractor.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_source_product_extractor.py`
  - Result: passed.

- `openspec validate company-scaleout-enrichment-hardening --strict`
  - Result: passed.

### Covered

- Generic source judgment acceptance requires target-company identity and fact attribution.
- Generic web product admission preserves LLM rejection reason.
- Yiou/PitchHub/generic source product and scenario candidate attribution preserves LLM rejection reason.
- Source-product reports expose only product name, product description, product category, technical tags, target customers, and application scenarios as business-facing product fields.
- Generic web products require accepted source judgment before `ready` status.
- Upload-batch summary and stage details expose rejected candidate counts, reasons, and bounded sanitized samples.

### Remaining

- Admin-console diagnostics and 5180 display remain under section 6.
- Full child-writer idempotency remains under task 5.3.
- 200-company dry-run/live validation, RAG smoke tests, 5180 inspection, and gated 1024-company full rerun remain pending.

## 2026-05-30 - Admin Pipeline Diagnostics And Company Detail Evidence

### Commands

- `cd apps/admin-console && uv run --no-sync pytest tests/test_pipeline_runs_api.py::test_get_pipeline_run_returns_company_enrichment_batch_status -q`
  - Result: passed, 1 test.
  - RED evidence: before implementation, this test failed because the pipeline run detail payload did not expose enrichment diagnostics beyond basic batch status fields.

- `cd apps/admin-console/frontend && npm test -- --run src/pages/PipelineRuns.test.tsx`
  - Result: passed, 2 tests.
  - RED evidence: before implementation, this test failed because the pipeline detail UI did not render source acceptance/rejection, product/scenario/event counts, vector refresh status, official failure reasons, candidate rejection reasons, source distribution, or company-level diagnostic samples.

- `cd apps/admin-console && uv run --no-sync pytest tests/test_pipeline_runs_api.py tests/test_domains_postgres.py -q`
  - Result: passed, 49 tests.

- `cd apps/admin-console/frontend && npm test -- --run src/pages/RecordDetail.test.tsx`
  - Result: passed, 4 tests.

- `cd apps/admin-console/frontend && npm test -- --run src/pages/PipelineRuns.test.tsx src/pages/RecordDetail.test.tsx`
  - Result: passed, 6 tests.

- `cd apps/admin-console && uv run --no-sync ruff check backend/api/pipeline.py tests/test_pipeline_runs_api.py`
  - Result: passed.

- `python -m compileall -q apps/admin-console/backend/api/pipeline.py`
  - Result: passed.

- `cd apps/admin-console/frontend && npm run build`
  - Result: passed; Vite reported the existing large chunk warning.

- `openspec validate company-scaleout-enrichment-hardening --strict`
  - Result: passed.

### Covered

- Upload-scoped company enrichment batch diagnostics in the pipeline detail API.
- Bounded company-level diagnostic samples with stage status, miss reason, last error, source counts, product/scenario/event counts, official product count, and vector refresh flag.
- Batch-level rollups for source adapters, official-site failure reasons, rejected candidate reasons, status counts, stage counts, miss reasons, LLM failures, and vector refresh count.
- Pipeline detail UI diagnostics for operators.
- Company detail source links remain visible through the evidence section while product cards stay limited to business-facing product fields.

### Remaining

- Company detail review actions/status still need a dedicated operator surface that does not violate the six-field product card requirement.
- 5180 search/detail navigation was not live-inspected in this slice.
- Full child-writer idempotency, 200-company dry-run/live validation, RAG smoke tests, and the gated 1024-company full rerun remain pending.

## 2026-05-30 - Batch Idempotency And Scale Validation Report Shape

### Commands

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py tests/data_agents/company/test_official_product_capture.py tests/scripts/test_run_company_signal_extract.py tests/scripts/test_run_company_source_product_extract.py tests/data_agents/company/test_source_product_extractor.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_narrative_backfill.py tests/scripts/test_run_milvus_backfill_company.py tests/data_agents/company/test_vectorizer.py -q`
  - Result: passed, 120 tests.

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_official_product_capture.py tests/data_agents/company/test_generic_source_judgment.py tests/data_agents/company/test_yiou_adapter.py tests/data_agents/company/test_serper_news_connector.py -q`
  - Result: passed, 84 tests.

- `cd apps/miroflow-agent && uv run --no-sync ruff check scripts/run_company_upload_enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_official_product_capture.py tests/scripts/test_run_company_signal_extract.py`
  - Result: passed.

- `python -m compileall -q apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/admin-console/backend/api/pipeline.py`
  - Result: passed.

- `cd apps/admin-console && uv run --no-sync pytest tests/test_pipeline_runs_api.py tests/test_domains_postgres.py -q`
  - Result: passed, 49 tests.

- `cd apps/admin-console/frontend && npm test -- --run src/pages/PipelineRuns.test.tsx src/pages/RecordDetail.test.tsx`
  - Result: passed, 6 tests.

### Covered

- Upload-batch validation report shape for selected company IDs, enabled/skipped stages, source-adapter counts, miss-reason counts, vector refresh count, RAG smoke status, and residual risks.
- Duplicate-safe product and application-scenario evidence insertion with source-tier preservation.
- Duplicate-safe financing signal insertion through `(company_id, event_type, dedup_key)` conflict handling.
- Duplicate-safe source-row ingestion through source-URL conflict guards for Yiou, PitchHub, generic Serper, and accepted generic web sources.
- Profile-summary backfill default only-missing behavior and vector refresh idempotency through Milvus upsert/collection idempotency tests.

### Remaining

- The actual 200-company dry-run and live bounded validation are still pending under section 7/8.
- RAG smoke checks, 5180 live inspection, and the gated 1024-company full rerun remain pending.

## 2026-05-30 - Representative Sample Selector And Plan-Only Dry Run

### Commands

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py::test_select_representative_company_sample_is_deterministic_and_stratified tests/scripts/test_run_company_upload_enrichment_batch.py::test_parse_args_accepts_dry_run_skip_flags tests/scripts/test_run_company_upload_enrichment_batch.py::test_process_batch_plan_only_uses_representative_sample_without_writes -q`
  - Result: passed, 3 tests.
  - RED evidence: before implementation, the same command failed because `select_representative_company_sample`, `load_representative_company_sample`, `--representative-sample-size`, and `--plan-only` did not exist.

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py -q`
  - Result: passed, 31 tests.

- `cd apps/miroflow-agent && uv run --no-sync ruff check scripts/run_company_upload_enrichment_batch.py src/data_agents/company/enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py`
  - Result: passed.

- `python -m compileall -q apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/src/data_agents/company/enrichment_batch.py`
  - Result: passed.

### Covered

- Deterministic representative sample selection by industry, website availability, and existing external-source coverage buckets.
- Stable selection order independent of candidate row input order.
- Upload-batch CLI support for `--representative-sample-size`.
- No-write `--plan-only` report path with selected company IDs, selection criteria, expected writes, stage policies, skipped stages, blocked prerequisites, RAG smoke status, and residual risks.

### Remaining

- The actual 200-company dry-run execution report remains pending under task 8.5.
- The 200-company live bounded validation, RAG smoke checks, 5180 inspection, and gated 1024-company full rerun remain pending.

## 2026-05-30 - Live Bounded Sample Mode And Validation Cleanup

### Commands

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py::test_process_batch_live_representative_sample_stays_bounded -q`
  - Result: passed, 1 test.

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_validation_cleanup.py -q`
  - Result: passed, 2 tests.
  - RED evidence: before implementation, the same command failed because `scripts/run_company_validation_cleanup.py` did not exist.

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_validation_cleanup.py -q`
  - Result: passed, 34 tests.

- `cd apps/miroflow-agent && uv run --no-sync ruff check scripts/run_company_upload_enrichment_batch.py scripts/run_company_validation_cleanup.py src/data_agents/company/enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_validation_cleanup.py`
  - Result: passed.

- `python -m compileall -q apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/scripts/run_company_validation_cleanup.py apps/miroflow-agent/src/data_agents/company/enrichment_batch.py`
  - Result: passed.

### Covered

- Live representative-sample runs keep child commands and Milvus refresh bounded to selected company IDs.
- The runner reports representative-sample scope and `full_population_attempted=false`.
- Validation cleanup defaults to dry-run.
- Applied cleanup touches only `company_enrichment_search_audit`, `company_enrichment_company_state`, and `company_enrichment_batch` for the selected batch.
- Cleanup regression tests protect Company production fact tables from accidental deletion or update.

### Remaining

- The actual 200-company dry-run and live bounded run remain pending.
- RAG smoke checks, 5180 inspection, and gated 1024-company full rerun remain pending.

## 2026-05-30 - Official Capture Script Options And Page Reuse

### Commands

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_official_product_capture.py::test_parse_args_accepts_dry_run_and_limit tests/scripts/test_run_company_official_product_capture.py::test_cli_dry_run_extracts_products_from_diagnostic_sitemap_pages -q`
  - Result: passed, 2 tests.
  - RED evidence: before implementation, the same command failed because sitemap/common-path discovery toggles were not exposed and sitemap-discovered diagnostic pages did not feed product extraction.

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_official_product_capture.py tests/data_agents/company/test_official_product_capture.py -q`
  - Result: passed, 30 tests.

- `cd apps/miroflow-agent && uv run --no-sync ruff check scripts/run_company_official_product_capture.py tests/scripts/test_run_company_official_product_capture.py`
  - Result: passed.

- `python -m compileall -q apps/miroflow-agent/scripts/run_company_official_product_capture.py`
  - Result: passed.

### Covered

- Official capture script supports timeout, page-count, JavaScript rendering, sitemap discovery, and common-path discovery controls.
- Official capture report includes failure taxonomy through attempt and failure rows.
- Diagnostic official pages are reused for product extraction, including sitemap-discovered pages.
- Official capture helper boundaries remain separated for page discovery, rendering fallback, fetch diagnostics, source-material extraction, product extraction, and failure classification.

### Remaining

- Runtime website coverage still needs the 200-company validation gate.

## 2026-05-30 - Company Detail Review State UI

### Commands

- `cd apps/admin-console/frontend && npm test -- --run src/pages/RecordDetail.test.tsx`
  - Result: passed, 5 tests.
  - RED evidence: before implementation, the new review-state/action assertion failed because product cards did not render review controls.

- `cd apps/admin-console/frontend && npm test -- --run src/pages/PipelineRuns.test.tsx src/pages/RecordDetail.test.tsx`
  - Result: passed, 7 tests.

- `cd apps/admin-console && uv run --no-sync pytest tests/test_domains_postgres.py tests/test_pipeline_runs_api.py -q`
  - Result: passed, 49 tests.

### Covered

- Company detail ordering remains basic information, products, application scenarios, recent dynamics.
- Product business fields remain limited to the six user-facing product fields.
- Product/scenario review state and review actions render separately from raw product fields.
- Source links remain in the evidence section.

### Remaining

- 5180 live search/detail inspection remains pending.

## 2026-05-30 - Focused Verification Gate And LLM Routing Isolation

### Commands

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/data_agents/test_structured_output_mode.py tests/data_agents/company/test_llm_routing.py -q`
  - Result: passed, 17 tests.
  - RED evidence: before implementation, the same command failed because `load_dotenv()` imported through `src.io.input_handler` populated `LOCAL_LLM_MODEL` and `LOCAL_LLM_API_KEY`, overriding Company task-specific DeepSeek routing.

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/data_agents/professor/test_llm_profiles.py tests/data_agents/company/test_llm_routing.py -q`
  - Result: passed, 30 tests.

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/data_agents/company/test_llm_routing.py tests/data_agents/company/test_generic_source_judgment.py tests/data_agents/company/test_source_product_extractor.py tests/data_agents/company/test_official_product_capture.py tests/data_agents/company/test_enrichment_batch.py tests/data_agents/company/test_vectorizer.py tests/data_agents/company/test_yiou_adapter.py tests/data_agents/company/test_serper_news_connector.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_signal_extract.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_narrative_backfill.py tests/scripts/test_run_company_official_product_capture.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/scripts/test_run_company_validation_cleanup.py tests/scripts/test_run_milvus_backfill_company.py -q`
  - Result: passed, 223 tests.

- `cd apps/miroflow-agent && uv run --no-sync ruff check src/data_agents/professor/llm_profiles.py src/data_agents/company/llm_routing.py`
  - Result: passed.

- `cd apps/miroflow-agent && uv run --no-sync python -m py_compile src/data_agents/professor/llm_profiles.py src/data_agents/company/llm_routing.py`
  - Result: passed.

- `cd apps/admin-console && uv run --no-sync pytest tests/test_domains_postgres.py tests/test_pipeline_runs_api.py tests/test_upload_pipeline_trigger.py tests/test_data_api_quality_status.py tests/test_data_api.py tests/test_chat_classifier_b_g_tune.py -q`
  - Result: passed, 92 tests and 7 skipped.

- `cd apps/admin-console/frontend && npm test -- --run src/pages/PipelineRuns.test.tsx src/pages/RecordDetail.test.tsx src/pages/DomainList.test.tsx`
  - Result: passed, 8 tests.

- `cd apps/admin-console/frontend && npm run build`
  - Result: passed; Vite reported the existing large chunk warning.

- `openspec validate company-scaleout-enrichment-hardening --strict`
  - Result: passed.

### Covered

- Company task-specific model routing is isolated from broad `LOCAL_LLM_*` endpoint overrides loaded from `.env`.
- The shared professor LLM profile resolver still preserves broad endpoint overrides for default callers.
- The Hydra config surface now includes `deepseek-v4-lite`.
- Company vector payload text and `profile_summary` include long profile text, technology summaries, products, technical tags, target customers, application scenarios, structured team highlights, and source-backed funding details.
- Focused Company, admin API, frontend, frontend build, lint, compile, and OpenSpec checks passed after the routing fix.

### Remaining

- Actual 200-company dry-run validation.
- Actual 200-company live bounded validation.
- Touched-company vector refresh and RAG smoke checks.
- 5180 live search/detail inspection.
- Gated 1024-company dry-run/live rerun and effect report.

## 2026-05-30 - 200-Company Dry-Run Bottleneck and Child-Concurrency Gate

### Commands

- `DATABASE_URL=... uv run --no-sync python scripts/run_company_upload_enrichment_batch.py --batch-id 4fe6c43d-2054-4732-b47f-2364dd48e9b2 --representative-sample-size 200 --dry-run --skip-persistence --skip-milvus --chunk-size 25 --stage-concurrency 2 --llm-stage-concurrency 2 --web-stage-concurrency 2 --stage-subchunk-size 5 --stage-timeout-seconds 1200 --stage-retry-budget 1 --retry-backoff-seconds 1 --sleep-seconds 0.05 --official-product-max-pages 3 --source-product-limit 4000`
  - Result: failed by wrapper timeout after 10,800 seconds.
  - Evidence: 175 selected companies completed, 25 selected companies were stale-running in `generic_source_judgment`.
  - Cleanup: no child `run_company_*` process remained; the 25 stale-running company states were closed to `failed` with `last_error='wrapper_timeout_after_10800_seconds'`, and the batch was marked `partial`.
  - Dry-run data safety: `company_product`, `company_product_evidence`, `company_application_scenario`, `company_signal_event`, and `company_news_item` row counts had zero delta after the no-write fix; `company_enrichment_search_audit` increased as permitted dry-run audit evidence.

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/data_agents/company/test_provider_rate_limit.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_signal_extract.py -q`
  - Result: passed, 99 tests.

- `cd apps/miroflow-agent && uv run --no-sync ruff check scripts/run_company_xlsx_team_synthesis.py scripts/run_company_source_product_extract.py scripts/run_company_generic_source_judgment.py scripts/run_company_news_ingest.py scripts/run_company_signal_extract.py scripts/run_company_upload_enrichment_batch.py src/data_agents/company/provider_rate_limit.py tests/data_agents/company/test_provider_rate_limit.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_signal_extract.py tests/scripts/test_run_company_upload_enrichment_batch.py`
  - Result: passed.

- `python -m compileall -q apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py apps/miroflow-agent/scripts/run_company_source_product_extract.py apps/miroflow-agent/scripts/run_company_generic_source_judgment.py apps/miroflow-agent/scripts/run_company_news_ingest.py apps/miroflow-agent/scripts/run_company_signal_extract.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/src/data_agents/company/provider_rate_limit.py`
  - Result: passed.

- `DATABASE_URL=... uv run --no-sync python scripts/run_company_upload_enrichment_batch.py --batch-id 4c87b052-b9a3-4e93-8bd7-5f9186bd5f10 --representative-sample-size 10 --dry-run --skip-persistence --skip-milvus --chunk-size 10 --stage-concurrency 1 --llm-stage-concurrency 1 --web-stage-concurrency 1 --stage-subchunk-size 10 --stage-timeout-seconds 900 --stage-retry-budget 0 --retry-backoff-seconds 0 --sleep-seconds 0.05 --official-product-max-pages 2 --source-product-limit 1000 --child-llm-concurrency 2 --child-web-concurrency 2`
  - Result: passed; batch `4c87b052-b9a3-4e93-8bd7-5f9186bd5f10` finished `succeeded`, 10 processed, 10 succeeded, 0 failed.
  - Dry-run data safety: zero delta for `company_product`, `company_product_evidence`, `company_application_scenario`, `company_signal_event`, and `company_news_item`; `company_enrichment_search_audit` increased by 52 audit rows.
  - Checkpoint evidence: 10 company states carried checkpoints for each of `generic_source_judgment`, `multi_source_narrative`, `news_iyiou`, and `news_pitchhub`.

### Covered

- The 200-company dry-run failure is now recorded as the measured scaleout bottleneck and a hard go/no-go gate before any 1024-company execution.
- Child LLM/web concurrency is configurable independently from stage/shard concurrency.
- DeepSeek and Serper calls now go through provider-level rate-limit wrappers.
- `run_company_xlsx_team_synthesis.py` now uses Company LLM task routing instead of the generic professor resolver.
- The runner will not overwrite already checkpointed company stages when a shard fails.
- A real 10-company dry-run smoke proves the new child-concurrency path starts, checkpoints, and preserves no business fact writes.

### Remaining

- Task 8.5 remains pending: the post-optimization 200-company dry-run still needs to complete successfully.
- Live bounded 200-company validation, touched-vector refresh, RAG smoke checks, 5180 inspection, and the gated 1024-company run remain pending.

## 2026-05-31 - 200-Company Post-Optimization Dry-Run

### Commands

- `DATABASE_URL=... uv run --no-sync python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py --batch-id fb7eeffb-ca23-45bd-8116-0029f8aa32ce --representative-sample-size 200 --dry-run --skip-persistence --skip-milvus --chunk-size 25 --stage-concurrency 2 --llm-stage-concurrency 2 --web-stage-concurrency 2 --stage-subchunk-size 10 --stage-timeout-seconds 1800 --stage-retry-budget 1 --retry-backoff-seconds 1 --sleep-seconds 0.05 --official-product-max-pages 3 --source-product-limit 4000 --child-llm-concurrency 2 --child-web-concurrency 2`
  - Result: passed.
  - Batch status: `succeeded`; 200 selected companies processed, 200 succeeded, 0 failed.
  - Runtime: 2026-05-30 19:47:17 UTC to 2026-05-31 00:12:45 UTC, about 4h25m.
  - Report: `.agents/runs/company-scaleout-enrichment-hardening/company-200-dry-run-post-optimization-20260530T1948Z.json`.
  - Summary: `.agents/runs/company-scaleout-enrichment-hardening/company-200-dry-run-post-optimization-summary-20260531.md`.
  - Stderr: `.agents/runs/company-scaleout-enrichment-hardening/company-200-dry-run-post-optimization-20260530T1948Z.stderr.txt`; empty.

- `DATABASE_URL=... uv run --no-sync python - <<'PY' ... company_enrichment_batch/company_enrichment_company_state/count verification ... PY`
  - Result: passed.
  - Final state: 200 `batch_complete/succeeded`; 824 unselected imported companies remained `queued`.
  - Business fact table deltas were zero for `company_product`, `company_product_evidence`, `company_application_scenario`, `company_signal_event`, and `company_news_item`.
  - `company_enrichment_search_audit` increased from 3740 to 4793, matching `summary.query_count=1053`.

### Covered

- The post-optimization 200-company dry-run gate.
- Child concurrency settings recorded as `llm=2` and `web=2`.
- Dry-run business fact-table no-write behavior.
- Per-company checkpoint finalization after web/LLM-heavy stages.
- Model-routing evidence in the batch artifact: trusted XLSX/search hints use `deepseek-v4-lite`; source judgment, financing extraction, source-product admission, and multi-source narrative synthesis use `deepseek-v4-pro`.
- Source and extraction metrics: 1053 queries, 513 fetches, 832 accepted sources, 1095 rejected sources, 122 source products extracted, 64 source scenarios extracted, 2 funding events extracted, and 192 multi-source narratives generated.

### Remaining

- Runtime is still too long for a direct 1024-company run.
- `source_product_extract`, `news_ingest`, and target-customer metric reporting were fixed after this dry-run; another bounded run is needed to observe the improved state shape, runtime, and corrected coverage counts.
- The 200-company live bounded run, touched-vector refresh, RAG smoke checks, 5180 inspection, and gated 1024-company dry-run/live execution remain pending.

## 2026-05-31 - Post Dry-Run Concurrency And Metric Hardening

### Commands

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_news_ingest.py::test_cli_dry_run_processes_companies_concurrently_when_configured -q`
  - RED before implementation: `companies_with_errors` was 2 because the first company blocked on a barrier and the second company never entered fetch concurrently.
  - GREEN after implementation: passed.

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_source_product_extract.py::test_cli_dry_run_extracts_products_without_insert tests/scripts/test_run_company_source_product_extract.py::test_cli_checkpoints_each_requested_company_even_without_source_rows -q`
  - RED before implementation: `products_with_target_customers` was missing, and `mark_company_stage_complete` was not available in the source-product script.
  - GREEN after implementation: passed.

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_xlsx_team_synthesis.py::test_process_company_synthesizes_publishable_products_from_xlsx -q`
  - RED before implementation: `products_with_target_customers` was missing from the XLSX/team company report.
  - GREEN after implementation: passed.

- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_upload_enrichment_batch.py -q`
  - Result: passed, 82 tests.

- `cd apps/miroflow-agent && uv run --no-sync ruff check scripts/run_company_news_ingest.py scripts/run_company_source_product_extract.py scripts/run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_xlsx_team_synthesis.py`
  - Result: passed.

- `python -m compileall -q apps/miroflow-agent/scripts/run_company_news_ingest.py apps/miroflow-agent/scripts/run_company_source_product_extract.py apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py`
  - Result: passed.

### Covered

- `run_company_news_ingest.py --concurrency` now actually fetches company web/news sources concurrently at company level instead of only accepting the CLI parameter.
- `run_company_source_product_extract.py` now checkpoints every requested company in the source-product stage, including requested companies that have no selected source rows.
- Source-product checkpoints include source rows processed, product count, scenario count, target-customer product count, rejected candidate count, and dry-run details.
- XLSX/team synthesis and source-product extraction now report `products_with_target_customers`, so batch-level summaries can stop reporting false zero target-customer coverage.

### Remaining

- These fixes were unit/script verified after the 200-company dry-run; a bounded rerun is still needed to measure runtime and observe corrected target-customer coverage in an end-to-end report.
- 200-company live bounded run, touched-vector refresh, RAG smoke checks, 5180 inspection, and 1024-company execution remain pending.

## 2026-05-31 - 10-Company Post-Fix Dry-Run Smoke

### Commands

- `DATABASE_URL=... uv run --no-sync python - <<'PY' ... create_enrichment_batch(...) ... PY`
  - Result: passed.
  - Batch created: `88cd2a26-bc87-401a-b4ed-2baa2a9a55ff`.
  - Companies selected: 10.

- `DATABASE_URL=... uv run --no-sync python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py --batch-id 88cd2a26-bc87-401a-b4ed-2baa2a9a55ff --dry-run --skip-persistence --skip-milvus --chunk-size 10 --stage-concurrency 1 --llm-stage-concurrency 1 --web-stage-concurrency 1 --stage-subchunk-size 10 --stage-timeout-seconds 900 --stage-retry-budget 0 --retry-backoff-seconds 0 --sleep-seconds 0.05 --official-product-max-pages 2 --source-product-limit 1000 --child-llm-concurrency 2 --child-web-concurrency 2`
  - Result: passed.
  - Batch status: `succeeded`; 10 selected companies processed, 10 succeeded, 0 failed.
  - Report: `.agents/runs/company-scaleout-enrichment-hardening/company-10-dry-run-post-fix-20260531T0030Z.json`.
  - Summary: `.agents/runs/company-scaleout-enrichment-hardening/company-10-dry-run-post-fix-summary-20260531.md`.
  - Stderr: `.agents/runs/company-scaleout-enrichment-hardening/company-10-dry-run-post-fix-20260531T0030Z.stderr.txt`; empty.

- `DATABASE_URL=... uv run --no-sync python - <<'PY' ... company_enrichment_batch/company_enrichment_company_state/count verification ... PY`
  - Result: passed.
  - Final state: 10 `batch_complete/succeeded`.
  - Business fact table counts remained unchanged from the post-200-dry-run baseline: `company_product=336`, `company_product_evidence=1113`, `company_application_scenario=227`, `company_signal_event=617`, and `company_news_item=461`.
  - `company_enrichment_search_audit` increased from 4793 to 4845, matching `summary.query_count=52`.

### Covered

- End-to-end command wiring for the post-dry-run fixes.
- Child concurrency metadata recorded as `llm=2` and `web=2`.
- Dry-run no-write behavior for business fact tables.
- Batch finalization and company-state finalization for the selected 10 companies.
- Metric propagation for `products_with_target_customers`; the batch reported 1 target-customer product.
- Model-routing evidence stayed aligned with the spec: Lite for trusted XLSX/search hints, Pro for source judgment, financing extraction, source-product admission, and multi-source synthesis.

### Remaining

- This smoke does not replace the 200-company live bounded validation.
- Source-product target-customer coverage remains low in this sample; the target-customer count came from XLSX/team synthesis.
- `multi_source_narrative` remains the slowest observed stage in the smoke and should stay rate-limited before scaling.

## 2026-05-31 - Provider-Limiter Concurrency and 200-Company Live Bounded Validation

### Commands

- `cd apps/miroflow-agent && uv run --no-sync pytest apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py -q`
  - Result: passed, 30 tests.
  - Covered `--company-id-file`, provider limiter CLI overrides, explicit-company sample freezing, and upload-batch stage policy reporting.

- `uv run --no-sync pytest apps/miroflow-agent/tests/data_agents/company/test_enrichment_batch.py::test_mark_batch_finished_clears_stale_last_error_on_success apps/miroflow-agent/tests/data_agents/company/test_enrichment_batch.py::test_mark_company_stage_complete_updates_checkpoint_counters -q`
  - Result: passed, 2 tests.
  - Covered successful batch finalization clearing stale `last_error` and company-stage checkpoint counter persistence.

- `python -m py_compile apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/src/data_agents/company/enrichment_batch.py`
  - Result: passed.

- `DATABASE_URL=... uv run --no-sync python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py --batch-id 66e8bcda-2030-42eb-84fb-5edefff97a43 --company-id-file .agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-selected-company-ids.txt --chunk-size 25 --stage-concurrency 4 --llm-stage-concurrency 4 --web-stage-concurrency 4 --stage-subchunk-size 1 --stage-timeout-seconds 1800 --stage-retry-budget 1 --retry-backoff-seconds 1 --sleep-seconds 0.05 --official-product-max-pages 3 --source-product-limit 4000 --child-llm-concurrency 4 --child-web-concurrency 4 --provider-llm-max-concurrency 8 --provider-serper-max-concurrency 4 --skip-milvus`
  - Result: passed.
  - Batch `66e8bcda-2030-42eb-84fb-5edefff97a43` finished `succeeded`, 200 selected companies processed, 200 succeeded, 0 failed.
  - Report: `.agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-resume-provider8-subchunk1-20260531T0532Z.json`.
  - Summary: `.agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-summary-20260531.md`.
  - Stderr: `.agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-resume-provider8-subchunk1-20260531T0532Z.stderr.txt`; empty.

- `DATABASE_URL=... uv run --no-sync python - <<'PY' ... company_enrichment_batch/company_enrichment_company_state/count verification ... PY`
  - Result: passed.
  - Final state: 200 `batch_complete/succeeded`; 824 unselected imported companies remained queued.
  - Batch row: `status=succeeded`, `companies_processed=200`, `companies_succeeded=200`, `companies_failed=0`, `last_error=NULL`.
  - Post-run counts: `company_product=668`, `company_product_evidence=2167`, `company_application_scenario=402`, `company_signal_event=694`, `company_news_item=1063`, `company_enrichment_search_audit=5892`.

### Covered

- Real live bounded persistence for exactly the fixed 200-company validation sample.
- Explicit sample freezing through `--company-id-file`, preventing representative-sample drift after source coverage changes.
- Provider limiter overrides: DeepSeek max concurrency 8 and Serper max concurrency 4.
- Company-level stage subchunks through `--stage-subchunk-size 1`, improving progress visibility and resume granularity for slow LLM/web stages.
- Batch report records `provider_rate_limits`, child concurrency, stage policies, selected company IDs, residual risks, and skipped Milvus.
- Business fact tables changed through the selected live validation pipeline while unselected imported companies remained queued.
- Successful batch finalization now clears stale restart errors.

### Remaining

- `milvus_refresh` was intentionally skipped, so touched-vector refresh and RAG smoke checks remain pending under task 8.7.
- 5180 search/detail inspection remains pending under tasks 6.5 and 8.8.
- The full validation report remains incomplete until vector/RAG and 5180 evidence are added.
- Generic web source judgment and multi-source narrative still have long-tail latency; future full-scale runs should keep company-level subchunks and add finer per-query/per-source timeout reporting.

## 2026-05-31 - Generic-Web Identity Cleanup, Vector Refresh, RAG, and 5180 Inspection

### Commands

- `uv run --no-sync pytest apps/miroflow-agent/tests/data_agents/company/test_generic_source_judgment.py apps/miroflow-agent/tests/scripts/test_run_company_generic_source_judgment.py -q`
  - Result: passed, 14 tests after RED/GREEN identity-guard and trusted-short-name coverage.

- `DATABASE_URL=... uv run --no-sync python - <<'PY' ... generic-web identity guard audit ... PY`
  - Result: passed.
  - Alias-aware audit: `.agents/runs/company-scaleout-enrichment-hardening/company-generic-source-identity-guard-audit-after-3char-alias-20260531T071721Z.json`.
  - Checked 725 accepted generic-web rows, found 90 invalid rows across 56 companies.

- `DATABASE_URL=... uv run --no-sync python - <<'PY' ... generic-web identity cleanup ... PY`
  - Result: passed.
  - Cleanup artifact: `.agents/runs/company-scaleout-enrichment-hardening/company-generic-source-identity-cleanup-20260531T071848Z.json`.
  - Deleted 90 `company_news_item` rows, 187 `company_product_evidence` rows, 48 products with no remaining evidence, and 32 application scenarios.

- `DATABASE_URL=... uv run --no-sync python - <<'PY' ... post-cleanup guard audit ... PY`
  - Result: passed.
  - Artifact: `.agents/runs/company-scaleout-enrichment-hardening/company-generic-source-identity-guard-post-cleanup-audit-20260531T071910Z.json`.
  - Checked 635 remaining accepted generic-web rows, found 0 invalid rows.

- `DATABASE_URL=... uv run --no-sync python apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py --include-source-materials --skip-team --concurrency 4 ...`
  - First 56-company run was terminated after a long-tail LLM wait; 44 company summaries had already committed.
  - The stale `pipeline_run` was closed as `partial` with 44 processed and 12 failed.
  - Remaining 12-company rerun succeeded: `.agents/runs/company-scaleout-enrichment-hardening/company-post-cleanup-narrative-refresh-remaining12-20260531T074059Z.json`.
  - Verification query showed all 56 cleanup-affected companies refreshed since cleanup.

- `DATABASE_URL=... MILVUS_USE_REAL_CLIENT=1 uv run --no-sync python apps/miroflow-agent/scripts/run_milvus_backfill.py --domain company --batch-size 32 --milvus-uri apps/miroflow-agent/milvus.db --company-id ...`
  - Result: passed.
  - Artifact: `.agents/runs/company-scaleout-enrichment-hardening/company-post-cleanup-milvus-refresh-affected56-20260531T074642Z.json`.
  - 56 companies processed, 0 errors.

- `DATABASE_URL=... MILVUS_USE_REAL_CLIENT=1 FILTER_BY_QUALITY_STATUS=0 uv run --no-sync python - <<'PY' ... company RAG smoke ... PY`
  - First smoke passed 4/5; the failed `逸步科技 智能鞋垫` query was not a valid expected fact after cleanup.
  - Final smoke passed 5/5 with a corrected identity-cleanup query.
  - Artifact: `.agents/runs/company-scaleout-enrichment-hardening/company-post-cleanup-rag-smoke-pass5-20260531T074843Z.json`.

- `agent-browser open http://127.0.0.1:5180/company/COMP-17d68ddf7fd6 && agent-browser wait --load networkidle && agent-browser snapshot -i -c`
  - Result: passed.
  - OneGu detail page loaded in 5180.

- `agent-browser get text @e1`
  - Result: passed.
  - Page text no longer contained `股一科技`, `深圳市的一科技`, or `个人简介`; it retained `公司简介`, `友心`, and `积分商城`.
  - Inspection artifact: `.agents/runs/company-scaleout-enrichment-hardening/5180-company-onegu-post-cleanup-inspection-20260531.json`.
  - Screenshot: `.agents/runs/company-scaleout-enrichment-hardening/screenshots/5180-company-onegu-post-cleanup-20260531.png`.

- `uv run --no-sync pytest apps/miroflow-agent/tests/data_agents/company/test_generic_source_judgment.py apps/miroflow-agent/tests/scripts/test_run_company_generic_source_judgment.py apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py apps/miroflow-agent/tests/data_agents/company/test_enrichment_batch.py -q`
  - Result: passed, 54 tests.

- `python -m py_compile apps/miroflow-agent/src/data_agents/company/generic_source_judgment.py apps/miroflow-agent/scripts/run_company_generic_source_judgment.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/src/data_agents/company/enrichment_batch.py`
  - Result: passed.

- `openspec validate company-scaleout-enrichment-hardening --strict`
  - Result: passed.

### Covered

- Generic-web identity gating now catches near-name and wrong-legal-entity
  contamination without rejecting common trusted short brand names.
- 200-company live bounded validation now has persistence, cleanup, summary
  refresh, vector refresh, RAG smoke, and 5180 inspection evidence.
- Representative 5180 company detail pages show the intended business order and
  company-specific labels.

### Remaining

- 1024-company full dry-run/live rerun is still pending under tasks 9.5-9.9.
- The post-cleanup narrative refresh exposed the need for per-call LLM timeout,
  retry, and finer checkpoint reporting before scaling further.

## 2026-05-31 - Child LLM Concurrency, Timeout, and Retry Hardening

### Commands

- `uv run --no-sync pytest apps/miroflow-agent/tests/scripts/test_run_company_xlsx_team_synthesis.py::test_parse_args_accepts_company_and_batch_scope apps/miroflow-agent/tests/scripts/test_run_company_xlsx_team_synthesis.py::test_open_llm_client_uses_company_task_routing apps/miroflow-agent/tests/scripts/test_run_company_generic_source_judgment.py::test_parse_args_accepts_concurrency_and_checkpoint_stage apps/miroflow-agent/tests/scripts/test_run_company_signal_extract.py::test_parse_args_accepts_concurrency_and_checkpoint_stage apps/miroflow-agent/tests/scripts/test_run_company_signal_extract.py::test_open_llm_client_disables_proxy_env apps/miroflow-agent/tests/scripts/test_run_company_source_product_extract.py::test_parse_args_accepts_batch_and_llm_fallback_flags apps/miroflow-agent/tests/scripts/test_run_company_news_ingest.py::test_parse_args_accepts_concurrency_and_checkpoint_stage apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py::test_parse_args_accepts_dry_run_skip_flags apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py::test_build_stage_commands_passes_child_concurrency_and_checkpoint_stage -q`
  - RED result before implementation: failed, 9 tests, for missing child LLM timeout/retry flags, missing runner propagation, and missing OpenAI `max_retries`.
  - GREEN result after implementation: passed, 9 tests.

- `uv run --no-sync pytest apps/miroflow-agent/tests/scripts/test_run_company_signal_extract.py::test_process_news_rows_uses_configured_worker_concurrency -q`
  - RED result before implementation: failed because `_process_news_rows` did not exist.
  - GREEN result after implementation: passed, 1 test.

- `uv run --no-sync pytest apps/miroflow-agent/tests/scripts/test_run_company_xlsx_team_synthesis.py apps/miroflow-agent/tests/scripts/test_run_company_generic_source_judgment.py apps/miroflow-agent/tests/scripts/test_run_company_signal_extract.py apps/miroflow-agent/tests/scripts/test_run_company_source_product_extract.py apps/miroflow-agent/tests/scripts/test_run_company_news_ingest.py apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py apps/miroflow-agent/tests/data_agents/company/test_llm_routing.py -q`
  - Result: passed, 117 tests.

- `python -m py_compile apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py apps/miroflow-agent/scripts/run_company_generic_source_judgment.py apps/miroflow-agent/scripts/run_company_source_product_extract.py apps/miroflow-agent/scripts/run_company_signal_extract.py apps/miroflow-agent/scripts/run_company_news_ingest.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py`
  - Result: passed.

- `openspec validate company-scaleout-enrichment-hardening --strict`
  - Result: passed.

### Covered

- Upload runner now defaults child execution to `LLM=4` and `web=3`.
- Upload runner exposes `--child-llm-timeout-seconds` and
  `--child-llm-retry-budget` and passes them to every LLM-using child command.
- LLM child scripts expose matching `--llm-timeout-seconds` and
  `--llm-retry-budget` options.
- OpenAI SDK clients now receive explicit `max_retries` from Company task
  routing.
- Signal extraction now uses per-news-row worker concurrency and serializes DB
  writes after LLM extraction.

### Recommended 1024 Dry-Run Parameters

Before task 9.5 live execution, use a dry-run with these scaleout controls:

```bash
uv run --no-sync python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py \
  --batch-id <batch-id> \
  --dry-run --skip-persistence --skip-milvus \
  --chunk-size 25 \
  --stage-concurrency 4 \
  --llm-stage-concurrency 4 \
  --web-stage-concurrency 4 \
  --stage-subchunk-size 1 \
  --stage-timeout-seconds 1800 \
  --stage-retry-budget 1 \
  --retry-backoff-seconds 1 \
  --sleep-seconds 0.05 \
  --official-product-max-pages 3 \
  --source-product-limit 4000 \
  --child-llm-concurrency 4 \
  --child-web-concurrency 3 \
  --child-llm-timeout-seconds 75 \
  --child-llm-retry-budget 1 \
  --provider-llm-max-concurrency 8 \
  --provider-serper-max-concurrency 4
```

### Remaining

- The 1024-company dry-run itself remains pending under task 9.5.
- The live 1024-company rerun remains gated on dry-run review.

## 2026-05-31 - Full 1024-Company Dry-Run and Provider-Limiter Regression

### Commands

- `uv run --no-sync pytest apps/miroflow-agent/tests/data_agents/company/test_provider_rate_limit.py -k 'does_not_serialize_call_body'`
  - RED result before implementation: failed because the wrapped provider call
    body was serialized and the test observed `max_active == 1`.

- `uv run --no-sync pytest apps/miroflow-agent/tests/data_agents/company/test_provider_rate_limit.py`
  - GREEN result after implementation: passed, 4 tests.

- `uv run --no-sync python -m py_compile apps/miroflow-agent/src/data_agents/company/provider_rate_limit.py`
  - Result: passed.

- `timeout 28800 uv run --no-sync python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py --batch-id 84fd0f38-1430-4532-9787-098f2663a3ce --company-id-file .agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-company-ids-20260531T081827Z.txt --include-failed --dry-run --skip-persistence --skip-milvus --chunk-size 1024 --stage-concurrency 40 --llm-stage-concurrency 40 --web-stage-concurrency 10 --stage-subchunk-size 1 --stage-timeout-seconds 2400 --stage-retry-budget 2 --retry-backoff-seconds 2 --sleep-seconds 0.02 --official-product-max-pages 3 --source-product-limit 12000 --child-llm-concurrency 2 --child-web-concurrency 3 --child-llm-timeout-seconds 90 --child-llm-retry-budget 2 --provider-llm-max-concurrency 40 --provider-serper-max-concurrency 10`
  - Result: passed, exit code 0.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-resume-llm40-fixed-20260531T112931Z.json`.
  - Stderr:
    `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-resume-llm40-fixed-20260531T112931Z.stderr.txt`
    (0 bytes).

- `DATABASE_URL=... uv run --no-sync python - <<'PY' ... full dry-run DB status and count audit ... PY`
  - Result: passed.
  - Database batch status: `succeeded`.
  - Companies processed/succeeded/failed: 1024/1024/0.
  - Every full dry-run stage checkpointed 1024/1024 with zero failed/running
    rows.

### Evidence Artifacts

- `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-report-20260531T115737Z.md`
- `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-summary-20260531T115737Z.json`
- `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-after-counts-20260531T115737Z.json`
- `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-run-execution-plan-20260531T115737Z.md`

### Covered

- Full imported-company dry-run processed 1024/1024 XLSX-backed canonical
  companies.
- Real official-site, Yiou, PitchHub, generic web, Serper, and DeepSeek access
  was used.
- Business fact tables had zero row-count delta:
  `company_product`, `company_product_evidence`,
  `company_application_scenario`, `company_signal_event`, and
  `company_news_item`.
- `company_enrichment_search_audit` increased from 5892 to 11450 rows and is
  retained as allowed search-audit evidence.
- Effective fixed-resume runtime was 28m 6s.
- Full live-run execution plan was recorded with stage policy, checkpoint/resume
  policy, provider caps, cleanup plan, rollback plan, and go/no-go criteria.

### Remaining

- Review `llm_failure_count=56` before task 9.7 live rerun.
- Task 9.7 live 1024-company rerun remains gated.
- Task 9.8 touched-vector refresh and RAG smoke remain pending until live data
  exists.
- Task 9.9 full-run effect report remains pending.

## 2026-05-31 - Full 1024-Company Live Rerun, Vector Refresh, RAG Smoke, And 5180 Inspection

### Commands

- `timeout 28800 uv run --no-sync python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py --batch-id a1a72d01-e054-48e9-8124-f62e920ab3f7 --company-id-file .agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-company-ids-20260531T081827Z.txt --skip-milvus --chunk-size 1024 --stage-concurrency 40 --llm-stage-concurrency 40 --web-stage-concurrency 10 --stage-subchunk-size 1 --stage-timeout-seconds 2400 --stage-retry-budget 2 --retry-backoff-seconds 2 --sleep-seconds 0.02 --official-product-max-pages 3 --source-product-limit 12000 --child-llm-concurrency 2 --child-web-concurrency 3 --child-llm-timeout-seconds 90 --child-llm-retry-budget 2 --provider-llm-max-concurrency 40 --provider-serper-max-concurrency 10`
  - Result: passed, exit code 0.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-20260531T120639Z.json`.
  - Stderr:
    `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-20260531T120639Z.stderr.txt`
    (0 bytes).

- `uv run --no-sync python - <<'PY' ... full live-rerun DB status and count audit ... PY`
  - Result: passed.
  - Database batch status: `succeeded`.
  - Companies processed/succeeded/failed: 1024/1024/0.
  - All stage families reported 1024 succeeded companies, with 0 failed,
    running, or partial companies.

- `uv run --no-sync python apps/miroflow-agent/scripts/run_milvus_backfill.py --domain company --batch-size 64 --milvus-uri apps/admin-console/milvus.db --company-id ...1024 touched company IDs...`
  - First invocation result: failed before execution because zsh scalar
    expansion passed the ID list as one argument.
  - Retry result: passed with a bash array.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-admin-milvus-refresh-20260531T133200Z.json`.
  - Result details: 1024 total, 1024 processed, 0 skipped, 0 errors, 48.8
    seconds.

- `uv run --no-sync python - <<'PY' ... RetrievalService company RAG smoke ... PY`
  - Result: passed.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-rag-smoke-20260531T133320Z.json`.
  - Result details: 5 passed, 0 failed. Product, target-customer, application
    scenario, recent-financing, and profile-summary checks all hit the
    expected company at rank 1.

- Agent-browser inspection of
  `http://127.0.0.1:5180/company/COMP-54fd4dd036ff`
  - Result: passed for representative rendering checks.
  - Text snapshot:
    `.agents/runs/company-scaleout-enrichment-hardening/5180-company-metalenx-full-live-text-20260531.txt`.
  - DOM snapshot:
    `.agents/runs/company-scaleout-enrichment-hardening/5180-company-metalenx-full-live-snapshot-20260531.txt`.
  - Screenshot:
    `.agents/runs/company-scaleout-enrichment-hardening/screenshots/5180-company-metalenx-full-live-20260531.png`.

- `uv run --no-sync python - <<'PY' ... effect metrics query ... PY`
  - Result: passed.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-effect-metrics-20260531T134500Z.json`.

### Evidence Artifacts

- `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-batch-20260531T120621Z.json`
- `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-before-counts-20260531T120621Z.json`
- `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-after-counts-20260531T132516Z.json`
- `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-summary-20260531T132516Z.json`
- `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-effect-report-20260531.md`

### Covered

- Task 9.7 full 1024-company live rerun after the full dry-run gate.
- Task 9.8 touched-vector refresh and post-refresh Company RAG smoke checks.
- Task 9.9 full-run effect report.
- 5180 representative detail-page inspection using the frontend path connected
  to the real backend database and admin-console Milvus Lite store.

### Remaining

- Product target-customer coverage remains a quality-improvement item.
- Product/scenario facts remain review-gated until accepted by an operator.
- Official-site capture remains bounded by availability, anti-bot behavior,
  JavaScript rendering quality, robots, CAPTCHA, login, and paywall limits.

## 2026-05-31 - OneGu Post-collection XLSX Product/Scenario Replay

### Commands

- `uv run --no-sync pytest -n0 --no-cov apps/miroflow-agent/tests/data_agents/company/test_source_product_extractor.py apps/miroflow-agent/tests/scripts/test_run_company_xlsx_team_synthesis.py apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py -q`
  - Result: passed, 59 tests.

- `DATABASE_URL=... uv run --no-sync python apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py --company-id COMP-17d68ddf7fd6 --include-source-materials --skip-team --skip-narrative --concurrency 1 --llm-timeout-seconds 90 --llm-retry-budget 1 --log-level INFO`
  - Result: passed.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/onegu-post-collection-product-replay-20260531T153722Z.json`.
  - Result details: 1 company processed, 1 product synthesized/written, 8
    scenarios synthesized/written, 0 product-synthesis failures, fallback model
    `deepseek-v4-pro`.

- `uv run --no-sync python - <<'PY' ... OneGu DB/API count verification ... PY`
  - Result: passed.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/onegu-api-ui-verification-20260531T154026Z.json`.
  - Result details: both `http://127.0.0.1:18188/api/company/...` and
    `http://127.0.0.1:5180/api/company/...` returned 1 product and 8
    application scenarios.

- `agent-browser open http://127.0.0.1:5180/company/COMP-17d68ddf7fd6 && agent-browser wait --text '友心积分商城' && agent-browser snapshot -s 'body' -d 8`
  - Result: passed.
  - Page text contained the `Product`, `Product name`, `Youxin points mall`,
    `Application scenarios`, `Improve user stickiness`, company profile, and
    technology-route sections.
  - Screenshot:
    `.agents/runs/company-scaleout-enrichment-hardening/screenshots/onegu-company-detail-products-20260531.png`.

- `DATABASE_URL=... uv run --no-sync python apps/miroflow-agent/scripts/run_milvus_backfill.py --domain company --company-id COMP-17d68ddf7fd6 --batch-size 1 --milvus-uri apps/admin-console/milvus.db --log-level INFO`
  - Result: passed.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/onegu-milvus-refresh-20260531T154006Z.json`.
  - Result details: 1 company processed, 0 skipped, 0 errors.

- `uv run --no-sync ruff check apps/miroflow-agent/src/data_agents/company/source_product_extractor.py apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/tests/data_agents/company/test_source_product_extractor.py apps/miroflow-agent/tests/scripts/test_run_company_xlsx_team_synthesis.py apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py`
  - Result: passed.

- `python -m py_compile apps/miroflow-agent/src/data_agents/company/source_product_extractor.py apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py`
  - Result: passed.

### Covered

- Task 10.1 regression coverage for the OneGu-style XLSX-only product/scenario
  case.
- Task 10.2 post-collection XLSX-baseline product/scenario extraction.
- Task 10.3 `deepseek-v4-pro` product fallback routing and diagnostics.
- Task 10.4 OneGu replay, persistence verification, 5180 verification, and
  single-company vector refresh.

### Remaining

- The fix should be exercised in the next bounded/full company rerun to improve
  the remaining XLSX-only product/scenario long tail.

## 2026-05-31 - All-company Post-collection Product/Scenario Coverage

### Commands

- `DATABASE_URL=... uv run --no-sync python - <<'PY' ... baseline product/scenario counts ... PY`
  - Result: passed.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/all-company-product-scenario-baseline-20260531T160624Z.json`.
  - Baseline details: 1024 resolved companies, 667 companies with products, 342
    companies with standalone application scenarios, 357 XLSX-described
    companies without products, and 682 without standalone scenarios.

- `DATABASE_URL=... COMPANY_DEEPSEEK_MAX_CONCURRENCY=8 uv run --no-sync python apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py --include-source-materials --skip-team --skip-narrative --concurrency 12 --llm-timeout-seconds 90 --llm-retry-budget 1`
  - Result: inner batch command reported status 0.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/all-company-post-collection-product-replay-20260531T160719Z.json`.
  - Result details: 1024/1024 companies processed, 1596 products written, 1513
    scenarios written, 42 product-synthesis parse failures, 0 company errors.

- `DATABASE_URL=... COMPANY_DEEPSEEK_MAX_CONCURRENCY=4 uv run --no-sync python apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py --company-id ...42 failed IDs... --include-source-materials --skip-team --skip-narrative --concurrency 4 --llm-timeout-seconds 120 --llm-retry-budget 2`
  - Result: inner batch command reported status 0.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/all-company-post-collection-product-failure-retry-20260531T162332Z.json`.
  - Result details: 42/42 companies processed, 176 products written, 223
    scenarios written, 0 product-synthesis failures.

- `DATABASE_URL=... COMPANY_DEEPSEEK_MAX_CONCURRENCY=6 uv run --no-sync python apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py --company-id ...373 residual IDs... --include-source-materials --skip-team --skip-narrative --concurrency 6 --llm-timeout-seconds 120 --llm-retry-budget 2`
  - Result: inner batch command reported status 0.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/all-company-product-scenario-residual-replay-20260531T162908Z.json`.
  - Result details: 373/373 companies processed, 884 products written, 316
    scenarios written, 0 product-synthesis failures.

- `DATABASE_URL=... COMPANY_DEEPSEEK_MAX_CONCURRENCY=6 uv run --no-sync python apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py --company-id ...264 residual IDs... --include-source-materials --skip-team --skip-narrative --concurrency 6 --llm-timeout-seconds 120 --llm-retry-budget 2`
  - Result: inner batch command reported status 0.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/all-company-scenario-derivation-residual-replay-20260531T163901Z.json`.
  - Result details: 264/264 companies processed, 630 products written, 41
    scenarios written, 0 product-synthesis failures.

- `DATABASE_URL=... uv run --no-sync python - <<'PY' ... final product/scenario counts and residual samples ... PY`
  - Result: passed.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/all-company-product-scenario-final-counts-20260531T164524Z.json`.
  - Final details: 1024 resolved companies, 4096 product rows, 1003 companies
    with non-rejected products, 2993 standalone scenario rows, 775 companies
    with non-rejected standalone scenarios, 21 companies without products, and
    249 companies without standalone scenarios.

- `DATABASE_URL=... uv run --no-sync python apps/miroflow-agent/scripts/run_milvus_backfill.py --domain company --batch-size 64 --milvus-uri apps/admin-console/milvus.db --log-level INFO`
  - Result: passed.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/all-company-product-scenario-milvus-refresh-20260531T164601Z.json`.
  - Result details: 1024 companies processed, 0 skipped, 0 errors.

- `uv run --no-sync python - <<'PY' ... 5180 company API smoke for OneGu and Wisson/万勋 ... PY`
  - Result: passed.
  - Output:
    `.agents/runs/company-scaleout-enrichment-hardening/all-company-product-scenario-api-smoke-20260531T164738Z.json`.
  - Result details: OneGu returned 1 product and 8 scenarios; Wisson/万勋
    returned 1 product and 2 scenarios through the 5180 API path.

- `uv run --no-sync pytest -n0 --no-cov apps/miroflow-agent/tests/data_agents/company/test_source_product_extractor.py apps/miroflow-agent/tests/scripts/test_run_company_xlsx_team_synthesis.py apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py -q`
  - Result: passed, 62 tests.

- `uv run --no-sync ruff check apps/miroflow-agent/src/data_agents/company/source_product_extractor.py apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/tests/data_agents/company/test_source_product_extractor.py apps/miroflow-agent/tests/scripts/test_run_company_xlsx_team_synthesis.py apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py`
  - Result: passed.

- `python -m py_compile apps/miroflow-agent/src/data_agents/company/source_product_extractor.py apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py`
  - Result: passed.

### Covered

- All 1024 resolved XLSX-backed companies were processed by the
  post-collection product/scenario extractor.
- The initial JSON-truncation failure class was repaired by increasing the LLM
  fallback output budget and recording parse diagnostics.
- The service/solution/core-technology offering gap was reduced with a broader
  source-grounded LLM prompt.
- Product-level application scenarios now produce standalone scenario rows when
  the LLM omits the separate `scenarios` array.
- Company vectors were refreshed for all 1024 companies after persistence.

### Remaining

- 21 companies still have no non-rejected product after all retries.
- 249 companies still have no standalone scenario rows after all retries.
- These residuals are not pipeline failures; they are recorded as source or
  extraction-quality residuals for later manual/source-enrichment review.
