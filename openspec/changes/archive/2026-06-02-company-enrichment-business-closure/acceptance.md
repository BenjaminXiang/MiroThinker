## Acceptance Evidence

Date: 2026-05-28

### Source News To Signal Events

- Focused tests passed: `uv run pytest tests/data_agents/company/test_signal_event_extractor.py tests/scripts/test_run_company_signal_extract.py -q -n0 --no-cov`.
- Yiou source-profile run completed with strict date-evidence validation: `news_total=19`, `news_processed=19`, `events_extracted=0`, `events_inserted=0`.
- PitchHub source-profile run completed with strict date-evidence validation: `news_total=20`, `news_processed=20`, `events_extracted=20`, `events_inserted=17`, `news_with_errors=0`.
- Real DB event count after source extraction: `legacy=575`, `pitchhub_36kr=17`.

### Source Body To Product Records

- Focused tests passed: `uv run pytest tests/data_agents/company/test_source_product_extractor.py tests/scripts/test_run_company_source_product_extract.py tests/data_agents/company/test_official_product_capture.py tests/scripts/test_run_company_official_product_capture.py -q -n0 --no-cov`.
- Source product extraction run completed for Yiou and PitchHub rows: `news_total=44`, `news_processed=44`, `products_extracted=11`, `products_inserted=11`.
- Real DB product counts after dedupe: `company_product=10`, `company_product_evidence=11`.
- Sample company `COMP-36d1c30cb50f` (`深圳旭宏医疗科技`) has product `Semacare` with PitchHub and Yiou evidence.

### Company API And Admin Detail Display

- Backend focused tests passed: `./.venv/bin/pytest tests/test_domains_postgres.py::test_company_released_object_exposes_products_events_and_source_evidence tests/test_chat_multi_domain_entity_stack.py::test_company_product_query_includes_enrichment_fields tests/test_chat_multi_domain_entity_stack.py::test_company_topic_sql_searches_products_events_and_funding tests/test_chat_multi_domain_entity_stack.py::test_company_topic_chat_uses_raw_query_for_funding_context -q`.
- Frontend build passed: `npm run build`.
- Live API check passed for `/api/company/COMP-36d1c30cb50f`: response includes `core_facts.products[0].name=Semacare`, `core_facts.recent_events[0].event_type=funding`, and Yiou/PitchHub evidence URLs.
- Browser check passed at `http://127.0.0.1:5180/company/COMP-36d1c30cb50f`: the page displayed a `Semacare` product row, a `funding` recent-event row, and Yiou/PitchHub source links.

### Company Milvus And RAG Refresh

- Focused tests passed: `uv run pytest tests/data_agents/company/test_vectorizer.py tests/scripts/test_run_milvus_backfill_company.py -q -n0 --no-cov`.
- Root cause fixed for file-backed Milvus refresh: `run_milvus_backfill.py` now defaults file URI clients to `MILVUS_USE_REAL_CLIENT=1`, while preserving `:memory:` test compatibility.
- Bounded refresh path added and verified: `run_milvus_backfill.py --domain company --company-id COMP-36d1c30cb50f --batch-size 1 --milvus-uri /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db` returned `companies_total=1`, `companies_processed=1`, `companies_with_errors=0`.
- Querying `company_profiles` for `COMP-36d1c30cb50f` returned profile summary text containing `Semacare` and the `2020-07-07 funding` event.
- Live chat check passed for `旭宏医疗产品是什么`: answer includes `Semacare` and `2020-07-07 funding`.
- Live chat check passed for `最近融资的深圳医疗 AI 公司`: response type `B_company_topic_search`, `match_count=40`, first result includes a funding snippet.

### Scope Note

A full company Milvus refresh command was started before the operator narrowed the scope and completed with `companies_total=1024`, `companies_processed=1024`. No further full refresh was run after that instruction. The implemented and accepted operational path is the bounded `--company-id` refresh.

### Structured Business Fields And Upload-Scoped Enrichment

