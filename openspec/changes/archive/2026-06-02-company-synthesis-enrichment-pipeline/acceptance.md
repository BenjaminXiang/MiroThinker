## Acceptance Evidence

### 2026-05-29 - Company upload processing status visibility

Requirement coverage:
- Pipeline run detail payloads now include upload-scoped `company_enrichment_batch` rows with status, current stage, total/selected/processed/succeeded/failed counts, timestamps, and last error.
- The admin pipeline detail page renders a localized `企业增强处理状态` section for company enrichment batches.
- The detail page auto-refreshes while the pipeline run or any upload-scoped company enrichment batch is queued or running.

Verification:
- `cd apps/admin-console && .venv/bin/python -m pytest tests/test_pipeline_runs_api.py::test_get_pipeline_run_returns_company_enrichment_batch_status -q` -> RED before implementation, then passed.
- `cd apps/admin-console/frontend && npm test -- --run src/pages/PipelineRuns.test.tsx` -> RED before implementation, then passed, 2 tests.
- `cd apps/admin-console && .venv/bin/python -m pytest tests/test_pipeline_runs_api.py tests/test_upload_pipeline_trigger.py -q` -> passed, 26 tests.
- `cd apps/admin-console/frontend && npm test -- --run src/pages/PipelineRuns.test.tsx src/pages/RecordDetail.test.tsx src/pages/DomainList.test.tsx` -> passed, 6 tests.
- `cd apps/admin-console/frontend && npm run build` -> passed.

Notes:
- Validation did not run a full apply upload of `docs/企业总表.xlsx`; only the previously verified dry-run path is used for safety because a full apply would schedule enrichment for thousands of company rows.

### 2026-05-28 - Spec and DeepSeek runtime baseline

Requirement coverage:
- `company-synthesis-enrichment-pipeline`: proposal, design, specs, and tasks define the upload-scoped XLSX baseline, source-tiered synthesis, generic ReAct web search, official website capture, product/scenario/customer extraction, financing updates, team structuring, long profiles, audit, and touched-company vector refresh.
- `company-enrichment-source-closure`: spec delta clarifies generic Serper identity-only query generation, `gl="cn"` / `hl="zh-cn"`, and LLM source judgment before generic web material enters synthesis.
- LLM runtime baseline: shared LLM profile resolver supports `deepseek-v4-pro` while preserving `deepseek-v4-flash` compatibility; Hydra default LLM config points at the OpenAI-compatible DeepSeek endpoint; credentials are loaded from ignored environment files or process environment.

Verification:
- `openspec validate company-synthesis-enrichment-pipeline --strict` -> passed.
- `cd apps/miroflow-agent && uv run pytest tests/data_agents/professor/test_llm_profiles.py -q` -> 13 passed.
- `cd apps/miroflow-agent && uv run python <hydra-compose-smoke>` -> provider `openai`, model `deepseek-v4-pro`, base URL `https://api.deepseek.com`.
- `cd apps/miroflow-agent && python <deepseek-openai-sdk-smoke>` -> requested model `deepseek-v4-pro`, response model `deepseek-v4-pro`, finish reason `stop`, reasoning output absent in non-thinking mode, response excerpt `DeepSeek V4 Pro OK`.

Notes:
- The first historical DeepSeek smoke attempt failed before reaching the API because the local process inherited a SOCKS proxy without `socksio`; successful smoke checks use `httpx.Client(trust_env=False)`, matching existing project patterns for avoiding ambient proxy interference.
- API keys are intentionally not written into committed files or acceptance evidence.

### 2026-05-28 - DeepSeek V4 Pro runtime hardening

Requirement coverage:
- The shared LLM profile resolver now defaults to `deepseek-v4-pro` when no `LLM_PROFILE` override is provided.
- The provider-specific non-thinking request body is centralized: DeepSeek v4 uses `{"thinking": {"type": "disabled"}}`; legacy Star/Gemma/Qwen-compatible callers keep `chat_template_kwargs.enable_thinking=false`.
- Core OpenAI-compatible runtime calls disable DeepSeek v4 thinking by default.
- Current company enrichment entrypoints and admin chat synthesis/classification use the default configured profile instead of hardcoding `gemma4`.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/professor/test_llm_profiles.py tests/llm/test_openai_client_extra_body.py tests/scripts/test_run_company_signal_extract.py -q` -> passed, 26 tests.
- `cd apps/admin-console && uv run --no-sync pytest tests/test_chat_v1.py tests/test_chat_classifier_c_type.py tests/test_chat_classifier_b_g_tune.py -q` -> passed, 37 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_narrative_backfill.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_source_product_quality_audit.py -q` -> passed, 55 tests.
- `cd apps/miroflow-agent && uv run python <deepseek-openai-sdk-smoke-via-shared-resolver>` -> resolved profile `deepseekv4pro`, requested model `deepseek-v4-pro`, response model `deepseek-v4-pro`, finish reason `stop`, reasoning output absent, response excerpt `DeepSeek V4 Pro OK`.

