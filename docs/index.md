# 深圳科创数据平台 — 文档导航

## 快速入口

- [工作区地图](../WORKSPACE.md)
- [**计划索引（当前状态一表看完）**](./plans/index.md)
- [解决方案与经验沉淀索引](./solutions/index.md)

## 当前主线（2026-04-18）

- **数据质量防线**：Round 7.x 全系列 LLM-优先数据门
  已完成 7.6 / 7.8 / 7.9 / 7.10' / 7.13 / 7.14 / 7.15 / 7.16-phase1 / 7.17。
  → [plans/2026-04-18-005](./plans/2026-04-18-005-data-quality-guards-and-identity-gate.md)
- **管道验证台**：`/browse` 三 tab（provenance / coverage / review）+ `pipeline_issue` 表
  → [plans/2026-04-18-006](./plans/2026-04-18-006-pipeline-verification-console.md)
- **下一波架构主线**：企业主 KG + 教授 STEM 并行重建
  → [plans/2026-04-17-005](./plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md)
  → [plans/2026-04-17-002](./plans/2026-04-17-002-professor-stem-parallel-rebuild-plan.md)
- **顶层路线图（波次编排）**：[plans/2026-04-16-007](./plans/2026-04-16-007-plan-portfolio-execution-roadmap.md)

## 文档分层

```
Data-Agent-Shared-Spec.md          ← 权威源
  ├── Company-Data-Agent-PRD.md
  ├── Professor-Data-Agent-PRD.md
  ├── Paper-Data-Agent-PRD.md
  └── Patent-Data-Agent-PRD.md

Agentic-RAG-PRD.md                 ← 消费四域数据的服务层
  └── Multi-turn-Context-Manager-Design.md

plans/index.md                     ← 执行计划（活跃 + 已完成 + 归档）
solutions/index.md                 ← 经验沉淀（best practices / 问题复盘）
```

当共享规范与域 PRD 冲突时，以共享规范为准。

## 跨域依赖

- **论文 → 教授**：论文以教授 roster 为采集锚点
- **论文 ← 教授**：论文信号反哺教授画像（`research_directions`、`profile_summary`）
- **企业 ↔ 教授**：通过企业库匹配 + 公开证据建立关联
- **企业 ↔ 专利**：通过标准化申请人名称建立关联
- **教授 ↔ 专利**：通过发明人 + 所属机构建立关联

## 产品需求 / 架构

| 文档 | 用途 | 状态 |
|---|---|---|
| [Data-Agent-Shared-Spec](./Data-Agent-Shared-Spec.md) | 四域共享架构、契约、质量标准 | 活跃 |
| [Company-Data-Agent-PRD](./Company-Data-Agent-PRD.md) | 企业域特有需求 | 活跃 |
| [Professor-Data-Agent-PRD](./Professor-Data-Agent-PRD.md) | 教授域特有需求 | 活跃 |
| [Paper-Data-Agent-PRD](./Paper-Data-Agent-PRD.md) | 论文域特有需求 | 活跃 |
| [Patent-Data-Agent-PRD](./Patent-Data-Agent-PRD.md) | 专利域特有需求 | 活跃 |
| [Paper-Collection-Multi-Source-Design](./Paper-Collection-Multi-Source-Design.md) | 论文多源采集设计 | 活跃 |
| [Agentic-RAG-PRD](./Agentic-RAG-PRD.md) | 检索增强智能体（服务层） | 活跃 |
| [Multi-turn-Context-Manager-Design](./Multi-turn-Context-Manager-Design.md) | 多轮对话上下文管理器 | 活跃 |

## 使用说明 / 工作流

| 文档 | 用途 |
|---|---|
| [Professor-Pipeline-V2-User-Guide](./Professor-Pipeline-V2-User-Guide.md) | 教授 Pipeline 运行、配置、检索、排查 |
| [Codex-Claude-Cross-Review-Usage](./Codex-Claude-Cross-Review-Usage.md) | Codex 主控 + Claude CLI 交叉 review 工作流 |
| [quality-status-compatibility](./quality-status-compatibility.md) | `quality_status` 字段兼容性规则 |

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
| `quality_status` | 对象质量状态：`ready` / `needs_review` / `low_confidence` |
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
