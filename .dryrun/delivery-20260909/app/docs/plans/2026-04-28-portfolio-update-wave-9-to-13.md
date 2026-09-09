---
title: Plan Portfolio Update — Wave 9–13
date: 2026-04-28
owner: claude
status: active
supersedes: docs/plans/2026-04-16-007-plan-portfolio-execution-roadmap.md
---

# Plan Portfolio Update — Wave 9–13

接续 [2026-04-16-007 portfolio roadmap](./2026-04-16-007-plan-portfolio-execution-roadmap.md)。原 roadmap 起草于 2026-04-16，**早于** Round 7.6→7.17、Round 8c、Agentic RAG M0.1→M6 全系列；其 Execution Authority 列表已不再反映现实。本计划取而代之，并把会话累积 review 找到的 **28 项 gap** 编入具体 wave。

## 0. 取代关系

- `2026-04-16-007` 标记为 **superseded**（保留为 reference / 历史）
- 本计划成为新的 **Level 1 Portfolio Meta Authority**
- 当前 PR/spec 冲突仍以 `docs/Data-Agent-Shared-Spec.md` 为第一裁决源（§8.3 同步要求生效）

## 1. 现状快照（2026-04-28）

### 1.1 自 2026-04-16 以来已 ship

- **数据质量防线**：Round 7.6 / 7.8 / 7.9 / 7.10' / 7.13 / 7.14 / 7.15 / 7.16-phase1 / 7.17 完整 LLM-优先质量门
- **管道验证台**：Round 8c `/browse` 三 tab + `pipeline_issue` 表（V006）
- **Agentic RAG M0.1–M6**：reranker client + identity gate v2 + ORCID backfill + homepage paper ingest (M2.1–M2.4) + retrieval service (M3) + chat routes + Serper rerank fallback (M4 + M5.2) + profile reinforcement (M6)
- **admin-console**：FastAPI + React 一期；chat UI v3.1（classifier A/B/D/E/F/G + Round 10 v2 SessionContext + Round 11 v3.1 D/E/G handlers）
- **Canonical 主 schema**：V003–V011 alembic（含 V007 run_id、V009 canonical_name_zh/en、V011 RAG 表）
- **文档治理**：CLAUDE.md / AGENTS.md / docs/index.md 同步代码现实；Shared-Spec §2/§3/§4/§5/§6/§7/§8 校准；rm 3 份 legacy 文档；术语表与 6 列状态矩阵建立

### 1.2 累积未闭环 gap（28 项）

按域分组（编号在后续 wave 表中引用）：

**A. 服务层 / 检索域覆盖**
1. Company 域接入 `RetrievalService`
2. Patent 域接入 `RetrievalService`
3. Company / Patent Milvus collection 建立
4. `get_object` / `get_related_objects` 实装

**B. PRD 字段暴露 gap**
5. 教授 `h_index` / `citation_count` / `paper_count` 在 admin API / chat profile / Milvus schema 统一暴露
6. 企业 `technology_route_summary` LLM 增强版
7. 论文 V011 字段（`full_text_url` / `title_resolution_cache_key`）对外暴露

**C. Round 7.x / 8c 收尾**
8. Round 7.16 phase 2 全 writer wiring `run_id`
9. Round 7.17 178/557 污染清除量化日志归档
10. `pipeline_issue` triage SLA（trigger → triage → close 运行口径）

**D. Agentic RAG 完整化**
11. C 类型作为一级 classifier 类型
12. G 类型多候选澄清对话
13. D 类型多轮收窄 + 专利第二轮
14. E 类型完整 Web Search + LLM 综合答案 + "综合自网络搜索"显式标注
15. 100 条意图识别基准集（PRD §F-R1）

**E. Multi-turn Context 完整化**
16. SessionContext 持久化（Postgres / Redis）
17. paper / company / patent 入栈
18. `ResultRef` 结构化引用
19. 话题切换检测
20. `current_module` 显式切换语义

**F. 主 KG / STEM 重建**
21. Company 主 KG 统一迁移（plan 2026-04-17-005）
22. Professor STEM Lane 1 核心采集（plan 2026-04-17-002 拆解）