Notes:
- A live smoke check found that the ignored local `.env` still overrode the model to `deepseek-v4-flash`; that local override was corrected to `deepseek-v4-pro`. No credential value was logged.

### 2026-05-28 - Company base readiness and detail contract slice

Requirement coverage:
- XLSX baseline readiness now has regression coverage for resolved meaningful rows, sparse rows, and unresolved identity blockers.
- Canonical XLSX import writes a `company.quality_status` candidate from XLSX baseline completeness independently from external product, scenario, or web enrichment review state.
- Company detail API selects `company.profile_summary` and `company.technology_route_summary` and returns those synthesized fields before falling back to latest snapshot `description` and `business`.
- Company detail UI renders Basic Information before Products, Application Scenarios, and Recent Events; company summary labels use the company-domain label; primary product cards expose only the six business-facing product fields.
- Serper payload tests assert `hl="zh-cn"` and `gl="cn"`; the ordinary generic query test now rejects the previous default news/product/funding tail.

Verification:
- `cd apps/admin-console && uv run --no-sync pytest tests/test_data_api_quality_status.py -q` -> passed, 6 tests.
- `cd apps/admin-console/frontend && npm test -- --run src/pages/RecordDetail.test.tsx` -> passed, 3 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_canonical_import_readiness.py tests/data_agents/company/test_serper_news_connector.py -q` -> passed, 24 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_import_xlsx.py tests/data_agents/company/test_release.py -q` -> passed, 8 tests.
- `openspec validate company-synthesis-enrichment-pipeline --strict` -> passed.

Remaining gaps:
- Generic source-discovery still needs trusted LLM alias extraction and upload-batch wiring for the bounded ReAct source-judgment runner.
- The full multi-source synthesis, official-site capture, financing update, team structuring, touched-company vector refresh, 100-company validation, and 5180 manual inspection remain open.

### 2026-05-28 - Baseline blocker persistence and summary serialization slice

Requirement coverage:
- Upload enrichment batches now run a `baseline_readiness` stage before external source capture.
- The stage persists per-company blockers in `company_enrichment_company_state.stage_status`, including unresolved identity, missing latest snapshot, missing company name, and missing meaningful XLSX baseline fields.
- The stage report exposes checked, ready, blocked, and blocker-count summaries without stopping product, scenario, or signal-event review states from remaining independently reviewable.
- Company summary edits now write synthesized `profile_summary` and `technology_route_summary` to `company`, not to XLSX snapshot `description` or `business`.
- Company release generation accepts synthesized summaries and uses them before rule-based XLSX fallback summaries.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py -q` -> passed, 6 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py -q` -> passed, 5 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_release.py -q` -> passed, 4 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_canonical_import_readiness.py tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_release.py -q` -> passed, 19 tests.
- `cd apps/admin-console && uv run --no-sync pytest tests/test_domains_postgres.py -q -k "company_summary or company_quality_status"` -> passed, 2 tests.
- `cd apps/admin-console && uv run --no-sync pytest tests/test_data_api_quality_status.py tests/test_domains_postgres.py -q -k "company"` -> passed, 16 tests.

Remaining gaps:
- The batch still needs XLSX/team synthesis, official-site source capture, generic ReAct source judgment integration, multi-source synthesis persistence, financing update, touched-company vector refresh, 100-company validation, and 5180 manual inspection.

### 2026-05-28 - Long narrative and technology summary slice

Requirement coverage:
- Company narrative synthesis now targets 500-900 Chinese characters for `profile_summary` when sufficient material exists.
- Sparse source material returns a `sparse_material` blocker instead of padding unsupported content.
- The narrative prompt includes XLSX `description` and `business`, structured products, official materials, Yiou materials, PitchHub/36Kr materials, and accepted generic web materials.
- Technology-route synthesis uses the same source-material bundle so products, technical tags, target customers, application scenarios, and source tiers can shape the technology or production-line summary without overwriting original XLSX fields.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_narrative_enrichment.py -q` -> passed, 9 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_narrative_enrichment.py tests/scripts/test_run_company_narrative_backfill.py -q` -> passed, 15 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_narrative_enrichment.py tests/company/test_team_parser.py -q` -> passed, 23 tests.
- `cd apps/miroflow-agent && python -m compileall -q src/data_agents/company/narrative_enrichment.py` -> passed.

Remaining gaps:
- Upload-batch multi-source synthesis wiring is still pending; this slice updates the synthesis module contract and tests, not the full batch writer.

### 2026-05-28 - Structured team persistence slice

Requirement coverage:
- Added reversible V036 migration columns on `company_team_member` for structured background, experience highlights, relevance, confidence, evidence span, and preserved raw team text.
- Extended the canonical `CompanyTeamMember` model to expose those structured fields.
- Added an idempotent structured-team writer that updates existing `company_id` + `snapshot_id` + `member_order` rows or inserts missing rows.
- XLSX import now persists fallback structured team fields through the same writer, preserving existing `team_raw` parsing behavior while making structured team highlights available for later synthesis and vectorization.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/storage/test_v036_migration.py tests/storage/test_alembic_revision_lineage.py -q` -> passed, 3 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_structured_business_models.py tests/data_agents/company/test_team_persistence.py tests/company/test_team_parser.py -q` -> passed, 18 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_canonical_import_readiness.py tests/data_agents/company/test_import_xlsx.py tests/postgres/test_canonical_import_xlsx.py -q` -> passed, 9 tests; skipped 3 Postgres integration tests because no `DATABASE_URL_TEST` or `DATABASE_URL` was set.

