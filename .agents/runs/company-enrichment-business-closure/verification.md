# Verification

Date: 2026-05-28

## Focused Unit And Script Tests

Command:

```bash
cd apps/miroflow-agent
uv run pytest \
  tests/data_agents/company/test_signal_event_extractor.py \
  tests/scripts/test_run_company_signal_extract.py \
  tests/data_agents/company/test_source_product_extractor.py \
  tests/scripts/test_run_company_source_product_extract.py \
  tests/data_agents/company/test_official_product_capture.py \
  tests/scripts/test_run_company_official_product_capture.py \
  tests/data_agents/company/test_vectorizer.py \
  tests/scripts/test_run_milvus_backfill_company.py \
  -q -n0 --no-cov
```

Result: `50 passed in 1.35s`.

Command:

```bash
cd apps/admin-console
./.venv/bin/pytest \
  tests/test_domains_postgres.py::test_company_released_object_exposes_products_events_and_source_evidence \
  tests/test_chat_multi_domain_entity_stack.py::test_company_product_query_includes_enrichment_fields \
  tests/test_chat_multi_domain_entity_stack.py::test_company_topic_sql_searches_products_events_and_funding \
  tests/test_chat_multi_domain_entity_stack.py::test_company_topic_chat_uses_raw_query_for_funding_context \
  -q
```

Result: `4 passed, 4 warnings`.

Command:

```bash
cd apps/admin-console/frontend
npm run build
```

Result: build completed successfully. Vite reported the existing large-chunk warning.

## Live DB And Source Closure

Database DSN used:

```text
postgresql://miroflow:miroflow@localhost:15432/miroflow_real
```

Real DB counts after source event/product extraction:

```text
company_product=10
company_product_evidence=11
company_signal_event by source:
  legacy=575
  pitchhub_36kr=17
```

Sample `深圳旭宏医疗科技` (`COMP-36d1c30cb50f`):

```text
product: Semacare
event: 2020-07-07 funding 深圳旭宏医疗科技有限公司 A轮 数千万人民币
```

## Bounded Milvus Refresh

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
uv run --no-sync python scripts/run_milvus_backfill.py \
  --domain company \
  --company-id COMP-36d1c30cb50f \
  --batch-size 1 \
  --milvus-uri /home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db \
  --log-level INFO
```

Result:

```json
{"companies_total": 1, "companies_processed": 1, "companies_skipped": 0, "companies_with_errors": 0}
```

Milvus query for `COMP-36d1c30cb50f` returned profile summary text containing:

```text
产品/服务：Semacare - Semacare 专注创新心电系统开发，运用 AI 自动诊断技术支持临床和远程心电诊断及监护。
最近动态：2020-07-07 funding 深圳旭宏医疗科技有限公司 A轮 数千万人民币
```

Scope note: a full company refresh was started before the operator clarified that a full 1024-company refresh was not needed; it completed with `companies_total=1024`, `companies_processed=1024`. After clarification, the accepted path was changed to bounded `--company-id` refresh and verified on the sample above.

## Live API, Browser, And Chat Smoke

Admin backend started with:

```bash
cd apps/admin-console
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
CHAT_MILVUS_URI='/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db' \
uv run --no-sync uvicorn backend.main:app --host 0.0.0.0 --port 18188 --log-level info
```

API check:

```bash
curl --noproxy '*' http://127.0.0.1:18188/api/company/COMP-36d1c30cb50f
```

Result: response includes `Semacare`, one `funding` recent event, and Yiou/PitchHub source URLs.

Browser check:

```bash
agent-browser --session company-closure open http://127.0.0.1:5180/company/COMP-36d1c30cb50f
agent-browser --session company-closure wait --text Semacare
agent-browser --session company-closure snapshot -i -c
agent-browser --session company-closure close
```

Result: page displayed the `Semacare` product row, the `funding` recent-event row, and Yiou/PitchHub source links.

Chat checks:

```bash
curl --noproxy '*' -X POST http://127.0.0.1:18188/api/chat \
  -H 'Content-Type: application/json' \
  --data '{"query":"旭宏医疗产品是什么"}'
