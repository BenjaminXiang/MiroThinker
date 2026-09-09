---
title: "Excel ingest validation roadmap 2026-05-04"
date: 2026-05-04
owner: codex
status: active
category: docs/solutions/integration-issues
module: apps/admin-console / apps/miroflow-agent
problem_type: validation_roadmap
severity: high
tags: [excel, company, patent, ingest, admin-console, retrieval, milvus]
---

# Excel ingest validation roadmap 2026-05-04

## 背景

国先中心后续会继续导入更多 Excel，重点不是单次导入是否不报错，而是：

1. 导入后 company / patent 数据能否完成解析、清洗、去重、关联和质量标记。
2. 新数据能否进入 Postgres 与 Milvus，并被 `/api/chat`、`/browse`、检索服务稳定召回。
3. 管理运维人员能否在 admin-console 看到导入进度、失败原因、待审核项和检索效果。

准确性优先于覆盖率：对 professor-company 这类公开证据可能缺失的关系，不能为了让问答样例有结果而写入弱对应关系。没有强证据时，应保留待审/未收录状态，并让检索回答明确说明证据不足。

## 当前结论

最新 admin upload apply 证据：

- `docs/source_backfills/host-e2e-admin-upload-2026-05-04T11-49-41Z.txt`
- result: `PASS`
- company upload task: `run_id=d630e052-27ca-4d0d-9291-87de063e00f4`、`items_processed=1025`、`items_failed=0`
- patent upload task: `run_id=d2e0bd09-a7c1-466a-a930-4fb2b6638eee`、`items_processed=1930`、`items_failed=0`
- `/api/pipeline/runs?triggered_by=admin-console&limit=8`: HTTP 200
- after DB snapshot: `company_count=1024`、`company_snapshot_count=3075`、`patent_count=1931`、`company_patent_link_count=105`、`admin_upload_source_page_count=4`

本轮真实 E2E 先后暴露并已修复：

- pipeline run 列表 SQL 在 nullable filter 下触发 Postgres `AmbiguousParameter`。
- repeated company upload 因 `seed_registry (seed_kind, scope_key)` 固定为 `company_xlsx/admin-console:company` 触发唯一约束。
- repeated upload 的 `source_page` 不能按文件 hash 复用，否则旧任务 detail 会被新任务覆盖。

最新 host V0 证据：

- `docs/source_backfills/host-e2e-excel-ingest-2026-05-04T11-32-40Z.txt`
- result: `PASS_WITH_GAPS_REVIEW_REQUIRED`
- company parser dry-run: `rows_read=1620`、`company_rows_parsed=1025`、`deduped_records=1025`
- company release dry-run: `input_record_count=1038`、`released_record_count=1037`
- patent parser dry-run: `records_parsed=1930`、`skipped_rows=0`
- patent release dry-run: `input_record_count=1931`、`released_record_count=1931`
- current Postgres: `company_count=1024`、`patent_count=1931`、`company_patent_link_count=76`
- admin upload V0 当时为 `HANDOFF_ONLY`；当前已由 `host-e2e-admin-upload-2026-05-04T11-49-41Z.txt` 验证为真实后台导入任务。
- Milvus probe: `OK` with `company_profiles=1024`、`patent_profiles=1931`、`paper_chunks=11591`、`professor_profiles=787`

11:32 run also fixed the harness environment gap: Postgres/Milvus probes now use
the project `uv` environment instead of host system Python, so `psycopg` and
`pymilvus` availability is stable under Codex CLI host execution.

2026-05-05 host closure evidence:

- `docs/source_backfills/host-e2e-admin-upload-2026-05-05T11-47-03Z.txt`
  - result: `PASS`
  - company task detail now includes `run_scope.result_summary`:
    `imported=1025`、`team_members_inserted=1302`、`lineage_rows=1025`、
    `milvus_backfill_required=true`、`milvus_backfill_status=not_triggered`
  - patent task detail now includes `run_scope.result_summary`:
    `imported=1930`、`company_patent_link_candidates=105`、
    `company_patent_links_written=105`、`company_patent_link_errors=0`、
    `artifact_dir=...-patent-release`、`milvus_backfill_required=true`、
    `milvus_backfill_status=not_triggered`
- `docs/source_backfills/host-e2e-excel-ingest-2026-05-05T11-47-47Z.txt`
  - result: `PASS`
  - failures: `0`
  - gaps: `0`
  - company/patent parser dry-run、release dry-run、Postgres/Milvus 状态、
    admin upload 能力与最近 upload result summary 全部通过。