Remaining gaps:
- Upload-batch LLM team structuring is still not wired as a standalone stage; this slice provides the schema and writer path.

### 2026-05-28 - Source query and site adapter slice

Requirement coverage:
- Generic Serper identity queries now expand from canonical name to registered name, XLSX company name, trusted project or short name, and stored aliases without appending funding, product, founder, recruiting, job, or industry keyword tails.
- The company news ingest script now selects registered name, aliases, and latest XLSX company name, then fetches ordinary Serper results once per generated identity query and records per-query diagnostics.
- Yiou and 36Kr/PitchHub site-filter adapters remain able to broaden recall with alias, alias plus founder, project name, and distinctive keywords, while tests verify source domain/path checks and company identity checks still gate acceptance.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_serper_news_connector.py tests/scripts/test_run_company_news_ingest.py -q` -> passed, 49 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_yiou_adapter.py -q` -> passed, 12 tests.

Remaining gaps:
- A dedicated trusted LLM alias extractor for generic web search is still pending; the current generic path uses stored/company-derived identity aliases and excludes non-identity query tails.
- The bounded ReAct source-judgment workflow and generic source-material acceptance remain open.

### 2026-05-28 - Generic ReAct source judgment slice

Requirement coverage:
- Added a bounded internal generic-web source workflow with inspectable `judge_source` and `fetch_webpage` steps and injectable LLM judgment/fetch tools.
- Snippet-only competitor results are rejected without fetching the page body.
- Potentially relevant but insufficient snippets trigger bounded full-page fetch and a second source judgment.
- Accepted generic source material requires both target-company identity and fact-attribution confirmation; otherwise the result is rejected with an explicit reason and evidence span.
- Recruiting and job-intent pages are excluded before LLM judgment.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_generic_source_judgment.py -q` -> passed, 4 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_generic_source_judgment.py tests/data_agents/company/test_serper_news_connector.py tests/scripts/test_run_company_news_ingest.py -q` -> passed, 53 tests.

Remaining gaps:
- The generic ReAct workflow is implemented as a tested core runner, but it is not yet wired into the upload enrichment batch persistence path.
- `extract_company_facts` is represented by the accepted source-material contract in this slice; downstream multi-source product/scenario/funding/team extraction remains pending.

### 2026-05-28 - XLSX product and scenario synthesis slice

Requirement coverage:
- Added an XLSX source-material synthesis entry point that combines trusted XLSX project name, description, business, and team raw text.
- The XLSX synthesis path returns products with product name, product description, product category, technical tags, target customers, and application scenarios when supported by product material.
- Industry-only material does not create products, scenarios, or inferred target customers.
- Existing Yiou/PitchHub/official-source extraction behavior remains covered by the full source-product extractor test file.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_source_product_extractor.py::test_xlsx_synthesis_uses_description_business_and_project_as_source_material tests/data_agents/company/test_source_product_extractor.py::test_xlsx_synthesis_does_not_invent_target_customers_from_industry_only -q` -> passed, 2 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_source_product_extractor.py tests/data_agents/company/test_structured_business_models.py -q` -> passed, 12 tests.

Remaining gaps:
- The source-material persistence helper is implemented, but the upload batch still needs to call it as a stage.

### 2026-05-28 - Product, scenario, and source-tier evidence slice

