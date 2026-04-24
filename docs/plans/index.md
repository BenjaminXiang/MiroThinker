# 计划索引

一张表说清楚现在什么是活的、什么是完成的、什么该看哪个文档。状态以代码 + 测试 + 数据/E2E 证据校准；没有验收证据的 plan 不标 COMPLETE。

## 🟢 当前活跃（OPEN / PARTIAL — 还在推进）

| 计划 | 主题 | 状态 |
|---|---|---|
| [2026-04-16-007-plan-portfolio-execution-roadmap](./2026-04-16-007-plan-portfolio-execution-roadmap.md) | 顶层波次路线图 | ACTIVE — Round 7/8 系列已从此接过主线 |
| [2026-04-17-005-company-primary-knowledge-graph-architecture-plan](./2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md) | 企业主 KG 架构（北极星） | PARTIAL — canonical model/import code 已在；统一 KG 迁移、关系回填、Milvus/search 未完成 |
| [2026-04-08-001-feat-paper-multi-source-priority-implementation-plan](./2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md) | 论文多源证据优先级 | PARTIAL — Phase A 代码/单测在；真实 dogfood 验收模板未填，Phase B 排队 |
| [2026-04-17-001-professor-stem-reset-and-storage-redesign-plan](./2026-04-17-001-professor-stem-reset-and-storage-redesign-plan.md) | 教授 STEM 重置与存储重构 | OPEN — 设计完成，实现待启动 |
| [2026-04-17-002-professor-stem-parallel-rebuild-plan](./2026-04-17-002-professor-stem-parallel-rebuild-plan.md) | 三 Lane 并行重建 | OPEN — 三 Lane 设计完成 |
| [2026-04-17-003-professor-stem-issue-closure-plan](./2026-04-17-003-professor-stem-issue-closure-plan.md) | STEM 残留问题收尾 | PARTIAL — Wave 1 JSON 健壮性收住；Wave 2 paper closure 进行中 |
| [2026-04-17-003-professor-official-anchor-first-paper-disambiguation-plan](./2026-04-17-003-professor-official-anchor-first-paper-disambiguation-plan.md) | 官方锚点优先的论文消歧 | OPEN — 9 真实 E2E 验证通过，尚未大规模 rollout |
| [2026-04-18-001-user-chat-interface-plan](./2026-04-18-001-user-chat-interface-plan.md) | 用户对话检索界面 | PARTIAL — `/api/chat` + Chat UI MVP 已在；完整 PRD（C、ResultRef、company/patent retrieval、benchmark）未完成 |
| [2026-04-18-003-company-product-capture](./2026-04-18-003-company-product-capture.md) | 企业产品信息采集 | OPEN — 原 plan 假设失效：V008 实际是 paper title relaxation；company product schema/migration 未见 |
| [2026-04-18-004-admin-console-professor-and-ui](./2026-04-18-004-admin-console-professor-and-ui.md) | 管理后台教授 UI | PARTIAL — `/browse` 静态控制台 + API + React SPA 页面已在；产品化字段映射和体验硬化仍需验收 |

## 🟡 Agentic RAG M0–M6 状态校准

| 计划 | 主题 | 真实状态 |
|---|---|---|
| [2026-04-20-004-m0.1-reranker-client](./2026-04-20-004-m0.1-reranker-client.md) | Reranker client | PARTIAL — provider/client 代码路径已在，线上 rerank dogfood 与降级监控未单独归档 |
| [2026-04-23-001-m1-identity-gate-v2](./2026-04-23-001-m1-identity-gate-v2.md) / [2026-04-23-002-m1-orcid-backfill](./2026-04-23-002-m1-orcid-backfill.md) | ORCID / identity gate v2 | PARTIAL — V011 表、backfill 脚本、name variant 支撑已在；覆盖率、误杀率和真实 backfill 报告需归档 |
| [2026-04-21-001-m2.1-homepage-publications-extractor](./2026-04-21-001-m2.1-homepage-publications-extractor.md) / [2026-04-21-002-m2.2-paper-title-resolver](./2026-04-21-002-m2.2-paper-title-resolver.md) / [2026-04-21-003-m2.3-paper-full-text-fetcher](./2026-04-21-003-m2.3-paper-full-text-fetcher.md) / [2026-04-21-004-m2.4-homepage-paper-ingest-orchestrator](./2026-04-21-004-m2.4-homepage-paper-ingest-orchestrator.md) | Homepage paper ingest | PARTIAL — extractor/resolver/fetcher/orchestrator 与测试在；真实 dogfood 验收模板未填 |
| [2026-04-22-001-m3-retrieval-service-paper-first](./2026-04-22-001-m3-retrieval-service-paper-first.md) | Retrieval service | PARTIAL — `professor` / `paper` 可检索；`company` / `patent` 未接入服务层 |
| [2026-04-22-002-m4-chat-routes-retrieval-integration](./2026-04-22-002-m4-chat-routes-retrieval-integration.md) / [2026-04-22-003-m5.2-web-search-rerank](./2026-04-22-003-m5.2-web-search-rerank.md) | Chat routes + web rerank | PARTIAL — A/B/D/E/F/G 路由与 Serper fallback 代码在；100 条分类基准、C 一级类型、D 专利第二轮和 E 综合答案验收未完成 |
| [2026-04-22-004-m6-profile-reinforcement](./2026-04-22-004-m6-profile-reinforcement.md) | Profile reinforcement | PARTIAL — 脚本与测试在；生产批量运行、re-embed 和效果对比未归档 |