- Focused tests passed: `uv run pytest apps/miroflow-agent/tests/storage/test_v034_migration.py apps/miroflow-agent/tests/storage/test_alembic_revision_lineage.py apps/miroflow-agent/tests/data_agents/company/test_structured_business_models.py apps/miroflow-agent/tests/data_agents/company/test_source_product_extractor.py apps/miroflow-agent/tests/data_agents/company/test_official_product_capture.py apps/miroflow-agent/tests/scripts/test_run_company_source_product_extract.py apps/miroflow-agent/tests/scripts/test_run_company_news_ingest.py apps/miroflow-agent/tests/scripts/test_run_company_signal_extract.py apps/miroflow-agent/tests/data_agents/company/test_vectorizer.py apps/miroflow-agent/tests/scripts/test_run_milvus_backfill_company.py apps/admin-console/tests/test_domains_postgres.py apps/admin-console/tests/test_chat_multi_domain_entity_stack.py apps/admin-console/tests/test_upload_pipeline_trigger.py`.
- Test result: `126 passed, 4 warnings`.
- Real DB migration applied: `alembic upgrade head` ran `V033 -> V034`.
- Bounded live Yiou run for `COMP-36d1c30cb50f` completed with `companies_processed=1`, `news_fetched=1`, `llm_search_hints_used=1`, `companies_with_errors=0`.
- Bounded live PitchHub run for `COMP-36d1c30cb50f` completed with `companies_processed=1`, `news_fetched=2`, `llm_search_hints_used=1`, `companies_with_errors=0`.
- Bounded source product/scenario extraction for `COMP-36d1c30cb50f` completed with `news_processed=3`, `products_extracted=2`, `scenarios_extracted=6`.
- Real DB verification for `COMP-36d1c30cb50f`: `company_product` has `Semacare`, `product_category=心电诊断系统`, `target_customers=[医院/临床机构]`, `application_scenarios=[临床心电诊断, 远程心电诊断, 心电监护]`, `technical_tags=[AI自动诊断, 心电系统]`.
- Real DB verification for `COMP-36d1c30cb50f`: `company_application_scenario` has `临床心电诊断`, `远程心电诊断`, and `心电监护`, each with PitchHub source evidence.
- Real DB financing verification for `COMP-36d1c30cb50f`: funding event normalized payload includes `round=A轮`, `amount_raw=数千万人民币`, `investors_raw=力合科创`, and `amount_cny_wan=1100`.
- Bounded Milvus refresh for `COMP-36d1c30cb50f` returned `companies_total=1`, `companies_processed=1`, `companies_with_errors=0`. A first attempt failed because `MILVUS_URI` was set to a local file path in the environment; rerun succeeded by passing the local file path only via `--milvus-uri`.
- Live API check passed after backend restart: `/api/company/COMP-36d1c30cb50f` includes structured products, application scenarios, and normalized funding fields.
- Live chat check passed for `旭宏医疗产品和应用场景是什么`: answer and structured payload include `Semacare`, `临床心电诊断`, `远程心电诊断`, `心电监护`, and the A-round funding event.
- Browser check passed at `http://127.0.0.1:5180/company/COMP-36d1c30cb50f`: product and application scenario tables display structured fields, and funding normalized JSON renders as readable JSON instead of `[object Object]`.

### Upload Batch Closure, Auditability, And Operations