Requirement coverage:
- Added a source-material model for synthesis inputs with source ID, source tier, URL, title, captured text, capture time, trust reason, and optional source-judgment fields.
- Synthesized products and application scenarios now flow through the existing `upsert_company_product` / `company_product_evidence` and `upsert_company_application_scenario` / `company_application_scenario_evidence` writers.
- Added V037 to preserve `source_tier` on product and scenario evidence rows.
- The quality gate promotes explicit XLSX and official-site products/scenarios to `ready` while keeping generic-web-only facts review-gated unless source judgment and fact attribution are strong.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_source_product_extractor.py::test_persist_synthesized_products_and_scenarios_uses_upsert_paths_and_quality_gate tests/data_agents/company/test_source_product_extractor.py::test_generic_web_only_products_remain_review_gated_without_strong_judgment -q` -> RED before implementation, then passed, 2 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_official_product_capture.py::test_product_evidence_preserves_source_tier tests/data_agents/company/test_official_product_capture.py::test_application_scenario_evidence_preserves_source_tier tests/storage/test_v037_migration.py tests/storage/test_alembic_revision_lineage.py -q` -> RED before implementation, then passed, 5 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_source_product_extractor.py tests/data_agents/company/test_structured_business_models.py tests/data_agents/company/test_official_product_capture.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_official_product_capture.py -q` -> passed, 38 tests.
- `python -m compileall -q apps/miroflow-agent/src/data_agents/company/source_product_extractor.py apps/miroflow-agent/src/data_agents/company/official_product_capture.py apps/miroflow-agent/alembic/versions/V037_add_company_evidence_source_tier.py` -> passed.

Remaining gaps:
- Yiou and PitchHub continue to provide high-quality source material, but this slice only promotes owned/baseline (`xlsx`, `official_site`) facts automatically; third-party and generic facts still depend on identity/source judgment and later audit policy.
- Upload batch wiring for this persistence helper remains pending.

### 2026-05-28 - Official-site source material capture slice

Requirement coverage:
- Official website capture now selects bounded same-host source-material URLs across homepage, about, product, service, solution, case, customer, and news sections.
- Official capture rejects external links, recruiting paths, domain-sale or JavaScript placeholder pages, and recruiting-only pages.
- Captured official pages become high-trust `official_site` `CompanySourceMaterial` records with source ID, URL, title, captured text, capture time, and trust reason.
- The official capture script dry-run report now records `official_pages_captured` and serialized `source_materials` for downstream validation counts and synthesis inputs.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_official_product_capture.py::test_select_candidate_material_urls_covers_core_official_sections tests/data_agents/company/test_official_product_capture.py::test_extract_official_source_materials_filters_noise_and_marks_high_trust -q` -> RED before implementation, then passed, 2 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_official_product_capture.py::test_capture_official_materials_for_record_fetches_core_sections -q` -> RED before implementation, then passed, 1 test.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_official_product_capture.py::test_cli_dry_run_report_includes_official_source_materials -q` -> passed, 1 test.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_official_product_capture.py tests/data_agents/company/test_yiou_adapter.py tests/scripts/test_run_company_official_product_capture.py -q` -> passed, 31 tests.
- `python -m compileall -q apps/miroflow-agent/src/data_agents/company/source_material.py apps/miroflow-agent/src/data_agents/company/source_product_extractor.py apps/miroflow-agent/src/data_agents/company/official_product_capture.py apps/miroflow-agent/scripts/run_company_official_product_capture.py` -> passed.

Remaining gaps:
- Upload batch orchestration still needs to wire official source materials into the multi-source synthesis stage and persisted per-company audit.

### 2026-05-28 - Team raw LLM structuring slice

Requirement coverage:
- Added an LLM-backed `team_raw` structuring entry point that outputs name, role, background, experience highlights, company/product relevance, confidence, evidence span, and preserved raw text.
- The structuring prompt explicitly forbids inventing education, employer, title, or founder facts outside the supplied XLSX team text.
- A source-grounded fallback remains available when no LLM client is provided or the LLM call fails.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/company/test_team_parser.py -q` -> passed, 14 tests.

Remaining gaps:
- Upload-batch LLM team structuring is still not wired as a standalone stage; schema and writer support are covered by the team persistence slice.

### 2026-05-28 - Company vector text enrichment slice

Requirement coverage:
- Company vector text includes long profile and technology summary when present.
- Product category, technical tags, target customers, application scenarios, structured team highlights, and normalized funding details are included in composed retrieval text.
- Company Milvus backfill and company/patent retrieval focused tests still pass.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_vectorizer.py::test_compose_company_text_includes_team_highlights_and_funding_details -q` -> passed.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_vectorizer.py tests/scripts/test_run_milvus_backfill_company.py tests/data_agents/service/test_retrieval_company_patent.py -q` -> passed, 22 tests.

Remaining gaps:
- Upload enrichment still needs to refresh only touched company vectors after persistence.
- Chat-level product/scenario/funding smoke checks remain pending until the upload batch writes new enriched data.

### 2026-05-28 - Generic Serper trusted identity-alias slice