- `docs/source_backfills/host-e2e-agentic-rag-2026-05-05T11-48-51Z.txt`
  - result: `PASS`
  - company / paper / patent / professor / C-followup chat gates 全部通过。

2026-05-05 TDD follow-up closure evidence:

- `docs/source_backfills/host-e2e-admin-upload-2026-05-05T13-39-00Z.txt`
  - result: `PASS`
  - admin upload apply path 仍可真实写入 company/patent。
  - company/patent upload 之后可通过
    `POST /api/pipeline/runs/{run_id}/milvus-backfill?dry_run=true`
    创建 `backfill_real` 子任务。
  - company / patent Milvus dry-run 子任务均 `succeeded`，result summary 写回
    `run_scope.result_summary`，并记录 collection schema check 输出。
- `docs/source_backfills/host-e2e-admin-upload-2026-05-05T13-43-09Z.txt`
  - result: `PASS_WITH_GAPS_REVIEW_REQUIRED`
  - 默认 admin upload host gate 已切到 `HOST_ADMIN_UPLOAD_E2E_MODE=dry-run`，
    避免反复写 `company` / `company_snapshot` / `patent` 主数据。
  - DB before/after 证明主数据未被 dry-run 污染：
    `company_snapshot_count=8200` 前后不变，`patent_count=1931` 前后不变。
  - dry-run 发现源 Excel 数据 gap：company workbook 有
    `rows_missing_company_name=3`，任务状态为 `partial`，脚本记录为 gap 而非失败。
- `docs/source_backfills/host-e2e-excel-ingest-2026-05-05T13-44-16Z.txt`
  - result: `PASS`
  - Excel gate 已区分真实 apply summary 与 dry-run summary；真实 apply summary
    仍取 13:39 的 company/patent 成功导入任务。
- `docs/source_backfills/host-e2e-agentic-rag-2026-05-05T13-44-48Z.txt`
  - result: `PASS`
  - LLM profile `gemma4`，host `star.sustech.edu.cn`，path
    `/service/model/gemma4/v1`，model `gemma-4-26b-a4b-it`，TCP 与
    OpenAI-compatible probe 均 OK。
  - company / paper / patent / professor / C-followup chat gates 全部通过。
- `docs/source_backfills/host-e2e-admin-upload-2026-05-05T16-44-18Z.txt`
  - result: `PASS_WITH_GAPS_REVIEW_REQUIRED`
  - company dry-run task `ac70fd4e-c4ff-4a31-a786-54e171d9dd1d` 输出
    `data_quality_issues=[missing_company_name]`。
  - `pipeline_issue` 写入成功：
    `issue_id=41dbcf89-1e3a-4a0b-b865-36b09e0ad337`，
    `reported_by=admin_upload_dry_run`，`source_rows=[1620,1621,1622]`。
  - patent dry-run 无数据质量 issue。
- `docs/source_backfills/host-e2e-excel-ingest-2026-05-05T16-44-38Z.txt`
  - result: `PASS`
  - company parser / release dry-run 均输出
    `missing_company_name_rows=[1620,1621,1622]`。
- `docs/source_backfills/host-e2e-agentic-rag-2026-05-05T16-45-10Z.txt`
  - result: `PASS`
  - LLM / Postgres / Milvus / classifier / chat gates 全部通过。
- `docs/source_backfills/host-e2e-admin-upload-2026-05-05T16-54-24Z.txt`
  - result: `PASS_WITH_GAPS_REVIEW_REQUIRED`
  - company dry-run task `de7681a1-a2af-4a22-bcc6-9a9c7a7bf31a` 继续稳定输出
    `data_quality_issues=[missing_company_name]`。
  - `pipeline_issue` 写入成功：
    `issue_id=98df6d4a-73f7-4a80-b253-9fd0051d82f5`，
    `reported_by=admin_upload_dry_run`，`source_rows=[1620,1621,1622]`。
  - 前端 smoke 已验证 `/pipeline-issues?...task_id=...` 可展示该 issue，
    任务详情页“质量问题”按钮可跳回过滤后的 issue 列表。
- `docs/source_backfills/host-e2e-pipeline-issues-ui-2026-05-05T16-58-21Z.txt`
  - result: `PASS`
  - `PATCH /api/pipeline-issues/{issue_id}` 已验证可关闭和重新打开 issue。
  - 浏览器 smoke 已验证 issue 列表页“关闭 / 重开”按钮可驱动真实 API，
    最终该源数据 gap 保持 `resolved=false`，避免误把缺公司名行标为已修复。