```

Result: `query_type=A_company_profile`; answer includes `Semacare` and `2020-07-07 funding`.

```bash
curl --noproxy '*' -X POST http://127.0.0.1:18188/api/chat \
  -H 'Content-Type: application/json' \
  --data '{"query":"最近融资的深圳医疗 AI 公司"}'
```

Result: `query_type=B_company_topic_search`, `match_count=40`, first result includes a funding snippet.

## Skipped Checks

- No new full 1024-company source web search/backfill was run after the operator clarified that full refresh was not needed.

## Upload Batch Closure Verification

Command:

```bash
uv run pytest -n0 --no-cov \
  apps/miroflow-agent/tests/storage/test_v033_migration.py \
  apps/miroflow-agent/tests/storage/test_v034_migration.py \
  apps/miroflow-agent/tests/storage/test_v035_migration.py \
  apps/miroflow-agent/tests/storage/test_alembic_revision_lineage.py \
  apps/miroflow-agent/tests/data_agents/company/test_enrichment_batch.py \
  apps/miroflow-agent/tests/data_agents/company/test_source_product_extractor.py \
  apps/miroflow-agent/tests/data_agents/company/test_official_product_capture.py \
  apps/miroflow-agent/tests/data_agents/company/test_signal_event_extractor.py \
  apps/miroflow-agent/tests/scripts/test_run_company_news_ingest.py \
  apps/miroflow-agent/tests/scripts/test_run_company_signal_extract.py \
  apps/miroflow-agent/tests/scripts/test_run_company_source_product_extract.py \
  apps/miroflow-agent/tests/scripts/test_run_company_official_product_capture.py \
  apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py \
  apps/miroflow-agent/tests/scripts/test_close_stale_pipeline_runs.py \
  apps/admin-console/tests/test_upload_pipeline_trigger.py \
  apps/admin-console/tests/test_domains_postgres.py \
  -q
```

Result: `132 passed, 4 warnings`.

Command:

```bash
cd apps/admin-console/frontend
npm run build
```

Result: build completed successfully. Vite reported the existing large-chunk warning.

Real DB batch verification:

```text
batch_id=393f8e5d-d965-4744-81e7-836f7f727aac
company_id=COMP-36d1c30cb50f
batch status=succeeded
companies_selected=1
companies_processed=1
companies_succeeded=1
companies_failed=0
checkpoint status=succeeded
query_count=16
source_result_count=3
accepted_source_count=3
event_count=0
product_count=2
scenario_count=6
official_product_count=3
miss_reason=null
milvus_refreshed=true
stages=news_iyiou, news_pitchhub, signal_extract, source_product_extract, official_product_capture, milvus_refresh
```

Search audit verification:

```text
iyiou audit rows=8 aggregate result_count=6
pitchhub_36kr audit rows=8 aggregate result_count=24
```

Resume verification command:

```bash
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
uv run python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py \
  --batch-id 393f8e5d-d965-4744-81e7-836f7f727aac \
  --limit 1 \
  --chunk-size 1 \
  --sleep-seconds 0 \
  --official-product-max-pages 1
```

Result:

```json
{"batch_id": "393f8e5d-d965-4744-81e7-836f7f727aac", "companies_selected": 0, "companies_processed": 0, "status": "succeeded", "stage_reports": []}
```

Live API verification:

```text
GET http://127.0.0.1:18188/api/company/COMP-36d1c30cb50f
id=COMP-36d1c30cb50f
products=4
application_scenarios=3
first_product=PROD-0ace5c9fffed MetaCor(tm) needs_review
```

Review API verification:

```text
POST /api/company/COMP-36d1c30cb50f/enrichment/product/PROD-0ace5c9fffed/review action=accept
previous_status=needs_review
new_status=ready