Requirement coverage:
- Generic Serper source discovery remains identity-only: canonical name, registered name, XLSX company name, project or short name, stored aliases, and trusted LLM identity aliases are the only query terms.
- LLM search hints now separate `identity_aliases` from broader site-search `aliases`; Yiou and PitchHub can still use product or founder terms for recall, while ordinary generic Serper only consumes `identity_aliases`.
- Product aliases, founder-name combinations, industry words, financing/news/product tails, site filters, and recruiting/job terms are not accepted as generic identity queries.
- Search audit payloads preserve `identity_aliases` alongside broader hints so operators can explain why a generic query was used.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_yiou_adapter.py::test_yiou_llm_hint_extraction_parses_alias_founder_and_keywords -q` -> RED before implementation, then passed, 1 test.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_news_ingest.py::test_fetch_generic_serper_includes_only_llm_trusted_identity_aliases -q` -> RED before implementation, then passed, 1 test.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_serper_news_connector.py tests/data_agents/company/test_yiou_adapter.py tests/scripts/test_run_company_news_ingest.py tests/data_agents/company/test_enrichment_batch.py -q` -> passed, 68 tests.
- `python -m compileall -q apps/miroflow-agent/src/data_agents/company/news_connectors/serper.py apps/miroflow-agent/src/data_agents/company/news_connectors/iyiou.py apps/miroflow-agent/scripts/run_company_news_ingest.py apps/miroflow-agent/src/data_agents/company/enrichment_batch.py` -> passed.

Remaining gaps:
- Generic source judgment and ReAct workflow tests were already green, but upload-batch wiring and 100-company validation still need to prove this query policy in the end-to-end path.

### 2026-05-28 - Financing signals and recent dynamics slice

Requirement coverage:
- Accepted source-backed financing material now normalizes `financing_round`, `amount_raw`, numeric `amount_cny_wan` when explicitly parseable, `investors`, `financing_summary`, source adapter, and source URL inside `company_signal_event.event_subject_normalized`.
- Signal extraction compares external financing evidence with XLSX latest-funding baseline fields loaded from the latest snapshot. Newer evidence is written as an active `company_signal_event` with `funding_freshness='newer_than_xlsx_baseline'` and an `xlsx_baseline` record; the XLSX snapshot fields are not overwritten.
- Same-date conflicting financing rounds or LLM-marked uncertain facts are review-gated by `status='needs_review'` with `review_reason` and source URL preserved.
- Added V038 so `company_signal_event.status` can store `needs_review` in addition to existing active/deprecated/deduped statuses.
- The company domain detail/release payload now includes recent-event `status` and uses the news source URL with fallback to normalized source evidence.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_signal_event_extractor.py::test_extract_signal_events_normalizes_source_backed_funding_fields tests/data_agents/company/test_signal_event_extractor.py::test_extract_signal_events_review_gates_conflicting_funding_baseline -q` -> RED before implementation, then passed, 2 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_signal_extract.py::test_insert_signal_events_uses_dedup_conflict -q` -> RED before implementation, then passed, 1 test.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/storage/test_v038_migration.py tests/storage/test_alembic_revision_lineage.py -q` -> RED before implementation, then passed, 3 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_signal_event_extractor.py tests/scripts/test_run_company_signal_extract.py tests/storage/test_v038_migration.py tests/storage/test_alembic_revision_lineage.py -q` -> passed, 24 tests.
- `cd apps/admin-console && uv run --no-sync pytest tests/test_domains_postgres.py::test_company_released_object_exposes_products_events_and_source_evidence tests/test_data_api.py -q` -> passed, 2 tests and 7 skips.
- `python -m compileall -q apps/miroflow-agent/src/data_agents/company/signal_event_extractor.py apps/miroflow-agent/scripts/run_company_signal_extract.py apps/miroflow-agent/alembic/versions/V038_allow_company_signal_event_needs_review.py apps/admin-console/backend/api/domains.py` -> passed.

Remaining gaps:
- The upload-batch runner still needs to call the financing extraction stage as part of the upload-scoped orchestration and include funding-event counts in the 100-company validation report.

### 2026-05-28 - Upload batch flags and stale-run cleanup slice

Requirement coverage:
- Company XLSX upload already imports the XLSX baseline, creates a `company_enrichment_batch`, inserts per-company state rows, and schedules `run_company_upload_enrichment_batch.py` as a detached subprocess instead of blocking the upload response on all enrichment stages.
- The upload batch runner now exposes explicit `--dry-run`, `--skip-live-web`, `--skip-official-site`, `--skip-yiou-pitchhub`, `--skip-generic-serper`, `--skip-persistence`, `--skip-milvus`, and `--stale-after-minutes` controls.
- Dry-run or skip-persistence mode passes `--dry-run` to child scripts that support it and suppresses Milvus refresh.
- Stale running enrichment batches and company state rows are failed with `stale_running_timeout`, so abandoned runs do not remain `running` indefinitely.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py::test_close_stale_running_enrichment_batches_fails_abandoned_rows -q` -> RED before implementation, then passed, 1 test.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py::test_parse_args_accepts_dry_run_skip_flags tests/scripts/test_run_company_upload_enrichment_batch.py::test_build_stage_commands_respects_dry_run_and_skip_flags -q` -> RED before implementation, then passed, 2 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py -q` -> passed, 14 tests.
- `cd apps/admin-console && uv run --no-sync pytest tests/test_upload_pipeline_trigger.py -q` -> passed, 13 tests.
- `python -m compileall -q apps/miroflow-agent/src/data_agents/company/enrichment_batch.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/admin-console/backend/api/upload.py` -> passed.