**G. 评测 / 验收基础设施**
23. 各域真实 E2E dogfood 结果归档机制
24. 4 域 retrieval Top-K 准确率基准

**H. UI / 用户层**
25. admin-console `RecordDetail.tsx` 字段映射完整性验证
26. 用户 chat UI 完整放量（plan 2026-04-18-001）

**I. 流程 / 文档治理**
27. Shared-Spec §8.3 "1 周同步时限" enforcement
28. `api.md` 历史中真实 Serper key 清理

**J. M-series 验收收尾**
29. **M2.4 主页论文采集 dogfood 验收**（R3 gate：10 profs × ≥ 15 papers/prof 挂链）—— 代码 + 单测齐全，但 `docs/solutions/integration-issues/homepage-paper-ingest-dogfood-template-2026-04-22.md` 仍为 `status: template-pending-execution`；真实 `professor_paper_link.evidence_source_type='personal_homepage'` 行数无证据归档

**K. admin-console 双存储分裂（2026-04-30 发现，严重）**

admin-console 当前同时维护两套存储后端，**React UI 几乎全部读旧 SQLite 快照，与 canonical Postgres `miroflow_real` 严重脱钩**：

| 模块 | 存储 | 用户面 |
|---|---|---|
| `chat.py` / `dashboard.py` / `data.py` / `review.py` / `pipeline.py` / `pipeline_issues.py` | **Postgres `miroflow_real`** | `/browse` + 后端 `/api/data/*` |
| `domains.py` (6 路由) / `batch.py` / `export.py` / `upload.py` | **SQLite `released_objects`** | **React SPA 全部** (DomainList / RecordDetail / 批量 / 导出 / 上传) |

实测证据（2026-04-30 同一台机器、同一 backend、同一查询 `institution=清华大学深圳国际研究生院`）：
- `/api/professor`（React 调，走 `domains.py` → SQLite）→ `total=4`
- `/api/data/professors`（browse 调，走 `data.py` → Postgres）→ `total=249`

衍生 gap：

30. **数据展示分裂**：React 列表 / 详情 / 关联 / 过滤选项 4 个查询路径全部读 SQLite，与 canonical 数据脱钩。Postgres 中存在但 SQLite 没有的字段在 React 上完全不可见
31. **写入面 silent failure**：React PATCH `/api/{domain}/{id}` 改字段、DELETE、批量 quality 标记只写 SQLite，**canonical Postgres 完全不感知**；下游 chat / retrieval / `/browse` 看不到这些改动；运营在 React 上的编辑事实上无效
32. **上传/导出与 canonical 解耦**：React 上传 xlsx/CSV → SQLite，不进 canonical 主线；React 导出的是 SQLite 旧快照，不是当前生产数据
33. **SQLite store 去留决策**：✅ **2026-05-01 已决定 deprecate**。退役条件：W10-6.1–6.4 完成、`domains.py` / `batch.py` / `export.py` / `upload.py` 全部切 canonical Postgres 后，Wave 13 内 git rm `SqliteReleasedObjectStore` + `backend/deps.py` 中 `get_store`

34. **`/browse` 长期退役**：✅ **2026-05-01 已决定**。原因：与 React SPA 高度重复 + 数据源分裂（实测 4 vs 249 教授），双面并存制造持续认知混淆。执行节奏：**先数据统一（Wave 10），后端口迁移 + git rm（Wave 13）**。不一刀切；Wave 10 完成后 React 与 `/browse` 数据一致，再启动迁移
35. **`/browse` 独有能力的 React 港口迁移**：provenance / coverage / review / pipeline-issue 4 个 tab 当前只在 `/browse` 有，React SPA 没对应页。退役前必须先在 React 建对应页面消费同一批 `/api/pipeline/*` / `/api/review/*` / `/api/pipeline-issues/*` 端点
36. **legacy `chat.html` 退役**：`backend/static/chat.html` 已被 React `Chat.tsx` 完全覆盖；与 `browse.html` 一并 git rm（Wave 13）

## 2. Wave 排布

四个结构性优先级由 2026-04-28 的 AskUserQuestion 决定：

- Wave 9：5 项打包（A+B+C+D + M2.4 dogfood 验收）
- Wave 10 / 11：**并行**（数据层 vs chat 层文件边界清晰）
- Wave 12：纳入 STEM Lane 1（其余 Lane 2/3 暂不做）+ Company 主 KG（季度内必须落地）
- Wave 13：长尾 / 治理