POST /api/company/COMP-36d1c30cb50f/enrichment/product/PROD-0ace5c9fffed/review action=needs_review
previous_status=ready
new_status=needs_review

company_enrichment_review_action rows for actor=codex-e2e: 2
```

## Source Product Semantic Quality Audit Closure

Task scope:

```text
batch_id=382fb63b-1a81-4ff2-8841-95ab87c717b1
database=postgresql://miroflow:miroflow@localhost:15432/miroflow_real
policy=XLSX import data is the trusted company baseline; external Yiou/PitchHub rows are untrusted candidates.
visibility_gate=only quality_status='ready' products/scenarios enter display, chat fallback, and company Milvus text.
```

Focused regression command:

```bash
uv run pytest \
  apps/admin-console/tests/test_domains_postgres.py \
  apps/admin-console/tests/test_chat_multi_domain_entity_stack.py \
  apps/miroflow-agent/tests/scripts/test_run_milvus_backfill_company.py \
  apps/miroflow-agent/tests/scripts/test_run_company_source_product_quality_audit.py \
  -q
```

Result:

```text
66 passed, 4 warnings in 0.18s
```

Lint command:

```bash
uv run ruff check \
  apps/miroflow-agent/scripts/run_company_source_product_quality_audit.py \
  apps/admin-console/backend/services/data_helpers.py \
  apps/admin-console/backend/services/chat_context.py \
  apps/admin-console/backend/api/domains.py \
  apps/admin-console/backend/api/chat.py \
  apps/miroflow-agent/scripts/run_milvus_backfill.py \
  apps/miroflow-agent/tests/scripts/test_run_company_source_product_quality_audit.py \
  apps/admin-console/tests/test_domains_postgres.py \
  apps/admin-console/tests/test_chat_multi_domain_entity_stack.py \
  apps/miroflow-agent/tests/scripts/test_run_milvus_backfill_company.py
```

Result:

```text
All checks passed!
```

LLM dry-run command:

```bash
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
uv run python apps/miroflow-agent/scripts/run_company_source_product_quality_audit.py \
  --batch-id 382fb63b-1a81-4ff2-8841-95ab87c717b1 \
  --dry-run \
  --llm-verify \
  --output .agents/runs/company-enrichment-business-closure/revalidation-100-source-product-quality-audit-llm-full-dry-run-2026-05-28.json
```

Result:

```json
{
  "totals": {"audited": 174, "llm_verified": 174, "llm_failed": 0},
  "decision_counts": {"ready_candidate": 30, "reject": 139, "needs_review": 5}
}
```

LLM apply command:

```bash
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
uv run python apps/miroflow-agent/scripts/run_company_source_product_quality_audit.py \
  --batch-id 382fb63b-1a81-4ff2-8841-95ab87c717b1 \
  --llm-verify \
  --apply-rejections \
  --promote-ready \
  --actor source-product-quality-audit-llm \
  --output .agents/runs/company-enrichment-business-closure/revalidation-100-source-product-quality-audit-llm-apply-2026-05-28.json
```

Result:

```json
{
  "totals": {"audited": 174, "llm_verified": 174, "llm_failed": 0},
  "decision_counts": {"ready_candidate": 31, "reject": 138, "needs_review": 5},
  "updated_counts": {"rejected": 138, "ready": 31}
}
```

Post-apply DB verification:

```text
audited_product_ids=174
quality_status:
  needs_review=5
  ready=31
  rejected=138
review_action rows for actor=source-product-quality-audit-llm:
  accept -> ready=31
  reject -> rejected=138