Remaining gaps:
- The runner still needs explicit upload-stage coverage for XLSX/team synthesis, official source-material capture naming, generic Serper ReAct judged-material persistence, multi-source synthesis input/output audit, and the full miss-reason enum required for 8.2, 8.4, and 8.5.

### 2026-05-28 - Upload batch miss-reason closure slice

Requirement coverage:
- Batch/search audit miss reasons now use the required operational enum values: `no_results`, `all_results_rejected`, `fetch_failed`, `llm_rejected`, `synthesis_no_facts`, and `persist_failed`.
- Source fetch errors are normalized to `fetch_failed` instead of the older `source_fetch_error` string.
- Non-search stages now produce per-company miss reasons: signal extraction with no events becomes `llm_rejected`, product/scenario extraction with no facts becomes `synthesis_no_facts`, and failed persistence-like stages become `persist_failed`.
- These reasons flow through `mark_company_stage_complete(..., miss_reason=...)`, so they remain visible in `company_enrichment_company_state` and downstream admin diagnostics.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py::test_infer_miss_reason_covers_operational_reason_enum -q` -> RED before implementation, then passed, 1 test.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py::test_miss_reason_by_company_covers_non_search_stage_failures -q` -> RED before implementation, then passed, 1 test.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py -q` -> passed, 16 tests.
- `python -m compileall -q apps/miroflow-agent/src/data_agents/company/enrichment_batch.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py` -> passed.

Remaining gaps:
- 8.2 and 8.4 remain open because generic ReAct judged-material persistence and full synthesis input/output audit still need upload-batch integration.

### 2026-05-28 - Touched-company Milvus refresh slice

Requirement coverage:
- Company Milvus backfill supports `--company-id` filters and restricts SQL to those IDs.
- Upload enrichment builds `milvus_refresh` commands with the current chunk's touched company IDs, avoiding a default 1024-company refresh.
- Local file-backed Milvus URI handling remains explicit and test-covered.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_milvus_backfill_company.py tests/scripts/test_run_company_upload_enrichment_batch.py::test_build_stage_commands_scope_every_stage_to_company_ids tests/scripts/test_run_company_upload_enrichment_batch.py::test_build_stage_commands_passes_local_milvus_uri_as_cli_arg -q` -> passed, 11 tests.
- `python -m compileall -q apps/miroflow-agent/scripts/run_milvus_backfill.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py` -> passed.

Remaining gaps:
- Chat/RAG product, scenario, target-customer, and recent-funding smoke checks remain pending until bounded validation writes refreshed company payloads.

### 2026-05-28 - Stage-level synthesis audit partial slice

Requirement coverage:
- Upload batch company stage status now stores normalized stage details for synthesis/persistence stages.
- `source_product_extract` records synthesis inputs, produced product/scenario counts, rejected or empty LLM fallback counts, and persistence outcome.
- `signal_extract` and `official_product_capture` record analogous produced-fact and rejection/error counters.
- Site-search stages already record query-level audit rows; this slice does not claim generic ReAct snippet/fetch/source-judgment audit completion.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py::test_stage_details_capture_synthesis_and_persistence_audit -q` -> RED before implementation, then passed, 1 test.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py -q` -> passed, 17 tests.
- `python -m compileall -q apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py` -> passed.

Remaining gaps:
- 8.4 remains open because generic ReAct snippet sufficiency, fetch attempts, source judgment, and accepted/rejected generic source material audit still need upload-batch integration.

### 2026-05-28 - DeepSeek V4 Pro ambient-proxy runtime smoke

Requirement coverage:
- The ignored local `apps/miroflow-agent/.env` now aligns all DeepSeek rollout model selectors with `deepseek-v4-pro`, including `DEEPSEEK_MODEL`, `LLM_PROFILE`, `LOCAL_LLM_MODEL`, and `ONLINE_LLM_MODEL`.
- The core OpenAI-compatible runtime client now creates sync and async HTTP clients with `trust_env=false`, so ambient proxy variables such as `ALL_PROXY=socks5://...` do not break LLM startup when optional SOCKS dependencies are absent.
- A live smoke check through the repository `OpenAIClient` reached DeepSeek `deepseek-v4-pro` in non-thinking mode without logging credentials.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/llm/test_openai_client_extra_body.py::test_openai_client_ignores_ambient_proxy_env -q` -> RED before implementation, then passed, 1 test.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/professor/test_llm_profiles.py tests/llm/test_openai_client_extra_body.py -q` -> passed, 18 tests.
- `source apps/miroflow-agent/.env && uv run python <deepseek-openai-client-smoke>` -> response model `deepseek-v4-pro`, finish reason `stop`, response `OK`, reasoning output absent, prompt tokens `19`, completion tokens `1`.

