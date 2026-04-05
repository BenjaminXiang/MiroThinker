# 深圳科创数据平台 — 文档导航

## 文档层级

本项目采用**分层文档结构**：

- **共享技术规范**（[Data-Agent-Shared-Spec.md](./Data-Agent-Shared-Spec.md)）是所有数据域的权威源，定义架构、契约、质量标准和 MiroThinker 实现映射
- **各域 PRD** 只定义该域的特有需求（数据来源、字段差异、采集流程、域特有校验）
- **服务层 PRD**（[Agentic-RAG-PRD.md](./Agentic-RAG-PRD.md)）定义面向用户的检索和对话能力

当共享规范与域 PRD 冲突时，以共享规范为准。

## 文档依赖关系

```
Data-Agent-Shared-Spec.md          ← 权威源
  ├── Company-Data-Agent-PRD.md
  ├── Professor-Data-Agent-PRD.md
  ├── Paper-Data-Agent-PRD.md
  └── Patent-Data-Agent-PRD.md

Agentic-RAG-PRD.md                 ← 消费四域数据的服务层
  └── Multi-turn-Context-Manager-Design.md
```

跨域依赖：

- 论文域依赖教授 roster 作为采集锚点
- 论文信号反哺教授画像（`research_directions`、`profile_summary`）
- 企业↔教授：通过企业库匹配 + 公开证据建立关联
- 企业↔专利：通过标准化申请人名称建立关联
- 教授↔专利：通过发明人 + 所属机构建立关联

## 文档清单

### 产品需求与架构

| 文档 | 用途 | 状态 |
|------|------|------|
| [Data-Agent-Shared-Spec.md](./Data-Agent-Shared-Spec.md) | 四域共享架构、契约、质量标准 | 活跃 |
| [Company-Data-Agent-PRD.md](./Company-Data-Agent-PRD.md) | 企业域特有需求 | 活跃 |
| [Professor-Data-Agent-PRD.md](./Professor-Data-Agent-PRD.md) | 教授域特有需求 | 活跃 |
| [Paper-Data-Agent-PRD.md](./Paper-Data-Agent-PRD.md) | 论文域特有需求 | 活跃 |
| [Patent-Data-Agent-PRD.md](./Patent-Data-Agent-PRD.md) | 专利域特有需求 | 活跃 |
| [Agentic-RAG-PRD.md](./Agentic-RAG-PRD.md) | 检索增强智能体（服务层） | 活跃 |
| [Multi-turn-Context-Manager-Design.md](./Multi-turn-Context-Manager-Design.md) | 多轮对话上下文管理器设计 | 活跃 |

### 使用说明

| 文档 | 用途 | 状态 |
|------|------|------|
| [Professor-Pipeline-V2-User-Guide.md](./Professor-Pipeline-V2-User-Guide.md) | 教授 Pipeline V2 使用说明（运行、配置、检索、排查） | 活跃 |

### 设计文档与实现计划

| 文档 | 用途 | 状态 |
|------|------|------|
| [教授 Pipeline V2 设计规范](./superpowers/specs/2026-04-05-professor-enrichment-pipeline-v2-design.md) | 教授管线 v2 全面改造设计 | 已实现 |
| [Agentic RAG 实现计划](./superpowers/plans/2026-03-31-agentic-rag-implementation.md) | RAG 服务层实现路线图 | 待启动 |
| [Admin Console 计划](./plans/2026-04-04-001-feat-admin-console-plan.md) | 管理后台功能计划 | 已实现 |
| [教授 Pipeline V2 计划](./plans/2026-04-05-001-feat-professor-enrichment-pipeline-v2-plan.md) | 教授管线 v2 实现计划 | 已实现 |

### 经验沉淀

| 文档 | 用途 |
|------|------|
| [Admin Console 模式](./solutions/admin-console-fastapi-sqlite-patterns-2026-04-04.md) | FastAPI + SQLite 分页、LIKE 转义、路由冲突 |
| [教授 Pipeline V2 部署](./solutions/professor-pipeline-v2-deployment-patterns-2026-04-05.md) | Milvus Lite、嵌入模型、域名匹配、代理 SSL |
| [数据代理 E2E 门控](./solutions/workflow-issues/data-agent-real-e2e-gates-2026-04-02.md) | 真实 E2E 验收标准 |

---

## 术语表

以下术语在所有文档中必须使用统一名称。

### 摘要字段

| 统一术语 | 适用域 | 含义 |
|----------|--------|------|
| `profile_summary` | 教授、企业 | 用户向画像摘要，200-300 字中文，用于语义检索和介绍 |
| `evaluation_summary` | 教授、企业 | 事实性评价摘要，100-150 字，基于客观指标 |
| `technology_route_summary` | 企业 | 技术路线摘要，面向路线对比和差异分析 |
| `summary_zh` | 论文 | 四段式结构化中文摘要（what / why / how / result） |
| `summary_text` | 论文、专利 | 用于 embedding 的完整摘要文本（论文由 `summary_zh` 拼接而成） |

### 来源与质量

| 统一术语 | 含义 | 不再使用 |
|----------|------|----------|
| `evidence` | 来源证据字段集合（类型、URL、时间、证据片段） | ~~`sources`~~ |
| `quality_status` | 对象质量状态：`ready` / `needs_review` / `low_confidence` | ~~`confidence`~~、~~`completeness_score`~~ |
| `last_updated` | 对象最后更新时间 | — |

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

每条对象的 `evidence` 字段为上述结构的数组。

### ID 前缀

| 域 | 前缀 | 示例 |
|----|------|------|
| 教授 | `PROF-` | `PROF-a1b2c3` |
| 企业 | `COMP-` | `COMP-x7y8z9` |
| 论文 | `PAPER-` | `PAPER-d4e5f6` |
| 专利 | `PAT-` | `PAT-g7h8i9` |

### 去重主锚点

| 域 | 主锚点 | 辅助信号 |
|----|--------|----------|
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
|------|------|--------|--------|----------|
| 去重准确率 | ≥ 95% | 含已知重复对的标注集 | ≥ 100 对 | 人工判定是否为同一实体 |