- Focused tests passed: `uv run pytest -n0 --no-cov apps/miroflow-agent/tests/storage/test_v033_migration.py apps/miroflow-agent/tests/storage/test_v034_migration.py apps/miroflow-agent/tests/storage/test_v035_migration.py apps/miroflow-agent/tests/storage/test_alembic_revision_lineage.py apps/miroflow-agent/tests/data_agents/company/test_enrichment_batch.py apps/miroflow-agent/tests/data_agents/company/test_source_product_extractor.py apps/miroflow-agent/tests/data_agents/company/test_official_product_capture.py apps/miroflow-agent/tests/data_agents/company/test_signal_event_extractor.py apps/miroflow-agent/tests/scripts/test_run_company_news_ingest.py apps/miroflow-agent/tests/scripts/test_run_company_signal_extract.py apps/miroflow-agent/tests/scripts/test_run_company_source_product_extract.py apps/miroflow-agent/tests/scripts/test_run_company_official_product_capture.py apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py apps/miroflow-agent/tests/scripts/test_close_stale_pipeline_runs.py apps/admin-console/tests/test_upload_pipeline_trigger.py apps/admin-console/tests/test_domains_postgres.py -q`.
- Test result: `132 passed, 4 warnings`.
- Frontend build passed: `npm run build`. Vite reported the existing large-chunk warning.
- Real DB V035 migration was applied to `miroflow_real`, adding upload enrichment batch, per-company checkpoint, search audit, and review action tables.
- Admin XLSX upload now creates a queued enrichment batch after canonical import and starts the resumable runner out of band instead of running the full external enrichment chain inline inside the upload task.
- Bounded upload-batch E2E for `COMP-36d1c30cb50f` used batch `393f8e5d-d965-4744-81e7-836f7f727aac` and completed with `status=succeeded`, `companies_selected=1`, `companies_processed=1`, `companies_succeeded=1`, and `companies_failed=0`.
- Per-company checkpoint verification for `COMP-36d1c30cb50f`: `query_count=16`, `source_result_count=3`, `accepted_source_count=3`, `event_count=0`, `product_count=2`, `scenario_count=6`, `official_product_count=3`, `miss_reason=null`, and `milvus_refreshed=true`.
- Stage checkpoint verification for `COMP-36d1c30cb50f`: `news_iyiou`, `news_pitchhub`, `signal_extract`, `source_product_extract`, `official_product_capture`, and `milvus_refresh` all recorded succeeded stage status.
- Search audit verification for the same batch/company: Yiou wrote 8 query audit rows with 6 aggregate result hits; PitchHub wrote 8 query audit rows with 24 aggregate result hits. The audit rows preserve query text, adapter, diagnostics, and LLM hint payloads.
- Resume verification passed by rerunning `run_company_upload_enrichment_batch.py --batch-id 393f8e5d-d965-4744-81e7-836f7f727aac --limit 1 --chunk-size 1 --sleep-seconds 0 --official-product-max-pages 1`; the runner returned `companies_selected=0`, `companies_processed=0`, `status=succeeded`, proving completed companies are skipped by default.
- Live API verification passed for `http://127.0.0.1:18188/api/company/COMP-36d1c30cb50f`: response includes 4 products and 3 application scenarios.
- Review action API verification passed for product `PROD-0ace5c9fffed`: `accept` changed `needs_review -> ready`, then `needs_review` restored `ready -> needs_review`; 2 audit rows were written for actor `codex-e2e`.
- Stale pipeline cleanup verification passed: stale `pipeline_run` `308531cd-2971-445b-b3b3-9571741995e0` was closed to `failed` with `reason=stale_pipeline_run_cleanup`, while the cleanup command filters by age and run kind.

### Ten Percent Validation Repair

- RED tests were added for the 10 percent validation defects and initially failed on the existing implementation:
  - local-file Milvus URI was not passed as a CLI argument by the upload batch runner;
  - local-file `MILVUS_URI` leaked into the Milvus subprocess environment;
  - chunk aggregate counters were copied into every company state row;
  - query audit accepted/rejected counters were repeated on each query row;
  - domain-sale and JavaScript placeholder official pages were extracted as products.