### 2.1 Wave 9 — 收尾 + 验收基础（≤ 2 周）

**入口条件**：本计划合入 → 启动；W9-5 还需 V011 alembic 已应用到 `miroflow_real`
**完成口径**：5 项 deliverable 全部 ship + 测试覆盖 + 数据证据归档

| # | 项 | gap | Owner | 主要产物 |
|---|---|---|---|---|
| W9-1 | 教授学术指标 3 层暴露 | #5 | codex | 详细设计契约：[.agents/specs/2026-04-30-w9-1-prof-academic-metrics.md](../../.agents/specs/2026-04-30-w9-1-prof-academic-metrics.md)（已 ready-for-codex）<br>(a) V012 alembic：professor 表加 `h_index` / `citation_count` / `paper_count` / `metrics_computed_at` / `metrics_source` 5 列<br>(b) `professor/openalex_metrics.py`（新建）+ `canonical_writer.upsert_professor_metrics` 写入<br>(c) admin API `/api/data/professors` 加 3 字段；删 `verified_paper_count`（统一 `paper_count`）<br>(d) `professor_profiles` Milvus collection 加 3 metadata；vectorize 时填入；retrieval 排序留 W11<br>(e) chat profile core_facts 加 3 字段；browse.html 列定义同步<br>**⚠ 注**：W9-1 完成后，`/browse` + chat 可见新字段，但 **React DomainList / RecordDetail 因走 SQLite store 仍不可见**——需要 W10-6.1（domains.py 切 Postgres）配套 |
| W9-2 | Round 7.16 phase 2 全 writer wiring `run_id` | #8 | codex | 所有 canonical writer（professor / company / paper / patent）显式传递真实 `run_id`；废止 `legacy_backfill` 占位的写入路径；CI 加守门测试 |
| W9-3 | 100 条意图识别基准集 | #15 | claude + codex | (a) `apps/admin-console/tests/fixtures/intent_classifier_benchmark.jsonl` 100 条 A/B/C/D/E/F/G 标注<br>(b) `tests/test_classifier_benchmark.py` 在 CI 跑准确率门控 ≥ 90%（PRD §F-R1）<br>(c) 不达标自动 fail PR |
| W9-4 | Round 7.17 178/557 清除量化日志归档 | #9 | codex | `scripts/run_name_identity_scan.py` 加 JSON 输出落 `docs/source_backfills/round-7-17-name-identity-clear-2026-04-28.jsonl`；附 README 说明字段；`source_backfills/README.md` 增条目 |
| W9-5 | M2.4 主页论文采集 dogfood 验收（R3 gate） | #29 | operator + claude | (a) Pre-flight：确认 V011 已 `alembic upgrade` 到 `miroflow_real`；33 个 V011 相关 pytest 全过<br>(b) Dry-run：`scripts/run_homepage_paper_ingest.py --dry-run --limit 10`，记录 per-prof JSONL<br>(c) Wet-run：选 5 个 dry-run 干净的 profs 跑真实写入 `--limit 5`<br>(d) SQL 校验：`professor_paper_link.evidence_source_type='personal_homepage'` 行数 / `paper_full_text` 来源分布 / `paper_title_resolution_cache` 命中率 / `pipeline_issue` 类型计数<br>(e) 重命名模板 → `docs/solutions/integration-issues/homepage-paper-ingest-dogfood-2026-04-XX.md`，`status: complete`<br>(f) `docs/index.md` Paper 行"数据/E2E 证据"列把模板链接换为实际归档；6 列状态矩阵中 Paper 行可考虑由 🟡 升级条件之一是 R3 gate 通过 |

### 2.2 Wave 10 — 服务层 4 域全覆盖（与 Wave 11 并行，3–4 周）

**入口条件**：W9-1 完成（Milvus schema 模板建好，W10-1/2 复用流程）
**完成口径**：`_VALID_DOMAINS = {"professor", "paper", "company", "patent"}`，4 域语义检索可用并有测试