```

Sample ready rows:

```text
勃望初芯半导体科技 / MEMS集成的生物医疗芯片模组
华力创科学（深圳） / SONATA介入超声导航机器人系统
华力创科学（深圳） / 光学力矩传感器及力控系统
华力创科学（深圳） / 工业机器人
华力创科学（深圳） / 微创手术介入医疗器械
```

Sample hidden needs-review rows:

```text
深圳元戎启行科技 / L3级自动驾驶商业化落地再提速，元戎启行
深圳元戎启行科技 / VLA大模型赋能元戎启行市占率第二抢占新订单先机
深圳元戎启行科技 / 周光：VLA模型将成智能驾驶体验颠覆性拐点
深圳元戎启行科技 / 已有20万辆量产乘用车搭载其城市NOA系统
深圳小墨智能科技 / 人机交互效果强的线下AI交互虚拟机器人
```

Sample rejected rows:

```text
交浦科技（深圳） / 脑疾病诊疗与康复设备
交浦科技（深圳） / 高性能人机交互产品
卓驭科技 / AD智驾的2025年：监管刹车、技术狂飙，“地大华魔”谁主沉浮？
图灵集市（深圳）科技 / AI新产业发展聚焦平台
```

5180 real-DB runtime verification:

```bash
tr '\0' '\n' < /proc/3291130/environ | rg '^DATABASE_URL='
curl -i -sS http://127.0.0.1:5180/api/health
curl --noproxy '*' -i -sS http://100.64.0.4:5180/api/health
```

Result:

```text
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real
127.0.0.1:5180/api/health -> HTTP 200 {"status":"ok"}
100.64.0.4:5180/api/health -> HTTP 200 {"status":"ok"}
```

Live API gate checks:

```text
GET http://127.0.0.1:5180/api/company/COMP-cff54e822fc5
products=DeepRoute IO, L4级自动驾驶全栈解决方案, L4级自动驾驶轻卡, 无图城区NOA, 城区NOA功能
statuses=ready only

GET http://127.0.0.1:5180/api/company/COMP-46240f3defcc
products=[]

GET http://127.0.0.1:5180/api/company/COMP-95791ebe18d4
products=6
statuses=ready only
```

Skipped checks:

```text
Full 1025-company external enrichment was not rerun in this slice.
The five needs_review products were not physically deleted because they remain hidden and may need operator review.
```

## Historical Cleanup And 100-Company Revalidation

Historical cleanup audit:

```text
.agents/runs/company-enrichment-business-closure/historical-noise-cleanup-2026-05-28.json
deleted company_product rows=25
post-cleanup remaining_noise_names=0
post-cleanup remaining_domain_or_js_evidence=0
```

Fresh 100-company validation batch:

```text
batch_id=382fb63b-1a81-4ff2-8841-95ab87c717b1
selection audit=.agents/runs/company-enrichment-business-closure/revalidation-100-selection-2026-05-28.json
excluded batches=142120fe-bc2c-486b-9955-573e06160cce, 8b717ebe-a4c7-40a2-ac84-cf229d4454da
selected companies=100
companies with website=58
```

Command:

```bash
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
MILVUS_URI='/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db' \
COMPANY_UPLOAD_ENRICHMENT_TIMEOUT_SECONDS=1200 \
uv run python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py \
  --batch-id 382fb63b-1a81-4ff2-8841-95ab87c717b1 \
  --limit 100 \
  --chunk-size 20 \
  --sleep-seconds 0 \
  --official-product-max-pages 1
```

Result:

```text
status=succeeded
companies_selected=100
companies_processed=100
companies_succeeded=100
companies_failed=0
```

Initial evidence exported:

```text
.agents/runs/company-enrichment-business-closure/revalidation-100-summary-2026-05-28.json
source_products=210
official_products=22
scenarios=107
events=51
```

RED regression checks:

```bash
uv run pytest -n0 --no-cov \
  apps/miroflow-agent/tests/data_agents/company/test_yiou_adapter.py::test_pitchhub_adapter_rejects_records_matching_only_llm_product_aliases \
  apps/miroflow-agent/tests/data_agents/company/test_official_product_capture.py::test_extract_products_rejects_protocol_social_app_and_generic_products_heading_noise \
  -q