- `docs/source_backfills/host-e2e-admin-upload-2026-05-05T17-03-43Z.txt`
  - result: `PASS_WITH_GAPS_REVIEW_REQUIRED`
  - company dry-run task `d11082da-654c-419b-ba36-c45b0ab450a1` 输出
    `recommended_action="Fill company_name in the source Excel rows before import."`。
  - `pipeline_issue` 写入成功：
    `issue_id=dc7aa450-85a8-4046-a4c5-43e5b45cea68`，
    `source_rows=[1620,1621,1622]`，evidence snapshot 包含同一
    `recommended_action`。
- `docs/source_backfills/host-e2e-pipeline-issues-ui-2026-05-05T17-05-10Z.txt`
  - result: `PASS`
  - live API 与浏览器 smoke 已验证“建议”列展示同一
    `recommended_action`，issue 最终状态保持 `resolved=false`。

### 已具备

- company Excel 解析器：`src/data_agents/company/import_xlsx.py`
  - 支持表头探测、续行合并、公司名标准化、融资事件/投资方抽取、重复记录合并。
- company Postgres canonical import：`src/data_agents/company/canonical_import.py`
  - 可写 `company` / `company_snapshot` / team / funding / lineage / `pipeline_run`。
- patent Excel 解析器：`src/data_agents/patent/import_xlsx.py`
  - 支持中文/英文标题、摘要、申请人、专利号、日期、类型、技术功效字段解析。
- patent release + Postgres 写入脚本：`scripts/run_patent_release_e2e.py`
  - 可写 `patent`，并通过公司名称/aliases 写 `company_patent_link`。
- Milvus 回填脚本：`scripts/run_milvus_backfill.py`
  - 支持 `company` / `patent` / `paper` / `professor` collection。
- admin-console 有 company/patent 上传入口和 Dashboard/列表/质量状态展示。

### 已新增闭环

- `/api/upload/{domain}` 对 company/patent 已接真实后台任务：
  - company 调用 `import_company_xlsx_to_postgres`。
  - patent 调用 parser / release / canonical writer / company-patent linkage。
- 上传接口返回 `task_id/source_page_id`；前端上传成功后跳转到导入任务详情。
- `/api/pipeline/runs` 和 `/api/pipeline/runs/{run_id}` 已提供任务列表/详情；详情包含 `items_processed/items_failed/error_summary/source_pages`。
- admin upload 完成后会把结构化结果写入 `run_scope.result_summary`；前端任务详情展示导入摘要。
- 导入摘要会明确标出 Milvus 回填状态和可执行 backfill 命令，避免导入后检索更新需求被静默遗漏。
- `/api/pipeline/runs/{run_id}/milvus-backfill` 已支持从任务详情创建
  `backfill_real` 子任务；`dry_run=true` 可安全验证 Milvus collection schema，
  非 dry-run 可执行实际回填。
- `/api/upload/{domain}?dry_run=true` 已支持 company/patent Excel 非破坏性验证：
  解析、写入 `pipeline_run/source_page`、关闭任务并写回 result summary，但不写
  company/patent 主数据。
- company dry-run 已把具体数据质量问题写入 `pipeline_issue`；当前覆盖
  `missing_company_name`，evidence snapshot 包含 `task_id`、`source_rows`、
  `issue_type`、`domain`。
- `/api/pipeline-issues` 已支持按 `task_id`、`domain`、`issue_type` 过滤
  evidence snapshot，用于从导入任务精确定位本次 dry-run 的质量问题。
- `/api/pipeline-issues/{issue_id}` 已支持关闭/重新打开 issue，并写回
  `resolved`、`resolved_at`、`resolution_notes`、`resolution_round`。
- company `missing_company_name` issue 已写入 `recommended_action`，并纳入
  host admin upload E2E gate。
- 质量问题页已展示 `recommended_action` 作为“建议”列。
- 前端上传弹窗已有“验证 / 导入”模式；任务详情页已有“Milvus 回填”动作。
- 前端已有“质量问题”页；任务详情页在存在 `data_quality_issues` 时可跳转到
  当前任务过滤后的 issue 列表。
- 质量问题页已有“关闭 / 重开”动作，并通过浏览器 smoke 验证。
- `host_e2e_admin_upload.sh` 默认使用 dry-run 模式；需要真实写库时显式设置
  `HOST_ADMIN_UPLOAD_E2E_MODE=apply`。

### 未闭环

