# 深圳科创数据平台 — 文档导航

> 最后更新：2026-04-24 — 增加"实现状态"列；标注 legacy 与归档文档。

## 快速入口

- [工作区地图](../WORKSPACE.md)
- [**计划索引（活跃 + 完成 + 归档）**](./plans/index.md)
- [解决方案与经验沉淀索引](./solutions/index.md)
- [**Agentic RAG 运维手册**](./Agentic-RAG-Operating-Guide.md) — 当前在线 `/api/chat` 的运维口径
- [架构决策记录（ADR）](./architecture-decisions/README.md)

## 当前主线（2026-04-24）

- **Agentic RAG M0.1–M6 已落地并完成 dogfood**。`/api/chat` 线上支持教授语义检索（B）、企业 + 论文跨域（D）、知识问答（E，含 Serper + reranker fallback）。
  → [Agentic-RAG-Operating-Guide](./Agentic-RAG-Operating-Guide.md) · [plans/2026-04-20-003](./plans/2026-04-20-003-agentic-rag-execution-plan.md) · [plans/2026-04-23-002](./plans/2026-04-23-002-m1-orcid-backfill.md)
- **数据质量防线**：Round 7.x 全系列 LLM-优先质量门（7.6 / 7.8 / 7.9 / 7.10' / 7.13 / 7.14 / 7.15 / 7.16-phase1 / 7.17）已完成。
  → [plans/2026-04-18-005](./plans/2026-04-18-005-data-quality-guards-and-identity-gate.md)
- **管道验证台**：`/browse` 三 tab（provenance / coverage / review）+ `pipeline_issue` 表。
  → [plans/2026-04-18-006](./plans/2026-04-18-006-pipeline-verification-console.md)
- **待启动 / 推进中**：企业主 KG 架构、教授 STEM 并行重建、Paper 多源 Phase B、Multi-turn 上下文管理器、查询类型 A/C/G 上线、用户端对话 UI 完整放量。
  → [plans/2026-04-17-005](./plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md) · [plans/2026-04-17-002](./plans/2026-04-17-002-professor-stem-parallel-rebuild-plan.md) · [plans/2026-04-18-001](./plans/2026-04-18-001-user-chat-interface-plan.md)
- **顶层路线图（波次编排）**：[plans/2026-04-16-007](./plans/2026-04-16-007-plan-portfolio-execution-roadmap.md)

## 文档分层