## ✅ 已完成（COMPLETE — 保留作参考）

| 计划 | 完成点 |
|---|---|
| [2026-04-04-001-feat-admin-console-plan](./2026-04-04-001-feat-admin-console-plan.md) | 管理后台一期：FastAPI + React + SQLite 查询界面 |
| [2026-04-16-002-professor-direct-profile-identity-hardening-plan](./2026-04-16-002-professor-direct-profile-identity-hardening-plan.md) | 直跳 profile 的身份加固 |
| [2026-04-16-003-professor-pipeline-residual-hardening-plan](./2026-04-16-003-professor-pipeline-residual-hardening-plan.md) | Wave 4 发现/抓取加固 |
| [2026-04-16-004-professor-school-adapter-architecture-plan](./2026-04-16-004-professor-school-adapter-architecture-plan.md) | School adapter 架构 Phase 1（CUHK/SYSU 上线） |
| [2026-04-16-005-workbook-coverage-gap-remediation-plan](./2026-04-16-005-workbook-coverage-gap-remediation-plan.md) | 工作簿覆盖缺口补齐 |
| [2026-04-16-006-professor-workbook-closure-sequencing-plan](./2026-04-16-006-professor-workbook-closure-sequencing-plan.md) | 教授工作簿 closure 编排 |
| [2026-04-18-002-real-data-e2e-and-db-separation](./2026-04-18-002-real-data-e2e-and-db-separation.md) | `miroflow_real` / `miroflow_test_mock` 双 DB 隔离（所有 Round 7/8 流程的基础） |
| [2026-04-18-005-data-quality-guards-and-identity-gate](./2026-04-18-005-data-quality-guards-and-identity-gate.md) | Round 7.6 / 7.8 / 7.9 / 7.10' / 7.13 / 7.14 / 7.15 — LLM 优先的数据质量门 |
| [2026-04-18-006-pipeline-verification-console](./2026-04-18-006-pipeline-verification-console.md) | Round 8c：`/browse` 三 tab + `pipeline_issue` 表（3 Lane 已合并） |
| [2026-04-18-007-name-identity-gate](./2026-04-18-007-name-identity-gate.md) | Round 7.17：canonical_name ↔ canonical_name_en LLM 门；solution 记录 full scan 230/557 污染并接入 `pipeline_issue`，清除/backfill 结果需以 source_backfills 或运行报告为准 |
| [2026-04-18-008-pipeline-run-id-trace](./2026-04-18-008-pipeline-run-id-trace.md) | Round 7.16 phase 1：V007 迁移 + 40,834 行 legacy_backfill 回填。phase 2 writer wiring 延后 |

## 📖 使用规则

- 想知道**数据质量现在到哪一步**：先看 `2026-04-18-005`（Round 7.x 系列全景）。
- 想知道**下一波架构主线**：看 `2026-04-17-005`（企业 KG 架构，当前北极星；已 partial）+ `2026-04-17-002`（教授 STEM 并行重建）。
- 想知道**Round 7.17 name gate 如何工作**：`2026-04-18-007` + [solutions/data-quality/name-identity-gate-round-7-17-2026-04-18](../solutions/data-quality/name-identity-gate-round-7-17-2026-04-18.md)。
- 想知道**run_id trace phase 2 还差什么**：`2026-04-18-008` §3.2–§3.3。
- 想知道**用户对话 / Agentic RAG 状态**：先看 `2026-04-20-003`，再看本页 M0–M6 状态校准；不要把操作手册等同于验收完成。
- 想知道**管理后台教授 UI 状态**：`2026-04-18-004`；当前有 `/browse` 静态控制台、后端 API 和 React SPA 页面，仍需字段映射/体验验收。

## 🗑️ 已删除的历史计划

以下计划已从 repo 删除，内容完全被后续计划吸收（如需查阅请 `git log --all -- docs/plans/`）：

- `2026-04-05-001-feat-professor-enrichment-pipeline-v2-plan`（v2，被 v3 取代）
- `2026-04-06-001-feat-admin-console-phase2-upgrade-plan`（被 2026-04-18-004 + 006 吸收）
- `2026-04-06-002-professor-pipeline-v3-redesign`（纯架构 historical）
- `2026-04-06-003-feat-professor-pipeline-v3-implementation-plan`（Umbrella，已被 2026-04-16/17 系列细化）
- `2026-04-17-004-shenzhen-stem-knowledge-graph-retrieval-and-ops-architecture-plan`（被 `2026-04-17-005` 明确取代）