- 上传接口的初始 `imported=0/skipped=0` 仍只是“已创建任务”，真实结果以任务详情为准；后续可以调整响应文案或 response model，避免误解。
- Dashboard 只展示域级总量和质量概览，仍缺失败行 drill-down、可重试动作。
- company/patent 的“上传 -> 解析 -> 写库 -> 关系 -> narrative/summary -> quality promote -> Milvus -> 检索验收”已有 host gate，但 retrieval smoke 结果还没有写回单次导入 validation report。
- 当前企业源 Excel 存在 3 行缺公司名；dry-run 已能发现并写入
  `pipeline_issue`，任务详情已能跳转到 issue 列表，issue 页已能关闭/重开；
  修复建议已写入 evidence；但还未提供原始行预览、认领人/处理人字段。

## 验证矩阵

### V0：非破坏性解析与 release 验证

命令：

```bash
bash apps/admin-console/scripts/host_e2e_excel_ingest_validation.sh
```

验收：

- company parser 输出 rows_read / records_parsed / deduped_records / duplicate_groups。
- patent parser 输出 rows_read / records_parsed / skipped_rows / skip_reasons。
- company release dry-run 输出 released_record_count。
- patent release dry-run 输出 patent_records / company_patent_link 候选统计。
- Postgres/Milvus 当前状态可采集。

意义：先证明新 Excel 的格式、字段、清洗逻辑能被当前代码理解，不改生产库。

### V1：Staging 写库验证

前提：使用 staging DB 或可回滚 real DB snapshot。

验收项：

- company 导入后：
  - `company` 新增/更新数量符合预期。
  - `company_snapshot` 与 source lineage 数量和 Excel 行数可对齐。
  - duplicate/alias 决策可解释。
  - team/funding 字段能落库。
- patent 导入后：
  - `patent` 新增/更新数量符合预期。
  - `company_patent_link` 命中率达到阈值。
  - link_errors 可解释，不能静默丢失。
  - patent_number/title/applicants 去重有效。

### V2：质量与关联验证

必须输出：

- company core field gap：industry / description / business / website / aliases。
- patent core field gap：title / abstract / patent_number / applicants / patent_type。
- company-patent link coverage：`links_written / link_candidates`。
- 重名/简称/别名冲突清单。
- 待人工审核行列表，进入 `pipeline_issue` 或 review queue。
- professor-company 等敏感关系必须区分 `verified`、`candidate`、`not_found`；candidate 不能默认作为强事实输出。

### V3：Milvus 与检索验证

每次 apply 后必须跑：

- `run_milvus_backfill.py --domain company`
- `run_milvus_backfill.py --domain patent`
- 重点 query Top-K：
  - 企业：行业/技术/产品/地区/简称。
  - 专利：技术词/申请人/专利号/功效短语。
- 验收不只看 HTTP 200：
  - expected query_type
  - min citations
  - Top-K 命中人工标注
  - object-level dedup
  - source/evidence 可追溯

## P0 缺口

1. company/patent admin upload 已从 handoff-only 改成真实后台任务，并通过 host E2E；任务详情已写入 `run_scope.result_summary`，覆盖 company 写入/团队/lineage 和 patent link coverage/artifact path。
2. 任务详情 API 已有基础字段和结果摘要；仍缺阶段级进度、错误样例、可重试动作。
3. 已补 Milvus 一键触发/队列化执行，且 dry-run 子任务通过 host E2E；下一步可加入实际回填的限流、互斥锁和操作确认。
4. retrieval smoke 已由 `host_e2e_agentic_rag.sh` 固定覆盖；下一步要把对应结果写回单次导入 validation report。
5. 前端已有导入任务队列/详情入口和导入摘要；仍缺失败/待审项 drill-down。

## 推荐实施顺序

1. 先跑 V0 脚本收集当前 Excel 解析/release 证据。
2. 已补 admin upload 后台任务：
   - company：接 `import_company_xlsx_to_postgres`。
   - patent：接 parser / release / canonical writer / linkage。
3. 已补 `/api/pipeline/runs` 任务列表/详情接口和前端任务页。
4. 已补 company/patent 导入后的 result summary，并纳入 host Excel gap 判定。
5. 已补 Milvus 回填队列化触发；继续补 retrieval smoke report 写回导入任务。
6. `host_e2e_admin_upload.sh` 已作为固定 host E2E gate 使用；默认 dry-run，
   需要真实写库时显式 `HOST_ADMIN_UPLOAD_E2E_MODE=apply`，并继续与 Excel/RAG gate 联跑。
7. 已为 dry-run 发现的 company `rows_missing_company_name=3` 增加
   `pipeline_issue` drill-down 记录，并补齐任务详情页到 issue 列表的跳转。
   已补 issue 关闭/重开动作和修复建议；继续扩展原始行摘要和认领人字段。