```

Result before repair: `2 failed`.

```bash
uv run pytest -n0 --no-cov \
  apps/miroflow-agent/tests/data_agents/company/test_official_product_capture.py::test_extract_products_rejects_marketing_channel_article_and_external_tool_noise \
  -q
```

Result before the broader official-product guard: `1 failed`.

Focused post-repair tests:

```bash
uv run pytest -n0 --no-cov \
  apps/miroflow-agent/tests/data_agents/company/test_yiou_adapter.py \
  apps/miroflow-agent/tests/data_agents/company/test_serper_news_connector.py \
  apps/miroflow-agent/tests/data_agents/company/test_official_product_capture.py \
  apps/miroflow-agent/tests/scripts/test_run_company_news_ingest.py \
  -q
```

Result: `67 passed`.

100-company validation cleanup:

```text
cleanup audit=.agents/runs/company-enrichment-business-closure/revalidation-100-cleanup-2026-05-28.json
follow-up cleanup audit=.agents/runs/company-enrichment-business-closure/revalidation-100-cleanup-followup-2026-05-28.json
restore audit=.agents/runs/company-enrichment-business-closure/revalidation-100-cleanup-restore-2026-05-28.json
deleted company_news_item=29
deleted company_signal_event=9
deleted company_application_scenario=17
deleted net company_product=53
restored product=BioFord™
```

Post-cleanup validation:

```text
post-cleanup summary=.agents/runs/company-enrichment-business-closure/revalidation-100-post-cleanup-summary-2026-05-28.json
source_rows_bad_after_cleanup=0
official_rows_bad_after_cleanup=0
news_items_after_start=150
source_products_after_start=174
official_products_after_start=5
scenarios_after_start=90
events_after_start=42
remaining official products=EmbodiFlow, SenseXperience, TeleXperience, BioFord™, 必可AEO认证系统
```

Stale cleanup verification:

```text
pipeline_run=308531cd-2971-445b-b3b3-9571741995e0
status=failed
error_summary.reason=stale_pipeline_run_cleanup
```

## Ten Percent Live Validation

Date: 2026-05-28

Sample:

```text
real company count=1024
snapshot count=1025
sample size=103
selection=ORDER BY md5(company_id || 'company-enrichment-10pct-2026-05-28-v2')
batch_id=142120fe-bc2c-486b-9955-573e06160cce
```

Command:

```bash
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
MILVUS_URI='/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db' \
COMPANY_UPLOAD_ENRICHMENT_TIMEOUT_SECONDS=1800 \
uv run python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py \
  --batch-id 142120fe-bc2c-486b-9955-573e06160cce \
  --limit 103 \
  --chunk-size 10 \
  --sleep-seconds 0 \
  --official-product-max-pages 1