- Focused regression tests passed after repair: `uv run pytest -n0 --no-cov apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py apps/miroflow-agent/tests/data_agents/company/test_enrichment_batch.py apps/miroflow-agent/tests/data_agents/company/test_official_product_capture.py -q`.
- Wider company enrichment tests passed after repair: `uv run pytest -n0 --no-cov apps/miroflow-agent/tests/storage/test_v035_migration.py apps/miroflow-agent/tests/storage/test_alembic_revision_lineage.py apps/miroflow-agent/tests/data_agents/company/test_enrichment_batch.py apps/miroflow-agent/tests/data_agents/company/test_source_product_extractor.py apps/miroflow-agent/tests/data_agents/company/test_official_product_capture.py apps/miroflow-agent/tests/data_agents/company/test_signal_event_extractor.py apps/miroflow-agent/tests/scripts/test_run_company_news_ingest.py apps/miroflow-agent/tests/scripts/test_run_company_signal_extract.py apps/miroflow-agent/tests/scripts/test_run_company_source_product_extract.py apps/miroflow-agent/tests/scripts/test_run_company_official_product_capture.py apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py apps/miroflow-agent/tests/scripts/test_close_stale_pipeline_runs.py apps/miroflow-agent/tests/scripts/test_run_milvus_backfill_company.py apps/admin-console/tests/test_upload_pipeline_trigger.py apps/admin-console/tests/test_domains_postgres.py -q`.
- Wider test result: `142 passed, 4 warnings`.
- Real DB smoke batch `8b717ebe-a4c7-40a2-ac84-cf229d4454da` passed with `MILVUS_URI=/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db` in the environment and local-file URI passed through the runner. Batch result: `status=succeeded`, `companies_processed=1`, `companies_succeeded=1`, `companies_failed=0`.
- Smoke batch Milvus stage returned `companies_total=1`, `companies_processed=1`, `companies_with_errors=0`; company state has `milvus_refreshed=true`.
- Smoke batch search audit aggregation now sums to `accepted=1` for Yiou and `accepted=2` for PitchHub instead of multiplying accepted counts by query row count.

### Historical Noise Cleanup And 100 Company Revalidation

- Historical 10 percent validation cleanup exported audit evidence to `.agents/runs/company-enrichment-business-closure/historical-noise-cleanup-2026-05-28.json`.
- Historical cleanup deleted 25 noisy `company_product` rows from batch `142120fe-bc2c-486b-9955-573e06160cce`, covering domain-sale pages, JavaScript placeholders, social/testimonial handles, CTA labels, footer/social links, and generic section titles. Post-cleanup checks found `remaining_noise_names=0` and `remaining_domain_or_js_evidence=0`.
- A fresh deterministic 100-company validation batch was created as `382fb63b-1a81-4ff2-8841-95ab87c717b1`, excluding the previous 103-company validation batch and the one-company smoke batch. Selection evidence was exported to `.agents/runs/company-enrichment-business-closure/revalidation-100-selection-2026-05-28.json`.
- The 100-company upload-enrichment runner completed with `status=succeeded`, `companies_selected=100`, `companies_processed=100`, `companies_succeeded=100`, and `companies_failed=0`.
- Initial 100-company evidence was exported to `.agents/runs/company-enrichment-business-closure/revalidation-100-summary-2026-05-28.json`. The run produced `source_products=210`, `official_products=22`, `scenarios=107`, and `events=51` before validation cleanup.
- The validation exposed source-acceptance contamination: product/keyword search terms could be reused as Yiou/PitchHub match terms. RED regression coverage was added in `test_pitchhub_adapter_rejects_records_matching_only_llm_product_aliases`; it failed before the repair and passed after the repair.
- The validation also exposed additional official-site product false positives. RED regression coverage was added for testimonial/social-handle, CTA/footer, protocol/social-app, marketing, channel, article-title, copyright, and external-tool noise. The focused tests failed before the guards and passed after the guards.
- Focused company source and official-product tests passed after repair: `uv run pytest -n0 --no-cov apps/miroflow-agent/tests/data_agents/company/test_yiou_adapter.py apps/miroflow-agent/tests/data_agents/company/test_serper_news_connector.py apps/miroflow-agent/tests/data_agents/company/test_official_product_capture.py apps/miroflow-agent/tests/scripts/test_run_company_news_ingest.py -q` returned `67 passed`.
- The 100-company cleanup exported audit evidence to `.agents/runs/company-enrichment-business-closure/revalidation-100-cleanup-2026-05-28.json`, `.agents/runs/company-enrichment-business-closure/revalidation-100-cleanup-followup-2026-05-28.json`, and `.agents/runs/company-enrichment-business-closure/revalidation-100-cleanup-restore-2026-05-28.json`.
- The 100-company cleanup deleted 29 contaminated `company_news_item` rows, 9 `company_signal_event` rows, 17 `company_application_scenario` rows, and 53 net noisy `company_product` rows. `BioFord™` was restored after an overly strict follow-up cleanup replay, with restoration evidence recorded.
- Post-cleanup validation exported `.agents/runs/company-enrichment-business-closure/revalidation-100-post-cleanup-summary-2026-05-28.json`. The repaired source identity guard found `source_rows_bad_after_cleanup=0`, and the repaired official-product guard found `official_rows_bad_after_cleanup=0`.
- Post-cleanup retained evidence counts for the 100-company batch are `news_items_after_start=150`, `source_products_after_start=174`, `official_products_after_start=5`, `scenarios_after_start=90`, and `events_after_start=42`. Remaining official products are `EmbodiFlow`, `SenseXperience`, `TeleXperience`, `BioFord™`, and `必可AEO认证系统`.