| # | 项 | gap | Owner |
|---|---|---|---|
| W10-1 | Company Milvus collection 建立 + 回填 | #1, #3 | codex |
| W10-2 | Patent Milvus collection 建立 + 回填 | #2, #3 | codex |
| W10-3 | `RetrievalService._VALID_DOMAINS` 扩到 4 域；`_search_domain` 新分支；`_row_to_evidence` 适配 | #1, #2 | codex |
| W10-4 | Company `technology_route_summary` LLM 增强版 | #6 | codex |
| W10-5 | `get_object` / `get_related_objects` 实装 | #4 | codex |
| **W10-6** | **admin-console 全部 React UI 切到 canonical Postgres**（双存储分裂修复）| **#25, #30, #31, #32, #33** | claude + codex | **见下方 W10-6 子项展开** |

#### W10-6 子项展开

原"RecordDetail 字段映射验证"严重低估范围。实际是 backend 8 个端点 + 4 个 React 操作面的存储后端切换。

| 子项 | 项 | 主要产物 |
|---|---|---|
| W10-6.0 | ~~架构决策~~ | ✅ **2026-05-01 已选 B**：改后端 `domains.py` 内部切 Postgres，前端 URL 不变。6 个 handler 重写为 Postgres 查询，输出 schema 保持 `ReleasedObject`；写入面（PATCH/DELETE/batch）对 canonical 表生效；前端零改动。详见 spec `.agents/specs/2026-04-30-admin-console-architecture.md` §8.1 |
| W10-6.1 | **`domains.py` 6 路由切 Postgres** | `list_domain` / `get_domain_object` / `get_filter_options` / `update_record` (PATCH) / `delete_record` (DELETE) / `get_related` 全部从 `SqliteReleasedObjectStore` 切到 Postgres 查询；与 `data.py` 已有的 SQL 复用或同源；**这一项是 W9-1 的 React 可见性前置** |
| W10-6.2 | **`batch.py` 切 Postgres** | 批量 quality 标记 / 批量删除直接对 canonical 表生效，不再写 SQLite |
| W10-6.3 | **`export.py` 切 Postgres** | React 导出当前生产数据，不是 SQLite 旧快照 |
| W10-6.4 | **`upload.py` 切 canonical 主线** | 决定上传目标：是写入 `source_page` raw 层并触发 pipeline，还是直接对 canonical 表 upsert；可能需要新设计 |
| W10-6.5 | **SQLite `released_objects` store 退役** | 全部 React 路径完成切换后，git rm `data_agents/storage/sqlite_store.py` + `backend/deps.py` 中 `get_store` / `get_sqlite_store`；移除 `ADMIN_DB_PATH` 环境变量；保留 1 个 commit hash 作为回滚锚 |
| W10-6.6 | **数据一致性验证** | 跑回归：`/api/professor` 与 `/api/data/professors` 返回一致；`/api/{domain}/{id}` 详情字段集与 `/api/data/{domain}s/{id}` 一致；React 上的编辑能在 `/browse` 立即看到 |

### 2.3 Wave 11 — Agentic RAG 类型完整化 + Multi-turn 持久化（与 Wave 10 并行）

**入口条件**：W9-3 完成（基准集就绪，给 W11 提供回归门）
**完成口径**：A/B/C/D/E/F/G 全部一级实装；benchmark 准确率达 PRD §F-R1 ≥ 90%；SessionContext 跨进程重启不丢失

| # | 项 | gap | Owner |
|---|---|---|---|
| W11-1 | C 类型一级 classifier + handler（基于 SessionContext 跨域跳转） | #11 | codex |
| W11-2 | G 类型多候选澄清对话（多候选 → 主动追问 → 上下文记录） | #12 | codex |
| W11-3 | D 类型多轮收窄 + 专利第二轮 | #13 | codex |
| W11-4 | E 类型完整 Web Search + LLM 综合答案 + "综合自网络搜索"显式标注 | #14 | codex |
| W11-5 | SessionContext 持久化（默认 Postgres，Redis 备选） | #16 | codex |
| W11-6 | paper / company / patent 入栈（`_record_and_return` 扩展） | #17 | codex |

### 2.4 Wave 12 — 主 KG + STEM Lane 1（季度内必落地，6–10 周）