### 2026-05-28 - Upload batch stage and generic-source audit closure

Requirement coverage:
- Upload enrichment batches now include baseline readiness, XLSX/team synthesis, official-site capture, Yiou search, PitchHub search, generic ReAct source judgment, source-product synthesis/persistence, signal extraction, and touched-company Milvus refresh stages.
- The XLSX/team stage generates company narrative and structured team output from the trusted XLSX baseline before external web enrichment.
- The generic ReAct stage runs identity-only Serper discovery, records query counts, result counts, snippet judgments, fetch attempts, source judgments, accepted/rejected source material, and writes accepted generic-web pages as source-backed material for downstream synthesis.
- Stage details now expose synthesis inputs, produced facts, rejected or sparse facts, persistence outcomes, source-discovery audit rows, and stage-level miss reasons.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py::test_build_stage_commands_scope_every_stage_to_company_ids tests/scripts/test_run_company_upload_enrichment_batch.py::test_build_stage_commands_respects_dry_run_and_skip_flags tests/scripts/test_run_company_upload_enrichment_batch.py::test_process_batch_skips_completed_companies_and_records_stage_reports tests/scripts/test_run_company_upload_enrichment_batch.py::test_stage_details_capture_generic_react_audit -q` -> passed, 4 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_source_product_extract.py::test_supported_source_url_allows_generic_web_after_source_judgment -q` -> passed, 1 test.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_xlsx_team_synthesis.py -q` -> passed, 4 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_xlsx_team_synthesis.py -q` -> passed, 59 tests.
- `python -m compileall -q apps/miroflow-agent/scripts/run_company_generic_source_judgment.py apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/scripts/run_company_source_product_extract.py apps/miroflow-agent/src/data_agents/company/enrichment_batch.py` -> passed.

Remaining gaps:
- The bounded 100-company upload-path validation and 5180 manual inspection are still pending.

### 2026-05-28 - Chat and retrieval context enrichment verification

Requirement coverage:
- Company profile chat answers now include product category, target customers, product application scenarios, technical tags, application scenarios, and normalized recent-funding details when those fields are present in the refreshed company payload.
- Retrieval evidence blocks now preserve company snippets from refreshed Milvus payloads, including product, target-customer, scenario, and recent-funding text, instead of reducing company evidence to name plus industry.
- Company retrieval snippets keep enriched profile-summary text long enough to retain product/scenario/funding material appended after the long profile, while preserving the existing profile-summary-first contract.

Verification:
- `cd apps/admin-console && uv run --no-sync pytest tests/test_chat_multi_domain_entity_stack.py::test_company_product_query_includes_enrichment_fields tests/test_chat_retrieval.py::test_company_retrieval_evidence_block_preserves_enrichment_context -q` -> RED before implementation, then passed, 2 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/service/test_retrieval_company_patent.py::test_retrieve_company_snippet_keeps_enrichment_after_long_profile -q` -> RED before implementation, then passed, 1 test.
- `cd apps/admin-console && uv run --no-sync pytest tests/test_chat_multi_domain_entity_stack.py tests/test_chat_retrieval.py -q` -> passed, 55 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/service/test_retrieval_company_patent.py tests/data_agents/company/test_vectorizer.py tests/scripts/test_run_milvus_backfill_company.py -q` -> passed, 23 tests.

Remaining gaps:
- Full focused company/admin/frontend test runs, previous validation-noise cleanup, the new 100-company validation, validation report, and 5180 manual inspection remain open.

### 2026-05-28 - Focused company, admin, and frontend verification