```
Data-Agent-Shared-Spec.md          ← 权威源（四域共享架构与契约）
  ├── Company-Data-Agent-PRD.md
  ├── Professor-Data-Agent-PRD.md
  ├── Paper-Data-Agent-PRD.md
  └── Patent-Data-Agent-PRD.md

Agentic-RAG-PRD.md                 ← 消费四域数据的服务层
  ├── Agentic-RAG-Operating-Guide.md  ← 对应的运维手册（当前首选运维入口）
  └── Multi-turn-Context-Manager-Design.md  ← 尚未落地

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
| [Data-Agent-Shared-Spec](./Data-Agent-Shared-Spec.md) | 🟡 契约层 ✅；**服务层仅 2/4 域** | `src/data_agents/{contracts,evidence,linking,normalization,publish,runtime}.py`；`service/retrieval.py:14` `_VALID_DOMAINS = {"professor","paper"}` | `apps/miroflow-agent/tests/data_agents/` | [solutions/best-practices/workbook-closure-via-source-backfill](./solutions/best-practices/workbook-closure-via-source-backfill-and-serving-side-knowledge-fields-2026-04-16.md) | company / patent 域未接入检索服务 |
| [Company-Data-Agent-PRD](./Company-Data-Agent-PRD.md) | 🟡 采集/导入/发布 ✅；主 KG 与技术路线未落地 | `src/data_agents/company/*`、`canonical/company.py` | `apps/miroflow-agent/tests/company/`、`admin-console/tests/test_crud.py` | — | 主 KG 统一迁移（plan 2026-04-17-005）；`technology_route_summary` 生成器；企业 Milvus collection |
| [Professor-Data-Agent-PRD](./Professor-Data-Agent-PRD.md) | 🟡 V3 采集 / 画像 / 质量门 ✅；学术指标聚合未暴露 | `src/data_agents/professor/*`（25+ 模块） | `apps/miroflow-agent/tests/professor/`、`admin-console/tests/test_professor_api.py` | [solutions/data-quality/name-identity-gate-round-7-17](./solutions/data-quality/name-identity-gate-round-7-17-2026-04-18.md)、[solutions/workflow-issues/professor-pipeline-current-findings](./solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md) | H-index / 总引用 / 近 5 年论文数 聚合字段（PRD §模块一 R2）；Web Search fallback |
| [Paper-Data-Agent-PRD](./Paper-Data-Agent-PRD.md) | 🟡 主页抓取 + OpenAlex/S2/ORCID 多通路 ✅；多源融合规则化未成型 | `src/data_agents/paper/*`（25 模块）、`scripts/run_homepage_paper_ingest.py` | `apps/miroflow-agent/tests/data_agents/`、`admin-console/tests/test_paper_api.py` | [solutions/integration-issues/homepage-paper-ingest-dogfood-template-2026-04-22](./solutions/integration-issues/homepage-paper-ingest-dogfood-template-2026-04-22.md) | 多源 Phase B；引文关系 |
| [Patent-Data-Agent-PRD](./Patent-Data-Agent-PRD.md) | 🟡 导入 / exact backfill ✅；**未接入检索服务** | `src/data_agents/patent/*` | tests 中 patent 覆盖待核查 | — | 检索服务未覆盖 patent；语义检索；专利-企业/发明人链接在线路径 |
| [Paper-Collection-Multi-Source-Design](./Paper-Collection-Multi-Source-Design.md) | 🟡 Phase A ✅；Phase B 未启动 | 见 [plans/2026-04-08-001](./plans/2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md) | Phase A pytest 通过（记录于 solution） | [solutions/workflow-issues/paper-multi-source-rollout-must-be-phased](./solutions/workflow-issues/paper-multi-source-rollout-must-be-phased-2026-04-08.md) | Phase B 优先级计算 + 权威源切换 |
| [Agentic-RAG-PRD](./Agentic-RAG-PRD.md) | 🟡 A 精确 + B 语义 + D 跨域 + E 知识 + F 拒答 + G 默认高置信 + 有限教授指代（C 子集）✅；完整 C 跨域跳转 / G 多候选澄清对话 / D 专利第二轮 / E 完整 Web+LLM 综合答案 ❌ | `apps/admin-console/backend/api/chat.py`（1720 行，classifier types = `{A,B,D,E,F,G,UNKNOWN}`；`_answer_cross_domain`、`_e_route_filter_scholarly_organics`、Round 11 v3.1 D/E/G handlers）+ `service/retrieval.py` | `admin-console/tests/test_chat_v1.py`、`test_chat_retrieval.py` | — | 意图识别 ≥ 90% 基准集（PRD §F-R1 100 条测试）；C 作为一级类型；D 多轮收窄；E"综合自网络搜索"显式标注 |
| [Multi-turn-Context-Manager-Design](./Multi-turn-Context-Manager-Design.md) | 🟡 进程内 SessionContext + 教授指代消歧 ✅；持久化 / 完整 EntityStack / 跨域上下文 ❌ | `chat.py:548–620` `SessionContext`（`entities`/`turns`/TTL 24h/cookie）+ `:1296–1320` `_record_and_return`（**仅 push professor**） | — | — | Postgres/Redis 持久化（进程重启即丢）；paper/company/patent 入栈；`ResultRef`；`current_module` 切换；话题切换检测 |

## 使用说明 / 工作流

| 文档 | 用途 | 状态 |
|---|---|---|
| [**Agentic-RAG-Operating-Guide**](./Agentic-RAG-Operating-Guide.md) | M0.1–M6 全流水线端到端操作手册（dogfood + 回滚 + 监控） | ✅ 当前首选运维手册 |
| [Codex-Claude-Cross-Review-Usage](./Codex-Claude-Cross-Review-Usage.md) | Codex 主控 + Claude CLI 交叉 review 工作流 | ✅ |
| [quality-status-compatibility](./quality-status-compatibility.md) | `quality_status` 字段兼容性规则 | ✅ 参考 |

> 注：教授 Pipeline V2 用户指南已被 V3 替代，文件已从仓库删除（见下方"归档"段）。V3 的实际操作口径在 [solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16](./solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md)。

## 参考与种子数据

| 文档 / 路径 | 用途 |
|---|---|
| [api.md](./api.md) | Serper / Embedding / Rerank / LLM 样例调用（**注意：包含硬编码 API key，勿对外分享**） |
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
| `evaluation_summary` | 教授、企业 | 事实性评价摘要，100-150 字，基于客观指标 |
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