**入口条件**：Wave 9 完成；不阻塞 Wave 10/11，可并行启动
**完成口径**：Company 主 KG 写入路径在产；Professor STEM Lane 1 核心采集回填完毕

| # | 项 | gap / plan | Owner |
|---|---|---|---|
| W12-1 | Company 主 KG 统一迁移 | #21 / plan 2026-04-17-005 | codex |
| W12-2 | Professor STEM Lane 1 核心采集修复 | #22 / plan 2026-04-17-002 (Lane 1 only) | codex |
| W12-3 | 论文 V011 字段（`full_text_url` / `title_resolution_cache_key`）对外暴露 | #7 | codex |

**显式排除**（暂不做，Wave 12 完成后再评估）：
- STEM plan 2026-04-17-001 存储重构 (Lane 2)
- STEM plan 2026-04-17-002 三 Lane 并行编排 (Lane 3)
- STEM plan 2026-04-17-003 后续残留收尾

### 2.5 Wave 13 — 长尾 / 治理

**入口条件**：Wave 11 / 12 完成大头后启动
**完成口径**：6 项 gap 全部归档

| # | 项 | gap | Owner |
|---|---|---|---|
| W13-1 | Multi-turn 完整化：`ResultRef` + 话题切换 + `current_module` 切换 | #18, #19, #20 | codex |
| W13-2 | E2E dogfood 归档机制 + 4 域 retrieval Top-K 基准 | #23, #24 | codex |
| W13-3 | 用户 chat UI 完整放量 | #26 / plan 2026-04-18-001 | claude + codex |
| W13-4 | Shared-Spec §8.3 1 周同步时限 enforcement hook（pre-commit + CI 检查 alembic 与 spec 同步） | #27 | claude |
| W13-5 | `api.md` 仓库历史 key 清理（git filter-repo / BFG） | #28 | claude |
| W13-6 | `pipeline_issue` triage SLA（trigger → triage → close 运行口径） | #10 | claude |
| **W13-7** | **`/browse` 三 tab 迁到 React 4 个新页**：`Provenance.tsx` / `Coverage.tsx` / `Review.tsx` / `PipelineIssues.tsx`（端点保持 `/api/pipeline/*` / `/api/review/*` / `/api/pipeline-issues/*` 不变，UI 重写） | #35 | codex |
| **W13-8** | **`/browse` 退役**：git rm `backend/static/browse.html` + `chat.html`；移除 `backend/main.py:62-73` 的 `/`、`/browse`、`/chat` 路由；`/` 改为重定向到 React Dashboard | #34, #36 | codex |
| **W13-9** | **SQLite released_objects store 退役**：git rm `data_agents/storage/sqlite_store.py`；移除 `backend/deps.py` 中 `get_store` / `get_sqlite_store`；移除 `ADMIN_DB_PATH` 环境变量 | #33 | codex |

## 3. Authority Stack（更新）

- **L1 Portfolio Meta Authority**：本计划 `2026-04-28-portfolio-update-wave-9-to-13.md`
- **L2 Wave-level Specs**：每 Wave 启动时由 claude 在 `.agents/specs/` 起设计契约 + `.agents/handoffs/` 给 codex
- **L3 Domain Plans**：gap 引用的各域专项 plan（2026-04-17-005、2026-04-08-001、2026-04-18-001 等）
- **L4 Completed Closure Records**：2026-04-16 系列、2026-04-18 系列已完成 plans、Round 7.x / M0–M6 系列
- **L5 Historical Design Context**：2026-04-16-007（superseded by this plan）；V2 系列已 git rm

## 4. Done Definitions（共享口径）

每个 gap 的 close 必须满足以下 5 项，否则不视为完成：

1. **代码证据**：实现位于 `apps/` 或 `libs/`，commit hash 绑定 gap 号
2. **测试证据**：相关 pytest 通过；新增/修改的契约必须带回归测试
3. **数据 / E2E 证据**：真实 E2E 或样本数据归档到 `docs/source_backfills/` 或 `docs/solutions/`
4. **契约同步**（影响 schema/API 时）：1 周内更新 `docs/Data-Agent-Shared-Spec.md`（§8.3 强制）
5. **状态矩阵更新**：`docs/index.md` 6 列矩阵的对应行升级，gap 在本文件 §1.2 划线 + 标 closing commit

