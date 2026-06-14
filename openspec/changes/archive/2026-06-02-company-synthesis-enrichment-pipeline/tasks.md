## 1. Contract and RED Regression Tests

- [x] 1.1 Add company base readiness regression tests in `apps/miroflow-agent/tests/data_agents/company/test_import_xlsx.py` or `apps/miroflow-agent/tests/data_agents/company/test_enrichment_batch.py`: a resolved XLSX-backed company with name plus meaningful snapshot fields promotes `company.quality_status` to `ready`, while unresolved or empty-baseline companies remain `needs_review` with an auditable blocker.
- [x] 1.2 Add company detail API regression tests in `apps/admin-console/tests/test_data_api_quality_status.py` or the nearest company detail API test: `company.profile_summary` and `company.technology_route_summary` are returned before snapshot `description` and `business`, and fallback still works when synthesized fields are absent.
- [x] 1.3 Add frontend regression coverage in `apps/admin-console/frontend/src/pages/RecordDetail.test.tsx`: company detail section order is Basic Information, Products, Application Scenarios, Recent Events; company summary is labeled as company profile, not personal profile; product cards hide audit/raw keys and show only product name, product description, product category, technical tags, target customers, and application scenarios.
- [x] 1.4 Add source-query regression tests in `apps/miroflow-agent/tests/data_agents/company/test_serper_news_connector.py`: ordinary generic Serper queries are exactly company full name and trusted short names or aliases, with no product/funding/founder/industry tails, and payloads always include `gl="cn"` and `hl="zh-cn"`.
- [x] 1.5 Add Yiou/PitchHub regression tests in `apps/miroflow-agent/tests/data_agents/company/test_yiou_adapter.py`: site-specific search may use alias, alias plus founder, and distinctive XLSX keywords to improve recall, but those terms alone do not satisfy company identity acceptance.
- [x] 1.6 Add LLM source-judgment unit tests for the generic ReAct workflow under `apps/miroflow-agent/tests/data_agents/company/`: snippet-only competitor results are rejected without fetch, relevant-but-insufficient snippets trigger full-page fetch, and accepted full pages must have company identity plus fact-attribution evidence.
- [x] 1.7 Add synthesis regression tests in `apps/miroflow-agent/tests/data_agents/company/test_source_product_extractor.py` or a new focused synthesis test: XLSX description/business can create product and scenario candidates, industry-only material cannot invent target customers, and products include the six required business fields.
- [x] 1.8 Add team-raw structuring tests in `apps/miroflow-agent/tests/company/test_team_parser.py` or a new company LLM structuring test: `team_raw` produces name, role, background, experience highlights, relevance, and evidence while preserving raw text.
- [x] 1.9 Add vectorization tests in `apps/miroflow-agent/tests/data_agents/company/test_vectorizer.py`: company vector text includes long profile, technology or production-line summary, products, target customers, application scenarios, structured team highlights, and newer funding signals.
- [x] 1.10 Add shared LLM profile tests in `apps/miroflow-agent/tests/data_agents/professor/test_llm_profiles.py`: `deepseek-v4-pro` resolves to the OpenAI-compatible DeepSeek base URL, uses `DEEPSEEK_API_KEY`, can be selected by alias, and preserves `deepseek-v4-flash` compatibility without committing API keys.

## 2. Company Base Readiness and Detail Contract

