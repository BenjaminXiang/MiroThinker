# 解决方案与经验沉淀索引

`docs/solutions/` 记录已在代码、真实 E2E、发布链路或检索链路中验证过的问题与经验。按分类列出，每条附一句话目的。

## 🔥 当前最常用入口

- [Round 7.17 name-identity gate](./data-quality/name-identity-gate-round-7-17-2026-04-18.md) — canonical_name ↔ canonical_name_en LLM 核验门，生产已触达
- [教授主线当前操作口径](./workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md) — 当前事实 + 执行约定
- [教授主线已收住 / 未收住问题清单](./workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md) — 跟踪待办
- [真实 E2E 验收口径](./workflow-issues/data-agent-real-e2e-gates-2026-04-02.md) — 通用 E2E 约束
- [Serving refresh vs 验收型 E2E 分流](./workflow-issues/professor-serving-refresh-must-use-full-harvest-not-sampled-e2e-2026-04-16.md)

## 🟡 数据质量（`data-quality/`）

- [Round 7.17 — name-identity gate](./data-quality/name-identity-gate-round-7-17-2026-04-18.md) — 🆕 2026-04-18
- [教授-论文缺口根因与补救](./data-quality/professor-paper-gap-root-cause-and-remediation-plan-2026-04-07.md)
- [教授 Pipeline V3 数据缺口分析](./data-quality/professor-pipeline-v3-data-gap-analysis-2026-04-07.md)
- [research_direction cleaner 误过滤 HSS](./data-quality/professor-research-direction-cleaner-overfiltered-hss-fields-2026-04-14.md)
- [homepage root 覆盖 profile_url](./data-quality/professor-homepage-root-overrode-profile-url-2026-04-14.md)

## 🟢 Best Practices（`best-practices/`）

- [学科敏感的教授质量门](./best-practices/discipline-aware-professor-quality-gate-2026-04-14.md)
- [安全搜索去重 + 重复检索告警](./best-practices/professor-safe-search-dedupe-and-duplicate-retrieval-warning-2026-04-15.md)
- [Workbook closure via source backfill](./best-practices/workbook-closure-via-source-backfill-and-serving-side-knowledge-fields-2026-04-16.md)
- [质量门 + 真实数据 Phase A gate](./best-practices/professor-prd-real-data-phase-a-gate-2026-04-14.md)
- [ORCID 官方第二证据源](./best-practices/official-linked-orcid-second-evidence-source-2026-04-15.md)
- [深圳高校 adapter 架构](./best-practices/professor-school-adapter-architecture-for-limited-shenzhen-seeds-2026-04-16.md)
- [Clean shared-store rebuild from batch DBs](./best-practices/professor-clean-shared-store-rebuild-from-batch-dbs-2026-04-17.md) — 🆕 2026-04-17
- [V3 pipeline 性能优化（历史参考）](./best-practices/professor-pipeline-v3-performance-optimization-2026-04-07.md)
- [adapter phase 1 minimal registry（历史参考）](./best-practices/professor-school-adapter-phase1-minimal-registry-and-real-e2e-2026-04-16.md)

## 🔧 Integration Issues（`integration-issues/`）

- [Seed fallback 必须跑赢 homepage redirect/nav 候选](./integration-issues/professor-seed-fallback-must-outrank-homepage-redirect-nav-candidates-2026-04-16.md)
- [Seed context + generic faculty direct-profile 误分类](./integration-issues/professor-seed-context-and-generic-faculty-direct-profile-misclassification-2026-04-16.md)
- [Thread-scoped Playwright browser for threadpool pipeline](./integration-issues/professor-thread-scoped-playwright-browser-for-threadpool-pipeline-2026-04-16.md)
- [官方 publication evidence fallback](./integration-issues/official-publication-evidence-fallback-2026-04-14.md)
- [Gemma-4 LLM 集成（代理 + 兼容性）](./integration-issues/gemma-4-llm-integration-proxy-and-provider-compat-2026-04-06.md)
- [CUHK SSL crawler markdown fallback](./integration-issues/cuhk-ssl-crawler-markdown-fallback-2026-04-07.md)
- [Discovery wave4 hardening（历史参考）](./integration-issues/professor-discovery-wave4-hardening-with-targeted-real-e2e-2026-04-16.md)
- [miroflow-agent 本地测试执行陷阱](./integration-issues/miroflow-agent-local-test-execution-pitfalls-2026-04-17.md) — 🆕 2026-04-17
- [梁永生同名论文污染调查](./integration-issues/professor-liang-yongsheng-same-name-paper-contamination-investigation-2026-04-17.md) — 🆕 2026-04-17
- [官方锚点冲突 vs 外部论文发现](./integration-issues/professor-official-anchor-conflict-vs-external-paper-discovery-2026-04-17.md) — 🆕 2026-04-17
- [STEM API 可用性与风险评估](./integration-issues/professor-stem-api-availability-and-risk-factors-2026-04-17.md) — 🆕 2026-04-17

## 📋 Workflow Issues（`workflow-issues/`）

- [教授 pipeline 当前操作口径](./workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md)
- [教授主线已收住 / 未收住问题清单](./workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md)
- [真实 E2E 验收口径](./workflow-issues/data-agent-real-e2e-gates-2026-04-02.md)
- [Serving refresh 使用完整 harvest](./workflow-issues/professor-serving-refresh-must-use-full-harvest-not-sampled-e2e-2026-04-16.md)
- [论文多源 rollout 必须分期](./workflow-issues/paper-multi-source-rollout-must-be-phased-2026-04-08.md)
- [教授 URL.md → paper closure](./workflow-issues/professor-url-md-ready-paper-closure-2026-04-08.md)
- [测试集答案 workbook 覆盖验证](./workflow-issues/testset-answer-workbook-coverage-validation-2026-04-16.md)
- [STEM 重建当前问题清单](./workflow-issues/professor-stem-rebuild-current-problems-2026-04-17.md) — 🆕 2026-04-17

## 🐛 Logic Errors（`logic-errors/`）

- [V3 quality gate false blocks](./logic-errors/professor-pipeline-v3-quality-gate-false-blocks-2026-04-07.md)

## 📂 通用文档（根目录）

- [admin-console FastAPI + SQLite 模式](./admin-console-fastapi-sqlite-patterns-2026-04-04.md)
- [professor Pipeline V2 部署模式](./professor-pipeline-v2-deployment-patterns-2026-04-05.md)

## 使用规则

- 先看 **🔥 当前最常用入口**，解决大部分场景。
- **🟡 Data Quality** 对应 Round 7.x 系列的污染防线；出现 `canonical_name_en` / 论文同名污染时先看这里。
- **🔧 Integration Issues** 对应"跑不起来"的场景，例如 Playwright、Gemma、SSL。
- **📋 Workflow Issues** 对应"做法不对"的场景，例如 E2E 抽样错误或 refresh 输入错分流。
- 🆕 标注的条目为最近两天新增；老文档保留作为背景参考。