### Source Product Semantic Quality Audit Closure

- Regression coverage was added for the batch-scoped source product audit, including ready candidates, company identity failure, generic/non-product names, product-not-grounded failure, LLM payload construction from the trusted XLSX baseline, LLM acceptance of true aliases, LLM rejection of wrong-company sources, textual confidence labels, and LLM failure fallback.
- The source product audit now supports `--llm-verify --llm-profile gemma4`. The LLM verifier treats XLSX company fields as the trusted baseline and external Yiou/PitchHub source text as untrusted evidence, then verifies company identity, product ownership, actual product/service status, confidence, and evidence quote before recommending `ready`, `needs_review`, or `rejected`.
- Display and retrieval surfaces were gated to `quality_status='ready'` for product and application scenario rows. This was applied to company detail/release SQL, chat topic fallback SQL, chat context SQL, and company Milvus SQL so `needs_review` and `rejected` source candidates remain stored but do not enter 5180 page display or RAG text.
- Focused regression command passed: `uv run pytest apps/admin-console/tests/test_domains_postgres.py apps/admin-console/tests/test_chat_multi_domain_entity_stack.py apps/miroflow-agent/tests/scripts/test_run_milvus_backfill_company.py apps/miroflow-agent/tests/scripts/test_run_company_source_product_quality_audit.py -q` returned `66 passed, 4 warnings`.
- Lint command passed: `uv run ruff check apps/miroflow-agent/scripts/run_company_source_product_quality_audit.py apps/admin-console/backend/services/data_helpers.py apps/admin-console/backend/services/chat_context.py apps/admin-console/backend/api/domains.py apps/admin-console/backend/api/chat.py apps/miroflow-agent/scripts/run_milvus_backfill.py apps/miroflow-agent/tests/scripts/test_run_company_source_product_quality_audit.py apps/admin-console/tests/test_domains_postgres.py apps/admin-console/tests/test_chat_multi_domain_entity_stack.py apps/miroflow-agent/tests/scripts/test_run_milvus_backfill_company.py` returned `All checks passed`.
- LLM dry-run evidence was exported to `.agents/runs/company-enrichment-business-closure/revalidation-100-source-product-quality-audit-llm-full-dry-run-2026-05-28.json`. It audited 174 source products, verified 174 with the LLM, and classified `ready_candidate=30`, `reject=139`, `needs_review=5`.
- LLM apply evidence was exported to `.agents/runs/company-enrichment-business-closure/revalidation-100-source-product-quality-audit-llm-apply-2026-05-28.json`. It audited 174 source products, verified 174 with the LLM, marked 138 rows `rejected`, promoted 31 rows to `ready`, and left 5 ambiguous rows as `needs_review`.
- Post-apply real DB verification for the 174 audited product IDs returned status counts: `ready=31`, `rejected=138`, `needs_review=5`. Review audit rows for actor `source-product-quality-audit-llm` returned `accept/ready=31` and `reject/rejected=138`.
- Ready sample after audit: `勃望初芯半导体科技 / MEMS集成的生物医疗芯片模组`; `华力创科学（深圳） / SONATA介入超声导航机器人系统`; `华力创科学（深圳） / 光学力矩传感器及力控系统`; `华力创科学（深圳） / 工业机器人`; `华力创科学（深圳） / 微创手术介入医疗器械`.
- Remaining `needs_review` sample after audit includes article-title or ambiguous candidates such as `深圳元戎启行科技 / L3级自动驾驶商业化落地再提速，元戎启行`, `VLA大模型赋能元戎启行市占率第二抢占新订单先机`, and `深圳小墨智能科技 / 人机交互效果强的线下AI交互虚拟机器人`. These rows are intentionally hidden from display/RAG by the ready-only gate.
- Rejected sample after audit includes wrong-company and article-title pollution such as `交浦科技（深圳） / 脑疾病诊疗与康复设备`, `交浦科技（深圳） / 高性能人机交互产品`, `卓驭科技 / AD智驾的2025年：监管刹车、技术狂飙，“地大华魔”谁主沉浮？`, and `图灵集市（深圳）科技 / AI新产业发展聚焦平台`.
- Live runtime verification showed 5180 is connected to the real DB: backend process environment has `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real`, and both `http://127.0.0.1:5180/api/health` and `http://100.64.0.4:5180/api/health` returned HTTP 200 when called with direct no-proxy curl.
- Live API verification after the ready-only gate: `GET http://127.0.0.1:5180/api/company/COMP-cff54e822fc5` returned only ready products for `深圳元戎启行科技` (`DeepRoute IO`, `L4级自动驾驶全栈解决方案`, `L4级自动驾驶轻卡`, `无图城区NOA`, `城区NOA功能`), while the five `needs_review` article-title candidates were not present in the product array.
- Live API verification after the ready-only gate: `GET http://127.0.0.1:5180/api/company/COMP-46240f3defcc` returned `product_count=0` for `交浦科技（深圳）`, hiding the rejected wrong-company products `脑疾病诊疗与康复设备` and `高性能人机交互产品`.
- Live API verification after the ready-only gate: `GET http://127.0.0.1:5180/api/company/COMP-95791ebe18d4` returned six ready products for `华力创科学（深圳）` and no non-ready product statuses.
- Remaining risk: the five `needs_review` source products are not deleted because they may require operator judgment, but they are no longer visible in company detail/release, chat fallback context, or company Milvus backfill. Full 1025-company external enrichment was not rerun in this slice.

### Company Detail Product Display Refinement

- Frontend regression tests were added in `apps/admin-console/frontend/src/pages/RecordDetail.test.tsx`.
- The product section now renders only six business-facing fields: product name, product description, product category, technical tags, target customers, and application scenarios.
- The product section no longer renders internal fields such as `product_id`, `source_url`, `quality_status`, `confidence`, or the review action column.
- Company summaries now label `profile_summary` as company introduction instead of personal profile.
- Recent events now render date, type, and summary instead of raw normalized JSON, hiding internal null fields such as `amount_cny_wan: null`.
- Focused frontend command passed: `npm run test -- src/pages/RecordDetail.test.tsx src/pages/DomainList.test.tsx src/pages/ProfessorWorkbench.test.tsx` returned `3 passed`, `6 passed`.
- Frontend build passed: `npm run build` completed successfully, with the existing Vite large-chunk warning.
- Live 5180 browser verification on `http://127.0.0.1:5180/company/COMP-cff54e822fc5` found the product section has no internal product fields, `公司简介` is present, `个人简介` is absent, and document width no longer exceeds the 1280px viewport.