- [x] 2.1 Update company import/promotion logic in `apps/miroflow-agent/src/data_agents/company/import_xlsx.py`, `apps/miroflow-agent/src/data_agents/company/canonical_import.py`, or `apps/miroflow-agent/src/data_agents/company/enrichment_batch.py` so XLSX baseline readiness is computed independently from external enrichment completeness.
- [x] 2.2 Define and persist baseline readiness blockers for unresolved identity, missing latest snapshot, and no meaningful baseline fields; expose the blockers in upload/enrichment batch summaries without blocking unrelated products/scenarios.
- [x] 2.3 Keep `company_product.quality_status`, `company_application_scenario.quality_status`, and uncertain `company_signal_event` rows independently reviewable after the company base record becomes `ready`.
- [x] 2.4 Fix company detail/release serialization in `apps/admin-console/backend/api/data.py`, related domain APIs, and `apps/miroflow-agent/src/data_agents/company/release.py` so synthesized `profile_summary` and `technology_route_summary` are primary and snapshot `description`/`business` are fallback-only.
- [x] 2.5 Fix `apps/admin-console/frontend/src/pages/RecordDetail.tsx` so company pages use company-domain labels, render the required section order, place products below basic information, and show product fields only in the six-field business display contract.
- [x] 2.6 Run focused checks: `cd apps/miroflow-agent && uv run pytest tests/data_agents/company/test_import_xlsx.py tests/data_agents/company/test_release.py -q` and `cd apps/admin-console && uv run pytest tests/test_data_api_quality_status.py -q`.

## 3. Long Profile, Technology Summary, and Team Structuring

- [x] 3.0 Configure the active LLM runtime for this rollout: add a DeepSeek v4 pro profile to the shared LLM resolver, set the core Hydra default LLM to OpenAI-compatible `deepseek-v4-pro`, and keep credentials in ignored `.env`/environment variables rather than committed config.
- [x] 3.1 Update `apps/miroflow-agent/src/data_agents/company/narrative_enrichment.py` so long Chinese company profiles target 500-900 characters when sufficient material exists, explicitly cite source facts internally, and record sparse-material blockers instead of padding unsupported content.
- [x] 3.2 Update technology or production-line summary generation so it uses XLSX `business`, products, official website product/service/solution material, Yiou/PitchHub material, and accepted generic source material, while preserving original XLSX fields.
- [x] 3.3 Implement or extend LLM-backed team structuring in `apps/miroflow-agent/src/data_agents/company/team_parser.py` or a focused adjacent module; output name, role, background, experience highlights, company/product relevance, confidence, and evidence span without inventing education or employer facts.
- [x] 3.4 Persist structured team output through existing `company_team_member` fields where sufficient; if existing columns cannot represent background/experience/evidence cleanly, add the smallest reversible migration and writer tests.
- [x] 3.5 Run focused checks: `cd apps/miroflow-agent && uv run pytest tests/data_agents/company/test_narrative_enrichment.py tests/company/test_team_parser.py -q`.

## 4. Product, Scenario, and Target-Customer Synthesis

- [x] 4.1 Add a source-material model for synthesis inputs that can represent XLSX fields, official pages, Yiou/PitchHub pages, and accepted generic web pages with source ID, source tier, URL, title, captured text, capture time, and trust reason.
- [x] 4.2 Implement XLSX fallback product/scenario synthesis in `apps/miroflow-agent/src/data_agents/company/source_product_extractor.py` or a focused synthesis module: extract product name, product description, product category, technical tags, target customers, and application scenarios from `description`, `business`, project name, and team context.
- [x] 4.3 Ensure target customers are accepted only when product material or official website material supports them; industry labels may guide candidate review but must not publish target customers by themselves.
- [x] 4.4 Write synthesized products through existing `upsert_company_product`/`company_product_evidence` paths and scenarios through `upsert_company_application_scenario`/`company_application_scenario_evidence`, preserving source tier and field-level evidence.
- [x] 4.5 Add a quality gate so XLSX-plus-official products can become publishable when evidence is explicit, while generic-web-only products remain reviewable unless source judgment and fact attribution are strong.
- [x] 4.6 Run focused checks: `cd apps/miroflow-agent && uv run pytest tests/data_agents/company/test_source_product_extractor.py tests/data_agents/company/test_structured_business_models.py -q`.

## 5. Official Website and High-Quality Source Capture