```

Result:

```text
status=partial
companies_selected=103
companies_processed=103
duration_seconds=3006
```

Stage status:

```text
news_iyiou succeeded=103 failed=0
news_pitchhub succeeded=103 failed=0
signal_extract succeeded=103 failed=0
source_product_extract succeeded=103 failed=0
official_product_capture succeeded=103 failed=0
milvus_refresh succeeded=0 failed=103
```

Search audit:

```text
iyiou companies=103 query_rows=724 search_results=642 no_result_query_rows=234 rejected_query_rows=285 rows_with_llm_hints=724
pitchhub_36kr companies=103 query_rows=715 search_results=2284 no_result_query_rows=68 rejected_query_rows=348 rows_with_llm_hints=715
```

New source evidence:

```text
iyiou companies=30 rows=44
pitchhub_36kr companies=40 rows=82
```

New structured rows:

```text
events: pitchhub_36kr companies=14 events=50; iyiou companies=3 events=3
products: companies=49 products=185 needs_review=185
scenarios: companies=25 scenarios=76 needs_review=76
official-like products: companies=19 products=55
```

Issues exposed:

```text
1. Milvus refresh failed for all 103 companies because pymilvus rejects local file MILVUS_URI values during subprocess startup.
2. Per-company checkpoint counters are inflated when chunk_size > 1 because stage aggregate counters are written to every company in the chunk.
3. company_enrichment_batch.companies_processed stays 0 while the batch is running; progress requires reading company_enrichment_company_state.
4. Search audit rows preserve diagnostics, but accepted/rejected counters are aggregate diagnostics repeated per query row, so summing them overcounts.
5. Official website extraction can produce false products from domain-sale and JavaScript placeholder pages, for example JavaScript, PayPal, GoDaddy, HugeDomains, and domain-sale text.
6. company_signal_event source-adapter reporting requires joining company_news_item through primary_news_id; the event table does not directly expose source_adapter.
7. An initial validation batch with identity_status='active' selected zero companies because current company rows use identity_status='resolved'. It was closed as failed with reason empty_validation_batch.
```

## Ten Percent Repair Verification

Date: 2026-05-28

RED checks observed before implementation:

```text
test_build_stage_commands_passes_local_milvus_uri_as_cli_arg failed with unexpected keyword argument milvus_uri
test_run_command_scrubs_local_milvus_uri_env_when_cli_arg_is_used failed because MILVUS_URI leaked into subprocess env
test_process_batch_uses_per_company_counters_and_updates_progress failed because query_count=3 was copied to each company
test_record_search_audit_stores_aggregate_counters_once_not_per_query failed because accepted_count summed to 4 instead of 2
test_extract_products_rejects_domain_sale_and_javascript_placeholder_pages failed because PayPal/GoDaddy were extracted as products
```

Focused regression command:

```bash
uv run pytest -n0 --no-cov \
  apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py \
  apps/miroflow-agent/tests/data_agents/company/test_enrichment_batch.py \
  apps/miroflow-agent/tests/data_agents/company/test_official_product_capture.py \
  -q
```

Result: `16 passed`.

Wider company enrichment command:

```bash
uv run pytest -n0 --no-cov \
  apps/miroflow-agent/tests/storage/test_v035_migration.py \
  apps/miroflow-agent/tests/storage/test_alembic_revision_lineage.py \
  apps/miroflow-agent/tests/data_agents/company/test_enrichment_batch.py \
  apps/miroflow-agent/tests/data_agents/company/test_source_product_extractor.py \
  apps/miroflow-agent/tests/data_agents/company/test_official_product_capture.py \
  apps/miroflow-agent/tests/data_agents/company/test_signal_event_extractor.py \
  apps/miroflow-agent/tests/scripts/test_run_company_news_ingest.py \
  apps/miroflow-agent/tests/scripts/test_run_company_signal_extract.py \
  apps/miroflow-agent/tests/scripts/test_run_company_source_product_extract.py \
  apps/miroflow-agent/tests/scripts/test_run_company_official_product_capture.py \
  apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py \
  apps/miroflow-agent/tests/scripts/test_close_stale_pipeline_runs.py \
  apps/miroflow-agent/tests/scripts/test_run_milvus_backfill_company.py \
  apps/admin-console/tests/test_upload_pipeline_trigger.py \
  apps/admin-console/tests/test_domains_postgres.py \
  -q
```

Result: `142 passed, 4 warnings`.

Live smoke:

```text
batch_id=8b717ebe-a4c7-40a2-ac84-cf229d4454da
company_id=COMP-36d1c30cb50f
MILVUS_URI=/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db
runner status=succeeded
companies_processed=1
milvus stage companies_total=1 companies_processed=1 companies_with_errors=0
batch status=succeeded
company state milvus_refreshed=true
```

Audit counter smoke:

```text
iyiou query rows=8 results=6 accepted=1
pitchhub_36kr query rows=8 results=24 accepted=2 name_rejected=9
```
