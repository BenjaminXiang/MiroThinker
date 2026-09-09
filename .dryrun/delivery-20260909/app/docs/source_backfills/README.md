# Source Backfills

本目录存放为了真实 workbook / PRD 验收而补入的可追溯 source backfill。

当前文件：
- `paper_exact_identifier_backfills.jsonl`: 精确论文标识 backfill，当前包含 `pFedGPA`。公开来源：Crossref DOI / AAAI article / arXiv。
- `v1-paper-summary-zh-full-2026-05-02.txt`: paper.summary_zh 全量真实回填日志；写入 3412 条，最终全表 `3456/7297 = 47.4%`。
- `paper-summary-zh-dogfood-2026-05-02-real.txt`: paper.summary_zh 早期 50 条 dogfood 真实日志。
- `w13-14-doi-verify-dryrun-2026-05-03.txt`: paper DOI verify 100 条 dry-run；0 confirmed，暴露 OpenAlex 400 与 arXiv 429。
- `patent_exact_identifier_supplement.xlsx`: 精确专利号 backfill，当前包含 `CN117873146A`。公开来源：Google Patents 页面。
- `w13-3-patent-e2e-full-2026-05-02.txt`: patent 真实 e2e + Milvus 回填日志；`1931/1931 summary_text`，`patent_profiles 1931`。
- `company_workbook_critical_supplement.xlsx`: workbook 关键公司对象补点源，当前覆盖 `普渡 / 开普勒 / 云迹 / 擎朗 / 九号 / 嘉立创 / 深南电路 / 一博科技 / 迈步机器人`，并补入 `跨维 / 光轮智能 / 银河通用 / 群核科技` 这批行业路线代表厂商。
- `company_knowledge_fields.jsonl`: company serving-side 知识字段 backfill，当前覆盖 `q11-q16` 所需的 `data_route_types / real_data_methods / synthetic_data_methods / capability_facets / movement_data_needs / operation_data_needs` 等结构化字段。
- `v2-company-narrative-dryrun-2026-05-02.txt` / `v2-company-narrative-full-2026-05-02.txt`: company profile_summary / technology_route_summary 真实 backfill 日志；最终覆盖 `1013/1024 = 98.93%`。
- `v2-stage3-company-top5-eval-2026-05-02.csv`: 50 条 company retrieval Top-5 评估输出，`human_top1..5` 待人工标注。
- `professor_company_roles.jsonl`: professor-company 关系 backfill，当前包含 `丁文伯 -> 深圳无界智航科技有限公司` 的证据链，用于 shared-store consolidate 时补入 `company_roles`。
- `round-7-17-name-identity-clear-{YYYY-MM-DD}.jsonl`: Round 7.17 name-identity gate scan 量化日志，每行记录一个被处理的教授决定（accepted / rejected / cleared / etc）。最后一行为 summary aggregate。使用方式：`scripts/run_name_identity_scan.py --apply --archive` 自动归档。字段定义见 `.agents/specs/2026-04-30-w9-4-name-identity-archive.md` §6.2。
- `w13-d2-promote-2026-05-02.txt`: `quality_status` 真实 promote 记录；professor `774 ready`、company `1013 ready`、paper `0 ready`、patent `1931 ready`。
- `w13-8-news-ingest-2026-05-03.txt`: Serper news ingest 真实日志；200 companies -> 482 news rows / 95 distinct companies。
- `intent-classifier-benchmark-2026-05-02-real.txt` / `intent-classifier-benchmark-2026-05-02-codex-sandbox.txt`: Agentic RAG classifier benchmark 归档；真实 run overall `0.690`，sandbox run 因内部 LLM 不可达退成 all `UNKNOWN`。
- `host-e2e-agentic-rag-2026-05-04T10-10-59Z.txt`: host Agentic RAG E2E 首轮证据；Gemma-4 OpenAI-compatible endpoint 可达，Postgres/Milvus env 未设置，HTTP chat 样例因 8010 端口冲突打到其他服务而无效。
- `host-e2e-agentic-rag-2026-05-04T10-29-40Z.txt`: host Agentic RAG E2E 二轮证据；LLM/Postgres/Milvus/API health 均通过，旧 harness `result=PASS`，但暴露 B-paper 空召回与 C follow-up 误路由，已据此收紧脚本验收。
- `host-e2e-agentic-rag-2026-05-04T10-54-21Z.txt` / `host-e2e-agentic-rag-2026-05-04T11-09-37Z.txt`: 收紧后的 host Agentic RAG E2E 证据；chat 样例已覆盖 B-company / B-paper / B-patent / A-professor / C-followup，11:09 仅因 standalone Milvus-Lite probe 文件锁误判为 FAIL，后续脚本已改为 `SKIPPED_LOCKED`。
- `host-e2e-agentic-rag-2026-05-04T11-31-40Z.txt` / `host-e2e-agentic-rag-2026-05-04T11-32-22Z.txt`: Codex CLI host 真实复跑证据；11:31 暴露 standalone probe 使用系统 Python 的依赖缺失，修复为项目 `uv` 环境后 11:32 `result=PASS`。
- `host-e2e-excel-ingest-{YYYY-MM-DDTHH-MM-SSZ}.txt`: 国先中心 Excel 持续导入验证日志；由 `apps/admin-console/scripts/host_e2e_excel_ingest_validation.sh` 生成，覆盖 company/patent parser dry-run、release dry-run、当前 Postgres/Milvus 状态与 admin upload 能力盘点。
- `host-e2e-admin-upload-{YYYY-MM-DDTHH-MM-SSZ}.txt`: admin-console 真实上传 E2E 日志；由 `apps/admin-console/scripts/host_e2e_admin_upload.sh` 生成，启动后端、上传 company/patent Excel、轮询 `/api/pipeline/runs/{task_id}`、记录任务列表和 DB 前后快照。`2026-05-04T11-49-41Z` 为当前 PASS 基线。
- `host-professor-stem-wide-harvest-2026-05-04T14-11-28Z.txt`: 深圳 STEM 12 人真实 E2E 基线；`10 released / 1 blocked / 1 non_stem_filtered`，45 条 paper staging，`suspicious_count=0`，空 SIGS 主页 `尤政院士` 被 `insufficient_academic_signal` + refusal 摘要门阻断，未进入 ready 发布。
- `host-professor-stem-wide-harvest-low-signal-websearch-2026-05-04T14-38-58Z.txt`: 低学术信号主页 web search 兜底真实 E2E；在仍传 `--skip-web-search` 的情况下，`尤政院士` 触发 `low_signal_override`，`stage5_web_search.search_count=1`、`low_signal_search_count=1`、`identity_verified=3`，最终 `11 released / 0 blocked / 1 non_stem_filtered`，45 条 paper staging，`suspicious_count=0`。
- `host-professor-stem-full-harvest-low-signal-websearch-{YYYY-MM-DDTHH-MM-SSZ}.txt`: 深圳 STEM 老师 full-harvest 后台采集日志；使用 `apps/miroflow-agent/scripts/e2e_seeds/shenzhen_stem_mainline_20260504.md`，写独立 artifacts/SQLite store，不直接切 live Postgres。当前后台任务为 `2026-05-04T14-45-20Z`，tmux session `prof_stem_full_low_signal_web_2026_05_04T14_45_20Z`，仍用 `--skip-web-search` 控制成本，但低学术信号记录会自动走 web search。
- `host-professor-stem-full-harvest-{YYYY-MM-DDTHH-MM-SSZ}.txt`: 深圳 STEM 老师 full-harvest 旧后台采集日志。`2026-05-04T11-54-16Z` 是旧质量门/旧批量落盘版本，已停止；`2026-05-04T12-27-43Z` 是中间修复版本；`2026-05-04T14-17-44Z` 是无低信号 web-search 兜底的旧 detached 任务，已停止并仅作为对照。