- [x] 5.1 Extend `apps/miroflow-agent/src/data_agents/company/official_product_capture.py` and `apps/miroflow-agent/scripts/run_company_official_product_capture.py` from narrow product-page capture to bounded official-site material capture across homepage, about, product, service, solution, case, customer, and news pages.
- [x] 5.2 Enforce official-site crawl limits: same host, configured URL count, depth, timeout, character budget, duplicate URL normalization, and rejection of domain-sale, placeholder, recruiting-only, and unrelated external pages.
- [x] 5.3 Store official captured pages as high-trust source material for profile, technology summary, product, scenario, target customer, and funding synthesis.
- [x] 5.4 Keep Yiou and 36Kr/PitchHub site-filter adapters in `apps/miroflow-agent/src/data_agents/company/news_connectors/iyiou.py` and `apps/miroflow-agent/src/data_agents/company/news_connectors/serper.py`, including diversified site-specific queries for alias, alias plus founder, full name, project name, and distinctive XLSX keywords.
- [x] 5.5 Strengthen Yiou/PitchHub acceptance so site/domain/path checks plus company identity checks are required before source material can feed synthesis.
- [x] 5.6 Run focused checks: `cd apps/miroflow-agent && uv run pytest tests/data_agents/company/test_official_product_capture.py tests/data_agents/company/test_yiou_adapter.py tests/scripts/test_run_company_official_product_capture.py -q`.

## 6. Generic Serper ReAct Source Workflow

- [x] 6.1 Refactor ordinary generic Serper discovery in `apps/miroflow-agent/src/data_agents/company/news_connectors/serper.py` so generic web/news queries are identity-only: canonical name, registered name, XLSX project/short name, and trusted LLM aliases.
- [x] 6.2 Preserve `gl="cn"` and `hl="zh-cn"` in every Serper request payload and add tests that fail if either locale field is removed.
- [x] 6.3 Build a bounded internal ReAct-style runner with inspectable tool steps: `serper_search`, `fetch_webpage`, `judge_source`, and `extract_company_facts`; use existing HTTP and LLM clients first, adding LangChain/LangGraph only if the dependency is explicitly justified and remains bounded.
- [x] 6.4 Record snippet sufficiency decisions before any page fetch: reject clearly irrelevant snippets, fetch only potentially relevant but insufficient snippets, and cap query count, result count, fetch count, body characters, LLM calls, and per-company runtime.
- [x] 6.5 Require LLM source judgment to confirm target-company identity and fact attribution before generic web material enters synthesis; rejected and needs-review judgments must include reason and evidence span.
- [x] 6.6 Exclude recruiting and job-intent pages from accepted source material in this change.
- [x] 6.7 Run focused checks: `cd apps/miroflow-agent && uv run pytest tests/data_agents/company/test_serper_news_connector.py -q` plus the new ReAct source-judgment tests.

## 7. Financing Signals and Recent Dynamics

- [x] 7.1 Extend `apps/miroflow-agent/src/data_agents/company/signal_event_extractor.py` so accepted source material can normalize financing round, date, amount, investor, and financing summary when explicitly present.
- [x] 7.2 Compare external financing evidence with XLSX baseline financing; write newer evidence as a `company_signal_event` latest-funding candidate and preserve older/history evidence without silently overwriting XLSX baseline fields.
- [x] 7.3 Keep conflicting or uncertain financing evidence review-gated with a clear reason and source URL.
- [x] 7.4 Ensure recent dynamics/detail payloads expose source-backed funding events with source URL, event date, normalized round, amount when available, investors when available, and status.
- [x] 7.5 Run focused checks: `cd apps/miroflow-agent && uv run pytest tests/data_agents/company/test_signal_event_extractor.py tests/scripts/test_run_company_signal_extract.py -q`.

## 8. Upload Batch, Audit, Resume, and Miss Reasons