## 5. 节奏建议

- **Wave 9** 启动后立即起 4 个 `.agents/specs/2026-04-28-w9-*` 设计契约
- **Wave 10 / 11** 并行启动，建议两个 git worktree 分别承载（`worktree-w10/` 数据层、`worktree-w11/` chat 层），避免 admin-console 与 data_agents 的合并冲突
- **Wave 12** 在 Wave 9 完成后即可启动，与 10/11 部分并行（owner 资源允许时）
- 每 Wave 结束写一份 closure record 到本文件 §1.1，并更新 `docs/plans/index.md`

## 6. 与 docs/Data-Agent-Shared-Spec.md 的衔接

本计划交付的契约级变更（W9-1 教授指标、W10-3 4 域 retrieval、W11-5 SessionContext 持久化、W12-1 Company KG 等）必须在合入主干 1 周内同步到 Shared-Spec：

- W9-1 → §4.3 教授节"可选学术指标"由 🟡 升级为 ✅；§7.2 教授校验补字段一致性
- W10-3 → §2.3 / §4.6 / §6.2 移除 "company / patent 规划中" 注；`_VALID_DOMAINS` 描述同步为 4 域
- W10-6 → §6.1 第 4 层（发布层）说明删除"SQLite released_objects"作为发布快照源；明确 admin-console 全部 React UI 直接消费 canonical Postgres；§4.2 / §4.3 字段表加"对外读路径"列指向 `/api/data/*`
- W11-5 → §4.2 在 `quality_status` 后或独立段说明 SessionContext 持久化已落地
- W12-1 → §5.1 Company 强制规则补主 KG 入产口径

## 7. 风险与开放问题

- **资源**：Wave 10 + 11 并行需要 codex 双 worktree 工作；如人力不足应优先 W11（用户面价值）
- **STEM Lane 1 vs Lane 2 边界**：W12-2 仅做核心采集修复，可能遇到存储瓶颈再触发 Lane 2，那时需重新决策
- **chat UI 放量时机**：W13-3 受 Wave 11 完成度影响；如 11 完成且 benchmark ≥ 90% 即可解 BLOCK
- **Company KG 与 Wave 10 顺序**：W12-1（KG 写入）与 W10-1/3（Company retrieval）有数据依赖，需在 W10 设计时预留 KG 写入路径

### 7.1 W10-6 架构决策（已锁定 — 2026-05-01）

✅ **方案 B 选定**：改后端 `domains.py` 内部切 Postgres，前端 URL 不变。

实施要点：
- `domains.py` 的 6 个 handler 重写为 Postgres 查询，输出 schema 保持原有 `ReleasedObject` shape（`id` / `display_name` / `core_facts` / `summary_fields` / `evidence` / `last_updated` / `quality_status`）
- React 零改动；写入面（PATCH / DELETE / batch / upload）也对 canonical 表生效
- 需要新写 Postgres 版本的 list / detail SQL（不直接复用 `data.py` 因输出 schema 不同）
- 与 `data.py` 短期重复 SQL 是接受的代价；`data.py` 在 W13-8 与 `/browse` 一起 git rm

未选用：
- **A** 改前端 fetchDomainList 走 `/api/data/*`：会强迫 React 4 页重写字段映射，短期摩擦较大
- **C** SQLite + Postgres 双写兼容：复杂度高、易不一致
- **D** 直接 git rm SQLite store：完整切换前 React 整段 break，风险高

详见 spec `.agents/specs/2026-04-30-admin-console-architecture.md` §8.1。

### 7.2 W10-6 与 W9-1 的依赖关系

W9-1 与 W10-6.1 严格不是顺序依赖，但**对 React UI 可见性而言两者必须配套**：

- 只做 W9-1：Postgres 有新字段，`/browse` 与 chat 看得到，但 React UI 看不到
- 只做 W10-6.1：React 切到 Postgres 但字段未补，仍展示空 H-index
- 两个一起做：React UI 完整可见

建议：把 W10-6.0 架构决策放在 Wave 9 启动前，把 W10-6.1（domains.py 切 Postgres）作为 W9-1 的并行支线，由同一个 codex 设计契约一起承载。