Requirement coverage:
- The full focused company data-agent suite covers XLSX readiness, enrichment batches, official capture, Yiou/PitchHub/generic search connectors, source-product extraction, signal extraction, company release, vectorization, and touched-company Milvus backfill.
- The focused admin-console suite covers upload pipeline triggering and company detail quality-status serialization.
- The RecordDetail frontend test and production build cover the company detail display contract used by the 5180 frontend.
- OpenSpec strict validation remains green after task and acceptance updates.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company tests/scripts/test_run_company_upload_enrichment_batch.py tests/scripts/test_run_company_official_product_capture.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_signal_extract.py tests/scripts/test_run_milvus_backfill_company.py -q` -> passed, 230 tests.
- `cd apps/admin-console && uv run --no-sync pytest tests/test_upload_pipeline_trigger.py tests/test_data_api_quality_status.py -q` -> passed, 19 tests.
- `cd apps/admin-console/frontend && npm test -- --run src/pages/RecordDetail.test.tsx` -> passed, 3 tests.
- `cd apps/admin-console/frontend && npm run build` -> passed; Vite emitted an existing large-chunk warning for the built bundle.
- `python -m compileall -q apps/admin-console/backend/services/chat_context.py apps/admin-console/backend/api/chat.py apps/miroflow-agent/src/data_agents/service/retrieval.py` -> passed.
- `openspec validate company-synthesis-enrichment-pipeline --strict` -> passed.

Remaining gaps:
- Prior validation-noise cleanup, the new 100-company validation, validation report, and 5180 manual inspection remain open.

### 2026-05-29 - Bounded 100-company upload validation closure

Requirement coverage:
- A new bounded 100-company validation was run from the uploaded XLSX path
  using the import batch `2c30b826-4aaa-48ca-8ce9-8bc5dc56c275`.
- The validation included a no-live-web dry-run batch, a live web/persistence
  run, XLSX baseline/team/product synthesis, official-site capture,
  Yiou/PitchHub capture, generic ReAct source judgment, source-product
  extraction, funding signal extraction, multi-source narrative synthesis, and
  touched-company Milvus refresh.
- The run did not perform a full 1024-company refresh.
- Representative companies were manually inspected in the 5180-connected
  environment for section order, company-domain summary label, long summary
  quality, product fields, application scenarios, recent dynamics, and source
  links.

Validation batches:
- Dry-run batch `2f157839-aab2-469f-b09c-122e21c4f8b8` -> succeeded,
  100 selected, 100 processed, 100 succeeded, 0 failed.
- Live batch `b854d0e0-1bcc-4ea8-968c-b4b4dab1f45c` -> succeeded,
  100 selected, 100 processed, 100 succeeded, 0 failed.

Final counts:
- Company base records ready: 100/100.
- Resolved companies: 100/100.
- Profiles length >= 500: 99/100.
- Technology-route summaries length >= 80: 99/100.
- Generic web audit: 314 queries, 1566 results, 415 accepted source rows.
- Yiou audit: 1084 queries, 1038 results, 71 accepted source rows.
- PitchHub audit: 1090 queries, 3810 results, 88 accepted source rows.
- Products: 336 total, 152 ready, 87 companies with any product, 82 companies
  with ready product.
- Product target-customer fields: 10 product rows.
- Product application-scenario fields: 112 product rows.
- Application scenarios: 227 total, 146 ready, 55 companies with scenarios,
  50 companies with ready scenarios.
- Funding events: 97 total, 55 companies with funding event, 42 source-backed
  signal events.
- Team: 423 member rows, 290 structured members, 86 companies with structured
  team.
- Touched-company vectors refreshed: 100.
- Current miss reasons: `synthesis_no_facts` 72 companies, `llm_rejected` 14,
  `all_results_rejected` 3, `no_results` 1.

Manual 5180 inspection:
- `COMP-37013bba3132`: page order, product, scenarios, funding history, long
  profile, technology route, and source links are visible.
- `COMP-54fd4dd036ff`: product display uses only the six business-facing fields;
  scenarios and recent financing are visible.
- `COMP-10047ff88d61`: prior unrelated Arabica/coffee pollution is absent;
  product and recent funding are visible.
- `COMP-7a89e82e6329`: sparse material falls back to XLSX description/business
  and has no product, scenario, recent dynamics, or source links yet.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_source_product_extractor.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/scripts/test_run_company_source_product_extract.py tests/data_agents/company/test_yiou_adapter.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_generic_source_judgment.py tests/data_agents/company/test_vectorizer.py tests/scripts/test_run_milvus_backfill_company.py tests/data_agents/company/test_narrative_enrichment.py -q` -> passed, 128 tests.
- `cd apps/admin-console && .venv/bin/python -m pytest tests/test_upload_pipeline_trigger.py tests/test_data_api_quality_status.py -q` -> passed, 20 tests.
- `cd apps/admin-console/frontend && npm test -- --run src/pages/RecordDetail.test.tsx` -> passed, 3 tests.
- `cd apps/miroflow-agent && uv run python <deepseek-v4-pro-non-thinking-smoke>` -> response model `deepseek-v4-pro`, finish reason `stop`, reasoning output absent.

Evidence:
- `.agents/runs/company-synthesis-enrichment-pipeline/validation-100.md`
  records the validation batches, aggregate counts, source audit, product and
  scenario evidence tiers, 5180 inspection, DeepSeek runtime smoke, LLM usage
  inventory, and residual rollout risks.

Residual risks:
- One sampled company remains sparse and uses XLSX fallback text instead of a
  synthesized long profile.
- Target-customer extraction coverage remains low and should be improved before
  claiming strong completeness.
- Official-site capture remains limited by website reachability and page
  structure.
- The next optimization should add bounded parallel LLM execution and stronger
  JSON/schema repair for narrative output stability.