使用方式：
- `run_paper_release_e2e.py` 会在文件存在时自动加载 `paper_exact_identifier_backfills.jsonl`，也可通过 `--supplement-jsonl` 显式传入。
- `run_patent_release_e2e.py` 会在文件存在时自动加载 `patent_exact_identifier_supplement.xlsx`，也可通过 `--supplement-patent-input` 显式传入。
- `run_company_release_e2e.py` 会在文件存在时自动加载 `company_workbook_critical_supplement.xlsx`，也可通过 `--supplement-input` 显式传入。
- `consolidate_to_shared_store.py` 会在文件存在时自动加载 `company_knowledge_fields.jsonl` 与 `professor_company_roles.jsonl`，并在 shared-store consolidate 时补入 serving-side 结构化字段与关系。
- `apps/miroflow-agent/scripts/apply_professor_company_role_backfill.py` 用于 dry-run 校验 `professor_company_roles.jsonl` 的教授/企业解析。只有人工确认关系证据足够准确后，才使用 `--apply --link-status verified` 写入 Postgres `professor_company_role`；不要为了让 C 类 E2E 有 citation 而写入弱 candidate 关系。
- `run_paper_summary_zh_backfill.py`、`run_company_narrative_backfill.py`、`run_paper_doi_verify.py`、`run_quality_promote.py`、`run_milvus_backfill.py` 产生的真实日志归档到本目录，用于判断 PRD/E2E 是否真正闭环。
- `apps/admin-console/scripts/host_e2e_admin_upload.sh` 是上传链路的真实回归入口。它会写入本机 Postgres；重复运行会新增 `company_snapshot` / `pipeline_run` / `source_page` 追踪行，但 canonical company/patent 对象应保持去重更新。
- `apps/miroflow-agent/scripts/analyze_professor_harvest_artifacts.py --output-dir <run-dir>` 用于分析 STEM harvest 输出，按机构统计 release/blocked/ready/paper staging/gap flags，并重新应用当前质量门识别旧产物中的 refusal/boilerplate 摘要。