- [x] 8.1 Replace synchronous serial upload enrichment in `apps/admin-console/backend/api/upload.py` with upload-scoped batch orchestration or a resumable subprocess/job runner that persists batch ID, company ID, stage, status, attempt count, timestamps, and last error.
- [x] 8.2 Update `apps/miroflow-agent/src/data_agents/company/enrichment_batch.py` and `apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py` so stages are baseline readiness, XLSX/team synthesis, official-site source capture, Yiou/PitchHub capture, generic ReAct web source judgment, multi-source synthesis, persistence, and touched-company vector refresh.
- [x] 8.3 Add explicit dry-run and skip flags for live web, official-site capture, generic Serper, Yiou/PitchHub, persistence, and Milvus refresh.
- [x] 8.4 Persist per-company audit for query generation, result counts, snippet sufficiency, fetch attempts, source judgment, accepted/rejected source material, synthesis inputs, produced facts, rejected facts, and persistence outcome.
- [x] 8.5 Persist miss reasons at least for `no_results`, `all_results_rejected`, `fetch_failed`, `llm_rejected`, `synthesis_no_facts`, and `persist_failed`; expose these reasons in batch summaries and admin diagnostics.
- [x] 8.6 Add stale-running cleanup or timeout handling for company enrichment pipeline runs so abandoned runs do not remain `running`.
- [x] 8.7 Run focused checks: `cd apps/miroflow-agent && uv run pytest tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py -q` and `cd apps/admin-console && uv run pytest tests/test_upload_pipeline_trigger.py -q`.

## 9. Retrieval, RAG, and Touched-Company Refresh

- [x] 9.1 Update `apps/miroflow-agent/src/data_agents/company/vectorizer.py` so vector payload text includes long profile, technology or production-line summary, products, product categories, technical tags, target customers, scenarios, structured team highlights, and source-backed funding signals.
- [x] 9.2 Update `apps/miroflow-agent/scripts/run_milvus_backfill.py` or company backfill helpers so upload enrichment refreshes only touched company IDs unless an explicit full refresh flag is provided.
- [x] 9.3 Verify chat/retrieval context can answer product, scenario, target-customer, and recent-funding questions from refreshed company payloads without requiring a full 1024-company refresh.
- [x] 9.4 Run focused checks: `cd apps/miroflow-agent && uv run pytest tests/data_agents/company/test_vectorizer.py tests/scripts/test_run_milvus_backfill_company.py tests/data_agents/service/test_retrieval_company_patent.py -q`.

## 10. Bounded Validation and Rollout Evidence

- [x] 10.1 Run `openspec validate company-synthesis-enrichment-pipeline --strict` and fix any OpenSpec formatting or requirement issues before implementation is considered ready.
- [x] 10.2 Run the full focused company test set: `cd apps/miroflow-agent && uv run pytest tests/data_agents/company tests/scripts/test_run_company_upload_enrichment_batch.py tests/scripts/test_run_company_official_product_capture.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_signal_extract.py tests/scripts/test_run_milvus_backfill_company.py -q`.
- [x] 10.3 Run the focused admin-console tests: `cd apps/admin-console && uv run pytest tests/test_upload_pipeline_trigger.py tests/test_data_api_quality_status.py -q`, then run frontend tests/build for `RecordDetail` if frontend tooling is installed.
- [x] 10.4 Clean prior 10% validation noise by batch/source marker only, not by deleting unrelated production data; record the cleanup SQL or dry-run output before applying it.
- [x] 10.5 Run a new bounded 100-company validation from the XLSX upload path, not a full 1024-company live run; include no-live-web dry-run, live-web limited run, persistence run, and touched-company Milvus refresh.
- [x] 10.6 Produce a validation report with counts for companies processed, auto-ready base records, official pages captured, Yiou hits, PitchHub hits, generic web accepted/rejected/needs-review, products created, scenarios created, target customers extracted, team structures created, funding events created, vectors refreshed, and miss reasons.
- [x] 10.7 Manually inspect representative companies in the 5180-connected environment for page ordering, company profile label, long summary quality, product fields, scenarios, recent dynamics, and source links before expanding beyond the 100-company validation.
- [x] 10.8 Run a DeepSeek smoke check without logging credentials: load `apps/miroflow-agent/.env`, call `deepseek-v4-pro` through the OpenAI-compatible SDK in non-thinking mode with a short prompt, and record only model, status, reasoning-output presence, and a short non-sensitive response excerpt.
- [x] 10.9 Expose upload-scoped company enrichment batch status in the admin pipeline detail page: backend detail payload includes batch progress, current stage, success/failure counts, and last error; frontend renders the processing status and auto-refreshes while the import run or enrichment batch is active.
