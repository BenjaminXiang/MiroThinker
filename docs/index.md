# 深圳科创数据平台 — 文档导航

> 🚨 **2026-06-26 真实 DB 复测纠偏**（read-only scan of `miroflow_real`，proxy 已 unset）。下方 2026-06-22 re-baseline 与状态矩阵的 company/patent 计数**严重过期/错误**，以此为准：
>
> | 域 | 文档旧值 | 2026-06-26 实测 | 备注 |
> |---|---|---|---|
> | company | 1,024 / ready 1,013 | **6,514 / ready 6,514（100%）** | 全 ready，无缺口；identity 全 `resolved` |
> | patent | 1,931 / ready 1,931 | **11,408 / ready 0（全 `partial`）** | `patent_type` 全 NULL → 门控判 `partial` → **0 条可检索**；`summary_text` 100% `fallback_template`（非 LLM）；`professor_patent_link` 0 行（R17 未接线） |
> | professor | 3,387 / ready 1,801 | 3,387 / ready 1,801（一致） | `canonical_name_en` 缺 **77**（非 portfolio 所称 3,314；旧值把"已有"当"缺失"记反） |
> | paper | 97,774 / ready 23,183 / unverified 53,165 | 97,774 / ready 23,183 / **unverified 28,403** / merged+rejected 24,327 | W0b(7,193)+title-cleanup(528) 已 apply；ready-worthy 但未 ready 仅 **66**（门控 bypass 残留） |
>
> **新发现的最高杠杆检索缺口**：patent 0/11,408 ready（`patent_type` NULL 致门控判 `partial`）—— 11,408 条已采集专利因缺一个字段全部不可检索。这是 ingest 映射修复，独立于下方 OpenSpec change。详见 [`openspec/changes/`](../openspec/changes/) 与 [2026-06-26 跨域审计](#)。
>
> 最后更新：2026-06-22 — professor/paper 域按 `miroflow_real` 实测重新校准（见下方 re-baseline 与 [portfolio](./plans/2026-06-22-professor-paper-gap-closure-portfolio.md)）；company/patent 域维持 5/2-5/3 口径。**（注：company/patent 计数已被上方 2026-06-26 纠偏取代。）**
>
> ⚠️ **2026-06-22 re-baseline**（professor/paper 域，read-only 实测）：paper 总数 97,774（`ready` 23,183，非旧"0"）；professor 3,387（`ready` 1,801）；`identity_status` unverified 53,165（W0b-eligible 28,928）；缺 `summary_zh` 72,537。6/15 文档标记的大缺口多项已修：`profile_summary`<200 仅 3、`research_overview` 缺 839、DOI 污染 0、`run_id` 0 null、education 缺 239。下方矩阵 5/4 计数在 professor/paper 行已被本段 supersede；详见 [portfolio](./plans/2026-06-22-professor-paper-gap-closure-portfolio.md) §0。

## 快速入口

- [工作区地图](../WORKSPACE.md)
- [**计划索引（活跃 + 完成 + 归档）**](./plans/index.md)
- [解决方案与经验沉淀索引](./solutions/index.md)
- [**Agentic RAG 运维手册**](./Agentic-RAG-Operating-Guide.md) — 当前在线 `/api/chat` 的运维口径
- [架构决策记录（ADR）](./architecture-decisions/README.md)

## 当前主线（2026-05-04）

- **Agentic RAG 代码路径已扩到 A/B/C/D/E/F/G + 四域 RetrievalService，但不等于完整 PRD 验收完成**。`/api/chat` 已有四域 target、C 跨域跳转、D 多轮收窄、E web fallback、G 澄清、Postgres `SessionStore` 与 `last_result_set`；2026-05-02 100 条意图识别真实基准为 overall `0.690`（B/G 明显不达标），sandbox 因内部 LLM 不可达退成 all `UNKNOWN`。2026-05-04 已补确定性 fallback，本地 benchmark 可跑；仍需 host 真实 LLM E2E 复验。
  → [Agentic-RAG-Operating-Guide](./Agentic-RAG-Operating-Guide.md) · [ADR-008](./architecture-decisions/ADR-008-intent-benchmark-ci-gate.md) · [plans/2026-04-20-003](./plans/2026-04-20-003-agentic-rag-execution-plan.md)
- **四域数据质量与向量层明显前进，但仍有分域验收缺口**。真实 promote 后（professor/paper 计数 2026-06-22 实测，见顶部 re-baseline）：professor `1,801/3,387 ready`，company `1013/1024 ready`，patent `1931/1931 ready`，paper `23,183/97,774 ready`（另有 9,032 `ready`+`unverified`，身份门未收口）；Milvus 全景已有 `professor_profiles` / `paper_chunks` / `company_profiles` / `patent_profiles`。
  → [w13-d2-promote](./source_backfills/w13-d2-promote-2026-05-02.txt) · [w13-3 patent e2e](./solutions/integration-issues/w13-3-patent-e2e-completed-2026-05-02.md)
- **管理台仍是混合形态**。`/browse` 静态控制台仍是 root 入口；React SPA 与 `/chat` 已在，但不是唯一 UI。`main.py` 已默认 `MILVUS_USE_REAL_CLIENT=1`，同时仍存在 CORS `*`、无 auth、上传接口仅 professor 调真实 pipeline，company/paper/patent 主要是记录/交接而非完整在线导入。
  → [plans/2026-04-18-006](./plans/2026-04-18-006-pipeline-verification-console.md)
- **下一轮优先级**：先在 host 复跑 classifier 100-case E2E，再修 paper DOI verify Q-10/Q-11 与 paper Milvus rebackfill；随后补 homepage selector、company Top-5 人工标注、admin auth/upload/React-browse 收敛。
  → [homepage paper ingest dogfood](./solutions/integration-issues/homepage-paper-ingest-dogfood-2026-05-02.md) · [doi verify dry-run](./source_backfills/w13-14-doi-verify-dryrun-2026-05-03.txt) · [company top-5 eval](./solutions/integration-issues/v2-stage3-company-top5-eval-2026-05-02.md)
- **顶层路线图（波次编排）**：[plans/2026-04-16-007](./plans/2026-04-16-007-plan-portfolio-execution-roadmap.md)

## 文档分层

```
Data-Agent-Shared-Spec.md          ← 权威源（四域共享架构与契约）
  ├── Company-Data-Agent-PRD.md
  ├── Professor-Data-Agent-Requirements-Audit-2026-05-09.md  ← 教授域 canonical（用户 2026-05-10 声明；临时，未来 §1–§7 沉淀回 PRD）
  ├── Professor-Data-Agent-PRD.md  ← legacy 参考；行为已被 Audit 取代
  ├── Paper-Data-Agent-PRD.md
  └── Patent-Data-Agent-PRD.md

Agentic-RAG-PRD.md                 ← 消费四域数据的服务层
  ├── Agentic-RAG-Operating-Guide.md  ← 对应的运维手册（当前首选运维入口）
  └── Multi-turn-Context-Manager-Design.md  ← 部分落地：SessionContext 子集已在 chat.py；完整设计未落地

plans/index.md                     ← 执行计划（活跃 + 已完成 + 归档）
solutions/index.md                 ← 经验沉淀（best practices / 问题复盘）
architecture-decisions/            ← ADR（跨任务长期架构决策）
```

当共享规范与域 PRD 冲突时，以共享规范为准。

## 跨域依赖

- **论文 → 教授**：论文以教授 roster 为采集锚点
- **论文 ← 教授**：论文信号反哺教授画像（`research_directions`、`profile_summary`）
- **企业 ↔ 教授**：通过企业库匹配 + 公开证据建立关联
- **企业 ↔ 专利**：通过标准化申请人名称建立关联
- **教授 ↔ 专利**：通过发明人 + 所属机构建立关联

## 产品需求 / 架构（与实现对应）

**图例**：✅ 已实现（有代码 + 测试/数据证据） · 🟡 部分实现（代码在、证据不足或功能有缺口） · 🚧 设计完成未落地 · 📝 纯设计文档

**评级标准**：必须同时提供"代码证据"和"测试/数据证据"才能标 ✅；任一列空缺一律退回 🟡。

| 文档 | 实现状态 | 代码证据 | 测试证据 | 数据 / E2E 证据 | 关键缺口 |
|---|---|---|---|---|---|
| [Data-Agent-Shared-Spec](./Data-Agent-Shared-Spec.md) | 🟡 契约层 ✅；服务层代码已 4/4 域，真实验收未全齐 | `apps/miroflow-agent/src/data_agents/{contracts,evidence,linking,normalization,publish,runtime}.py`；`service/retrieval.py` `_VALID_DOMAINS = {"professor","paper","company","patent"}`；`get_object` / `get_related_objects` 已在 | `apps/miroflow-agent/tests/data_agents/service/test_retrieval*.py` | `professor_profiles 3,387 / paper 97,774 / company_profiles 1,024 / patent_profiles 1,931`（professor/paper 计数 2026-06-22 实测；[w13-3 patent e2e](./solutions/integration-issues/w13-3-patent-e2e-completed-2026-05-02.md)） | Agentic RAG classifier 真实基准未过；company Top-5 待人工标注；paper `ready` 23,183 但 `unverified` 53,165（W0b-eligible 28,928 待收口） |
| [Company-Data-Agent-PRD](./Company-Data-Agent-PRD.md) | 🟡 采集/导入/发布 + narrative + Milvus/检索路径已在；人工准确率未闭环 | `apps/miroflow-agent/src/data_agents/company/*`、`canonical/company.py`、`storage/milvus_collections.py`、`service/retrieval.py` company 分支 | `apps/miroflow-agent/tests/data_agents/company/`、`apps/miroflow-agent/tests/data_agents/service/test_retrieval*.py`、`apps/admin-console/tests/test_crud.py` | [V2 narrative](./solutions/integration-issues/v2-company-narrative-completed-2026-05-02.md)：旧 `1013/1024 = 98.93%`（2026-05-02）；**2026-06-26 实测 6514/6514 = 100% ready**；[Top-5 eval](./solutions/integration-issues/v2-stage3-company-top5-eval-2026-05-02.md)：50/50 有结果，待人工标注 | Top-5 ≥85% 需人工确认；企业关系/别名精度仍需专项 E2E（needs_review 已随全 ready 清零）|
| [Professor-Data-Agent-Requirements-Audit-2026-05-09](./Professor-Data-Agent-Requirements-Audit-2026-05-09.md) | 🟡 教授域 canonical（用户 2026-05-10 声明；临时，未来 §1–§7 沉淀回 PRD）；V3 采集 / 画像 / 质量门 ✅；真实 web fallback 与部分指标验收未闭环 | `apps/miroflow-agent/src/data_agents/professor/*`；V012 指标字段；admin/chat/Milvus 输出字段已补强 | `apps/miroflow-agent/tests/professor/`、`apps/miroflow-agent/tests/data_agents/professor/`、`apps/admin-console/tests/test_professor_api.py` | [w13-d2 promote](./source_backfills/w13-d2-promote-2026-05-02.txt)：旧 `774/787 ready`（2026-05-02）；2026-06-22 实测 `1,801/3,387 ready`；[Round 7.17](./solutions/data-quality/name-identity-gate-round-7-17-2026-04-18.md) | STEM/HSS 质量抽检、真实 Web Search fallback、教授-企业/论文链路准确率仍需 E2E 抽样 |
| [Professor-Requirement-Review-2026-05-10](./Professor-Requirement-Review-2026-05-10.md) | 🟢 决策快照（2026-05-10）；Audit 13+ 主题决策已锁；含 Paper-from-prof-page + Patent-from-prof-page 子流；spec 起草直接照搬 | 决策记录文档，无代码 | — | — | Paper / Patent 全量 review 仍待做（仅 from-prof-page 子流已锁） |
| [Professor-Data-Agent-PRD](./Professor-Data-Agent-PRD.md) | ⚪ legacy 参考（2026-05-10 起）；行为已被 Audit 取代；保留为历史 | — | — | — | 不再用于解释当前需求；详见 [`resolve-professor-canonical-baseline`](../openspec/changes/archive/2026-05-10-resolve-professor-canonical-baseline/) |
| [Paper-Data-Agent-PRD](./Paper-Data-Agent-PRD.md) | 🟡 主页抓取 + OpenAlex/S2/ORCID 多通路在；summary_zh 部分回填；身份核验与 homepage selector 未闭环；2026-05-10 起 PRD §3.2 / §4.2 / §4.3 / §5.2 / §9 等数节决策已在 Review 中锁定，PRD 体内重写为后续 change | `apps/miroflow-agent/src/data_agents/paper/*`、`scripts/run_homepage_paper_ingest.py`、`scripts/run_paper_doi_verify.py`、V018 `summary_zh` | `apps/miroflow-agent/tests/data_agents/paper/`、`tests/scripts/test_run_homepage_paper_ingest.py`、`apps/admin-console/tests/test_paper_api.py` | [V1 summary_zh](./solutions/integration-issues/v1-paper-summary-zh-completed-2026-05-02.md)：旧 `3456/7297 = 47.4%`（2026-05-02）；2026-06-22 实测 paper 97,774，`ready` 23,183，缺 `summary_zh` 72,537，缺 `abstract_clean` ~72,705，`prof_page_only` 空壳死端 66,401；[DOI dry-run](./source_backfills/w13-14-doi-verify-dryrun-2026-05-03.txt)：DOI 污染实测 0（已清） | `identity_status` unverified **28,403**（W0b 7,193 + title-cleanup 528 已 apply；旧 53,165 已过期）；ready-worthy 但未 ready 仅 **66**（门控 bypass 残留）；66,401 标题空壳待源采集；`full_text_fetcher` `no_arxiv_id` 失败 25,860；homepage selector 覆盖不足 |
| [Paper-Requirement-Review-2026-05-10](./Paper-Requirement-Review-2026-05-10.md) | 🟢 决策快照（2026-05-10）；16 条主决策已锁；与 Professor Review 平行；spec 起草直接照搬 | 决策记录文档，无代码 | — | — | PRD/MSD 体内尚未沉淀；6 条 paper-* debt 状态从 open → decision-locked，待后续 change 执行 |
| [Patent-Data-Agent-PRD](./Patent-Data-Agent-PRD.md) | 🟡 导入 / summary / ready / Milvus / chat 专利查询真实跑通；关系准确率仍需抽检 | `apps/miroflow-agent/src/data_agents/patent/*`、`storage/milvus_collections.py` patent collection、`service/retrieval.py` patent 分支、`chat.py` 专利 applicant 查询 | `apps/miroflow-agent/tests/data_agents/patent/test_import_xlsx.py`、`test_release.py`、`test_exact_backfill.py`、retrieval service tests | [W13-3 patent e2e](./solutions/integration-issues/w13-3-patent-e2e-completed-2026-05-02.md)：旧 `1931/1931 ready`（2026-05-02 测试集）；**2026-06-26 实测 11,408 条全 `partial` / 0 `ready`（`patent_type` 全 NULL 致门控判 partial）**，`summary_text` 100% `fallback_template`，`patent_profiles` Milvus 仍为旧 1931（DB 11,408 未 rebackfill） | 🔴 `patent_type` NULL 致 0 可检索（ingest 映射修复）；`professor_patent_link` 0 行（R17 未接线）；申请人 normalize 后续；专利-企业/发明人链接准确率需 E2E |
| [Paper-Collection-Multi-Source-Design](./Paper-Collection-Multi-Source-Design.md) | 🟡 Phase A 代码/单测在；Phase B 未启动 | 见 [plans/2026-04-08-001](./plans/2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md) | paper/provider 单测与 homepage ingest 脚本测试 | [solutions/workflow-issues/paper-multi-source-rollout-must-be-phased](./solutions/workflow-issues/paper-multi-source-rollout-must-be-phased-2026-04-08.md) | Phase A 真实 E2E 结果需单独归档；Phase B 优先级计算 + 权威源切换 |
| [Agentic-RAG-PRD](./Agentic-RAG-PRD.md) | 🟡 A-G 与四域召回代码已在；真实 classifier rerun 阻塞完整验收 | `apps/admin-console/backend/api/chat.py`（`QueryType = A/B/C/D/E/F/G/UNKNOWN`、deterministic fallback、`_TARGET_DOMAINS` 四域、C/D/E/G handlers、Postgres SessionStore）+ `service/retrieval.py` 四域 | `apps/admin-console/tests/test_chat_v1.py`、`test_chat_retrieval.py`、`test_chat_c_handler.py`、`test_chat_session_persistence.py`、`test_classifier_benchmark.py` fallback coverage、retrieval service tests | [ADR-008](./architecture-decisions/ADR-008-intent-benchmark-ci-gate.md)：历史真实 benchmark overall `0.690`；[company chat D 实测](./solutions/integration-issues/v2-stage3-company-top5-eval-2026-05-02.md)；[patent chat 实测](./solutions/integration-issues/w13-3-patent-e2e-completed-2026-05-02.md) | host 复跑 100-case、四域 chat E2E、C 多轮、D 收窄、E 搜索标注与 source trace |
| [Multi-turn-Context-Manager-Design](./Multi-turn-Context-Manager-Design.md) | 🟡 Postgres SessionStore + 四域 entity stack + `last_result_set` 已在；完整上下文产品验收未完成 | `chat.py` `SessionContext`（`entities`/`turns`/`last_result_set`/TTL/cookie）+ `backend/storage/chat_session.py` + V015/V016 | `apps/admin-console/tests/test_chat_c_handler.py`、`test_chat_session_persistence.py` | — | `ResultRef` 完整语义、`current_module`/topic switch 策略、跨进程/重启真实 E2E 和多轮四域用户脚本仍需验收 |

## 使用说明 / 工作流

| 文档 | 用途 | 状态 |
|---|---|---|
| [**Agentic-RAG-Operating-Guide**](./Agentic-RAG-Operating-Guide.md) | M0.1–M6 操作入口；完成度以本页状态矩阵和已归档 dogfood 结果为准 | 🟡 当前运维手册；非完整验收证明 |
| [Codex-Claude-Cross-Review-Usage](./Codex-Claude-Cross-Review-Usage.md) | Codex 主控 + Claude CLI 交叉 review 工作流 | ✅ |
| [quality-status-compatibility](./quality-status-compatibility.md) | `quality_status` 字段兼容性规则 | ✅ 参考 |

> 注：教授 Pipeline V2 用户指南已被 V3 替代，文件已从仓库删除（见下方"归档"段）。V3 的实际操作口径在 [solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16](./solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md)。

## 参考与种子数据

| 文档 / 路径 | 用途 |
|---|---|
| `docs/api.md`（本地 gitignored） | Serper / Embedding / Rerank / LLM 样例调用；真实 key 必须来自环境变量或本地 secret 文件，文档不得写入真实 key |
| [source_backfills/](./source_backfills/README.md) | 补全用的 JSONL / XLSX 数据文件（company knowledge、paper identifiers、patent supplement、professor-company roles 等） |
| [教授 URL.md](./教授%20URL.md) | 种子名单入口 URL 原始列表（实际作为 crawler seed 使用，非设计文档） |

## 🗑️ 已从 repo 删除的历史文档

以下文档已 `git rm`，不再是活跃的设计源。如需查阅请用 `git log --all --diff-filter=D -- <path>`。

- `docs/Professor-Pipeline-V2-User-Guide.md` — 教授 V2 使用指南；V3 已在产（详见 `src/data_agents/professor/*`），V3 操作口径见 [solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16](./solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md)。
- `docs/superpowers/plans/2026-03-31-agentic-rag-implementation.md` — Agentic RAG 早期探索，已被 [plans/2026-04-20-002-agentic-rag-implementation-design](./plans/2026-04-20-002-agentic-rag-implementation-design.md) 与 [plans/2026-04-20-003-agentic-rag-execution-plan](./plans/2026-04-20-003-agentic-rag-execution-plan.md) 取代。
- `docs/superpowers/specs/2026-04-05-professor-enrichment-pipeline-v2-design.md` — 教授 V2 设计，V3 已在产。

已从 repo 删除的历史**计划**见 [plans/index.md](./plans/index.md) 尾部 "🗑️ 已删除的历史计划"。

## 经验沉淀快速入口

- [solutions/index.md](./solutions/index.md)
- [Agentic RAG intent benchmark gate](./architecture-decisions/ADR-008-intent-benchmark-ci-gate.md)
- [Patent W13-3 真实 E2E + Milvus](./solutions/integration-issues/w13-3-patent-e2e-completed-2026-05-02.md)
- [Paper summary_zh full backfill](./solutions/integration-issues/v1-paper-summary-zh-completed-2026-05-02.md)
- [Company narrative + Top-5 eval](./solutions/integration-issues/v2-company-narrative-completed-2026-05-02.md)
- [数据质量 — Round 7.17 name-identity gate](./solutions/data-quality/name-identity-gate-round-7-17-2026-04-18.md)
- [workflow — 教授 Pipeline 当前操作口径](./solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md)
- [workflow — 教授主线已收住 / 未收住问题](./solutions/workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md)
- [best-practices — 工作簿 closure via source backfill](./solutions/best-practices/workbook-closure-via-source-backfill-and-serving-side-knowledge-fields-2026-04-16.md)

---

## 术语表

以下术语在所有文档中必须使用统一名称。

### 摘要字段

| 统一术语 | 适用域 | 含义 |
|---|---|---|
| `profile_summary` | 教授、企业 | 用户向画像摘要，200-300 字中文，用于语义检索和介绍 |
| `technology_route_summary` | 企业 | 技术路线摘要，面向路线对比和差异分析 |
| `summary_zh` | 论文 | 四段式结构化中文摘要（what / why / how / result） |
| `summary_text` | 论文、专利 | 用于 embedding 的完整摘要文本（论文由 `summary_zh` 拼接而成） |

### 来源与质量

| 统一术语 | 含义 |
|---|---|
| `evidence` | 来源证据字段集合（类型、URL、时间、证据片段） |
| `quality_status` | 对象质量状态：`ready` / `needs_review` / `low_confidence` / `needs_enrichment`（4 个 canonical 值，与 `src/data_agents/contracts.py:9` 和 [quality-status-compatibility](./quality-status-compatibility.md) 对齐） |
| `last_updated` | 对象最后更新时间 |
| `run_id` | 生产该行的 `pipeline_run.run_id`（Round 7.16 phase 1 起） |

### `evidence` 统一结构

```json
{
  "source_type": "official_site | xlsx_import | public_web | academic_platform | manual_review",
  "source_url": "https://...",
  "source_file": "qimingpian_export_202603.xlsx",
  "fetched_at": "2026-03-15T10:30:00Z",
  "snippet": "可选证据片段",
  "confidence": 0.95
}
```

### ID 前缀

| 域 | 前缀 | 示例 |
|---|---|---|
| 教授 | `PROF-` | `PROF-a1b2c3` |
| 企业 | `COMP-` | `COMP-x7y8z9` |
| 论文 | `PAPER-` | `PAPER-d4e5f6` |
| 专利 | `PAT-` | `PAT-g7h8i9` |

### 去重主锚点

| 域 | 主锚点 | 辅助信号 |
|---|---|---|
| 企业 | 标准化公司名称 | `credit_code`、官网、法人 |
| 教授 | 姓名 + 学校 + 院系 + 职称 | 邮箱、Scholar ID |
| 论文 | DOI > Arxiv ID > 标题相似度+作者重叠 | — |
| 专利 | 专利号/公开号 | 标题相似度+申请人重叠 |

### 验收标准模板

所有验收标准必须包含：

1. **测试集来源** — 明确指向哪组测试数据
2. **样本量** — 抽样检验需注明最小样本量
3. **评判标准** — "准确"的具体定义（精确匹配/语义相关/人工评估）
4. **评审方式** — 自动化/人工抽检/混合

示例：

| 指标 | 要求 | 测试集 | 样本量 | 评判标准 |
|---|---|---|---|---|
| 去重准确率 | ≥ 95% | 含已知重复对的标注集 | ≥ 100 对 | 人工判定是否为同一实体 |
