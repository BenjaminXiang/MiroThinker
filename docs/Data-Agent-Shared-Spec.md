# 数据采集智能体群 — 共享技术规范

> **本文档是四个数据域的权威源。** 当域 PRD 与本文档冲突时，以本文档为准。
> 术语定义见 [术语表](./index.md#术语表)。各域 PRD 见 [文档导航](./index.md)。

本文档定义 `Company-Data-Agent`、`Professor-Data-Agent`、`Paper-Data-Agent`、`Patent-Data-Agent` 的共享契约：长期架构、域间协作、统一对外字段、质量要求、MiroThinker 实现映射。

共享的是**逻辑契约**，不是底层物理 schema。各域可独立设计物理表结构。

---

## 一、文档定位

### 1.1 共享规范的作用

本规范统一以下内容：

- 长期存储架构与域边界
- 各数据域对线上服务暴露的最小契约字段
- 统一的 filter 语义
- 域间关联的最小要求
- 数据质量、验证、更新与发布要求
- 与当前 MiroThinker 代码实现的衔接方式

### 1.2 不在本文档强制统一的内容

以下内容不要求四个数据域完全一致：

- PostgreSQL 的物理表名和列名
- 原始抓取层、中间清洗层的内部 schema
- 各域内部去重流程的具体实现细节
- 各域 embedding 的生成批次与内部任务拆分
- 离线中间文件目录结构

原则是：

- **逻辑契约强统一**
- **物理 schema 允许独立演进**

---

## 二、整体架构

### 2.1 架构形态

架构形态统一为：

- **PostgreSQL + Milvus**。不区分 dev 与长期形态；所有环境（本地、测试、生产）均按此组织，不再使用 SQLite 作为 dev 代替物。
- 当前部署：`miroflow_real`（生产数据）+ `miroflow_test_mock`（测试 / mock）两个 Postgres 实例并存；向量层使用 Milvus（本地部署为 Milvus-Lite 文件，生产为独立 Milvus 服务）。

设计目标：

- 教授、企业、论文、专利可各自独立维护 PostgreSQL schema（允许同实例多 schema，或各域独立实例）
- 每个数据域可各自维护一组 Milvus collection（示例当前在用：`professor_profiles`、`paper_chunks`；company / patent collection 规划中）
- 线上服务层负责跨域编排，不要求底层合并成一个总库

### 2.2 多库、多 collection 的域边界

推荐的长期形态如下：

| 数据域 | 主 PostgreSQL | 主 Milvus collection | 说明 |
| --- | --- | --- | --- |
| 教授 | professor domain DB | professor profile collections | 教授身份、履历、画像、关联关系 |
| 企业 | company domain DB | company profile collections | 企业骨架、画像、关键人物、关联关系 |
| 论文 | paper domain DB | paper summary collections | 论文事实、摘要、关键词、教授关联 |
| 专利 | patent domain DB | patent summary collections | 专利事实、解释性摘要、申请人/发明人关联 |

这里的“独立”包括：

- 各 Agent 可有各自独立 PostgreSQL 库
- 各 Agent 可有各自独立 schema
- 各 Agent 可有各自独立 collection 划分策略

但独立不等于任意：

- 必须遵守统一的对外契约字段
- 必须遵守统一的 filter 语义
- 必须向服务层暴露稳定 ID 和可追溯来源字段

### 2.3 线上服务层职责

线上服务层显式承担以下职责：

- 查询编排
- 多源召回
- 结果融合
- rerank
- 跨域聚合
- 实时外部 fallback

因此，共享规范不再假设：

- 所有数据都在单一关系库中
- 所有召回都通过一条 SQL 完成
- 各数据域必须复用同一套物理 schema

**当前服务层实现范围（2026-04 状态）**：

- `apps/miroflow-agent/src/data_agents/service/retrieval.py` 中的 `RetrievalService` 当前仅覆盖 `professor` / `paper` 两域（`_VALID_DOMAINS = {"professor", "paper"}`）。
- `company` / `patent` 语义检索能力规划中，见 [plans/2026-04-20-003](./plans/2026-04-20-003-agentic-rag-execution-plan.md) M3 及 [plans/2026-04-17-005](./plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md)。
- 在这两域未接入前，服务层对它们的查询仍走 SQL / 结构化检索回退。

### 2.4 通用离线工作流

四个数据域建议统一采用以下离线流程模型：

1. **源数据进入**
   - xlsx 导入、自写爬虫、官网抓取、学术平台抓取、辅助 Web Search
2. **清洗与标准化**
   - 字段归一化、日期标准化、实体标准化、结构化抽取
3. **去重与关联**
   - 域内去重、跨域关联、关系字段生成
4. **用户向摘要与向量化**
   - 生成用户可读摘要字段，并写入向量索引
5. **发布与验证**
   - 发布到对外契约层（见 §6.1 第 3-4 层：canonical 规范化层 + 发布层）
   - 过 Round 7.x 质量门控：`name_identity_gate`、`paper_identity_gate`、`title_quality` / `topic_quality` gate（见 §7.2 最小自动化校验）
   - `pipeline_issue` 表（V006 起）记录异常与不一致项，供管道验证台回看
   - 做抽样验证、定向补采、生成报告

### 2.5 跨域依赖关系

不再采用“所有域共用一个全局严格 Phase 链”的假设。

当前共享依赖应收敛为：

- `Professor roster -> Paper`
  - 论文周期性采集以深圳教授 roster 为锚点
- `Paper -> Professor enrichment`
  - 论文是教授画像更新的重要输入
- `Company <-> Professor`
  - 教授与企业的关联建立在企业库匹配与公开证据之上
- `Company <-> Patent`
  - 企业与专利通过标准化企业名、申请人、公开证据建立关联
- `Professor <-> Patent`
  - 教授与专利通过发明人、单位、公开证据建立关联

明确取消以下旧假设：

- 企业域必须先完成，教授域才能开始基础采集
- 教授的企业关联必须依赖 `企名片 API`
- 把论文域当成开放式全文献抓取器

---

## 三、与当前 MiroThinker 实现的映射

### 3.1 为什么在 MiroThinker 项目内做这件事

原因不是“文档放在一个仓库里方便”，而是当前仓库已经有一套高价值实现：

- BrowseComp-ZH 表现优异的 agent runtime
- 多轮工具调用编排
- 搜索、网页抓取、PDF/网页抽取、Python 处理工具
- 任务日志、trace、benchmark-style 批量执行框架

这意味着数据采集 Agent 的实现方向，应优先复用现有 MiroThinker 能力，而不是另起一套完全独立的 agent runtime。

### 3.2 当前代码基线

当前与数据采集 Agent 最相关的实现基线分为三组：

#### A. Agent 运行基线（runtime / 通用工具）

- [`pipeline.py`](../apps/miroflow-agent/src/core/pipeline.py) — 统一任务入口，拼装 `ToolManager`、`Orchestrator`、`OutputFormatter`。
- [`orchestrator.py`](../apps/miroflow-agent/src/core/orchestrator.py) — 多轮 agent loop、上下文压缩、rollback、防重复查询。
- [`tool_executor.py`](../apps/miroflow-agent/src/core/tool_executor.py) — 参数修正、重复调用检测、空结果回滚、工具结果后处理。
- [`settings.py`](../apps/miroflow-agent/src/config/settings.py) — Hydra 配置到 MCP 工具的映射。
- Hydra agent 配置位于 [`conf/agent/`](../apps/miroflow-agent/conf/agent/)，包含 `mirothinker_v1.0`、`mirothinker_v1.5_keep5_max{200,400}`、`mirothinker_1.7_keep5_max{200,300}`、`multi_agent`、`single_agent` 等；**当前常用基线**是 `mirothinker_v1.5_keep5_max200.yaml`（single-agent search + scrape + python）与 `mirothinker_1.7_keep5_max200.yaml`。
- [`search_and_scrape_webpage.py`](../libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/search_and_scrape_webpage.py) — 搜索、重试、URL 过滤。
- [`jina_scrape_llm_summary.py`](../libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/jina_scrape_llm_summary.py) — 抓取后抽取、Jina + Python fallback。
- [`common_benchmark.py`](../apps/miroflow-agent/benchmarks/common_benchmark.py) — 可复用的任务批量执行与日志框架。

#### B. 数据契约层（共享层，四域共享）

- [`contracts.py`](../apps/miroflow-agent/src/data_agents/contracts.py) — 四域共享 Pydantic 模型、`QualityStatus` 等 Literal 类型。
- [`evidence.py`](../apps/miroflow-agent/src/data_agents/evidence.py) — 统一 `evidence` 结构构造与校验。
- [`normalization.py`](../apps/miroflow-agent/src/data_agents/normalization.py) — 实体名、日期、字段归一化工具。
- [`linking.py`](../apps/miroflow-agent/src/data_agents/linking.py) — 跨域关联（normalize + evidence 驱动）。
- [`publish.py`](../apps/miroflow-agent/src/data_agents/publish.py) — 发布层通用 helper（发布层 = §6.1 第 4 层）。
- [`runtime.py`](../apps/miroflow-agent/src/data_agents/runtime.py) — 运行时 context、run_id 生成、worker 调度。
- [`canonical/`](../apps/miroflow-agent/src/data_agents/canonical/) — 规范化主 schema 层（§6.1 第 3 层）：`common.py`、`company.py`、`paper.py`、`professor.py`、`relations.py`、`source.py`。
- [`taxonomy/`](../apps/miroflow-agent/src/data_agents/taxonomy/) — 学科分层 + 种子（`domain_tier.py`、`seed_data.py`）。
- [`quality/`](../apps/miroflow-agent/src/data_agents/quality/) — 阈值配置（`threshold_config.py`）。
- [`providers/`](../apps/miroflow-agent/src/data_agents/providers/) — LLM / 搜索 / 反查 provider（`anthropic`、`qwen`、`dashscope`、`mirothinker`、`web_search`）。
- [`storage/`](../apps/miroflow-agent/src/data_agents/storage/) — 持久化：`sqlite_store.py`（历史）、`milvus_store.py`、`milvus_collections.py`（collection 定义）、`postgres/{connection,seed_loader}.py`。
- [`service/retrieval.py`](../apps/miroflow-agent/src/data_agents/service/retrieval.py) — `RetrievalService` + `Evidence` dataclass；当前覆盖 professor / paper。
- [`service/search_service.py`](../apps/miroflow-agent/src/data_agents/service/search_service.py) — 结构化检索回退。

#### C. 四域与跨域质量门（domain-specific）

- 教授域质量门：[`professor/name_identity_gate.py`](../apps/miroflow-agent/src/data_agents/professor/name_identity_gate.py)（Round 7.17 canonical_name 双语身份门）、[`professor/paper_identity_gate.py`](../apps/miroflow-agent/src/data_agents/professor/paper_identity_gate.py)（Round 8c，professor_paper_link 置信门，CONFIDENCE_THRESHOLD=0.8）、[`professor/quality_gate.py`](../apps/miroflow-agent/src/data_agents/professor/quality_gate.py)（学科敏感质量门）、[`professor/identity_verifier.py`](../apps/miroflow-agent/src/data_agents/professor/identity_verifier.py)。
- 论文域门控：`paper/title_quality.py`、`paper/title_cleaner.py`、`paper/title_resolver.py`（见 V011 `paper_title_resolution_cache`）。
- 教授域采集主体：`professor/{discovery,roster,parser,profile,school_adapters,enrichment,paper_publication,vectorizer,pipeline_v3}.py`（25+ 模块）。
- 论文域采集主体：`paper/{homepage_http,homepage_ingest,chunker,openalex,orcid,crossref,semantic_scholar,full_text_fetcher,release,milvus_backfill}.py` 等（V011 RAG 表由 `run_homepage_paper_ingest.py` 写入）。
- 企业域：`company/{models,release,enrichment,import_xlsx,canonical_import,knowledge_backfill,exact_backfill}.py`。
- 专利域：`patent/{models,linkage,release,import_xlsx,exact_backfill}.py`。

#### D. Alembic 主迁移（Postgres schema）

位于 [`apps/miroflow-agent/alembic/versions/`](../apps/miroflow-agent/alembic/versions/)，按时间顺序：

- V001 — `init_source_layer`
- V002 — `init_company_domain`
- V003 — `init_professor_domain`
- V004 — `init_paper_patent_domain`
- V005a / V005b — `professor_paper_link` / `cross_domain_relations`
- V006 — `pipeline_issue`（管道验证台）
- V007 — `add_run_id_trace`（全局 run_id 追踪；Round 7.16 phase 1）
- V008 — `relax_paper_title_not_null`
- V009 — `add_canonical_name_zh`（双语身份字段；Round 7.17）
- V010 — `add_professor_profile_fields`
- V011 — `add_rag_tables`（`paper_full_text` / `paper_title_resolution_cache` / `professor_orcid`）

### 3.3 推荐实现方式

共享规范推荐的实现方向是：

- 以现有 MiroThinker runtime 为基础
- 为教授、企业、论文、专利分别补 domain-specific prompt / config / post-processing
- 用现有搜索、抓取、抽取、Python 工具完成大部分“采集 + 清洗”闭环
- 需要 domain-specific 硬规则时，再辅以离线脚本和结构化清洗模块

不推荐一开始就设计：

- 一套完全独立的调度器
- 一套和现有 `ToolManager` 平行的新工具注册系统
- 一套和现有 `benchmark` / `task log` 平行的新验证体系

### 3.4 当前工具能力映射

| 采集/清洗能力 | 当前优先复用实现 | 备注 |
| --- | --- | --- |
| Web Search | `search_and_scrape_webpage` / `tool-google-search` / `tool-sogou-search` / `providers/web_search.py`（Serper） | Web Search 是辅助能力，不是主骨架 |
| 网页抓取 | `search_and_scrape_webpage` / `jina_scrape_llm_summary` / `paper/homepage_http.py` | 支持网页抓取与信息抽取 |
| PDF/长文抽取 | `jina_scrape_llm_summary` / `paper/full_text_fetcher.py` / `paper/cv_pdf.py` | 适合论文、专利、报告类页面 |
| 结构化清洗/标准化 | `tool-python` + 离线脚本 + `data_agents/normalization.py` | 用于实体标准化、去重辅助、字段解析 |
| 任务执行 | `pipeline.py` + `Orchestrator` | 适合 task-style 采集 Agent |
| 评估与日志 | `common_benchmark.py` + `TaskLog` | 可复用到验证与补采环节 |
| 向量检索 | `service/retrieval.py`（`RetrievalService` + 并发多域 ANN）+ `storage/milvus_collections.py` + `professor/vectorizer.py` + `paper/milvus_backfill.py` | 目前覆盖 professor / paper，company / patent 规划中 |
| Rerank | `providers/` 下 reranker client（M0.1，chat.py 通过 `_get_reranker_client` 使用） | Qwen3-Reranker-8B 本地部署 |
| 跨域关联 | `data_agents/linking.py` + `canonical/relations.py` + V005a/V005b 关系表 | 必须基于 normalization + 公开证据 |
| 主 schema 承载 | `canonical/{common,company,paper,professor,relations,source}.py` + V003/V004 Postgres schema | §6.1 第 3 层 |

---

## 四、共享逻辑契约

### 4.1 统一 ID 规则

各数据域必须提供稳定 ID，建议采用以下前缀：

- `PROF-*`
- `COMP-*`
- `PAPER-*`
- `PAT-*`

ID 规则要求：

- 同一对象跨更新周期尽量稳定
- 不依赖用户可见名称直接裸拼
- 可由各域内部规则生成，但需保证域内唯一

### 4.2 最小对外对象契约

每个数据域都必须向线上服务层暴露至少以下字段：

| 字段 | 说明 |
| --- | --- |
| `id` | 稳定主键 |
| `object_type` | `professor` / `company` / `paper` / `patent` |
| `display_name` | 主展示字段，教授/企业通常对应 `name`，论文/专利通常对应 `title` |
| `core_facts` | 供服务层和回答层消费的核心事实字段 |
| `summary_fields` | 用户向摘要字段集合 |
| `evidence` | 来源证据数组，结构见 4.5 节 |
| `last_updated` | 最近更新时间 |
| `run_id` | **必填**，对应 `pipeline_run.run_id`（Round 7.16 phase 1 起）；V007 迁移建立该列，legacy 行以 `legacy_backfill` 占位值填充。所有 writer 必须在 phase 2 writer wiring 完成后显式传递真实 run_id（进度见 [plans/2026-04-18-008](./plans/2026-04-18-008-pipeline-run-id-trace.md)）。 |
| `quality_status` | 4 个 canonical 值：`ready` / `needs_review` / `low_confidence` / `needs_enrichment`（对齐 `data_agents/contracts.py:9` 与 [quality-status-compatibility](./quality-status-compatibility.md)） |

### 4.2.1 摘要字段命名标准

各域的摘要字段必须使用以下统一名称（详见 [术语表](./index.md#摘要字段)）：

| 字段 | 适用域 | 用途 |
| --- | --- | --- |
| `profile_summary` | 教授、企业 | 画像摘要，200-300 字中文 |
| `evaluation_summary` | 教授、企业 | 事实性评价摘要，100-150 字 |
| `technology_route_summary` | 企业 | 技术路线摘要 |
| `summary_zh` | 论文 | 四段式结构化中文摘要（what / why / how / result） |
| `summary_text` | 论文、专利 | embedding 用完整摘要文本 |

论文域的 `summary_text` 由 `summary_zh` 四段拼接而成，不是独立生成的第二份摘要。

### 4.3 各域最低字段要求

#### 企业

最低对外字段必须包含：

- `id`
- `name`
- `normalized_name`
- `industry`
- `profile_summary`
- `evaluation_summary`
- `technology_route_summary`（**当前实现为规则拼接**：`company/enrichment.py` 基于 `business` / `description` / `website` 等字段合成；LLM 增强版本见 [plans/2026-04-17-005](./plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md) §9.2，未交付）
- `key_personnel`
- `last_updated`
- `run_id`
- `evidence`

#### 教授

最低对外字段必须包含：

- `id`
- `name`
- `canonical_name_zh` / `canonical_name_en`（V009 / Round 7.17 起必填；必须通过 `professor/name_identity_gate.py` LLM 核验才能赋值 `canonical_name_en`）
- `institution`
- `department`
- `title`
- `research_directions`
- `profile_summary`
- `evaluation_summary`
- `company_roles`
- `last_updated`
- `run_id`
- `evidence`

**可选学术指标**（PRD §模块一 R2 要求，代码中 `professor/models.py` + `publish_helpers.py` 已有字段，但**服务层暴露未统一**——admin API / chat profile / Milvus schema 尚未全部带出，现状见 [docs/index.md](./index.md) 教授行缺口列）：

- `h_index`（总 h-index；可选）
- `citation_count`（总引用数；可选）
- `paper_count`（论文总数；可选）

教授的代表论文不再作为 professor 对象上的原始字段发布。
如需展示代表论文，必须通过 `verified professor_paper_link` 关联到 canonical `paper` 对象后再派生（verified 的判定见 §5.2 `paper_identity_gate`）。

#### 论文

最低对外字段必须包含：

- `id`
- `title`
- `authors`
- `professor_ids`
- `year`
- `venue`
- `summary_zh`
- `summary_text`
- `keywords`
- `last_updated`
- `run_id`
- `evidence`

可选扩展字段（V011 起可用，RAG 支持）：`full_text_url`、`full_text_storage_ref`（对应 `paper_full_text` 表）；`title_resolution_cache_key`（对应 `paper_title_resolution_cache`）。

#### 专利

最低对外字段必须包含：

- `id`
- `title`
- `applicants`
- `inventors`
- `patent_type`
- `filing_date`
- `publication_date`
- `summary_text`
- `company_ids`
- `professor_ids`
- `last_updated`
- `run_id`
- `evidence`

### 4.4 统一 filter 语义

服务层看到的 filter 语义必须统一，即使各域底层列名不同。

最低统一 filter 包括：

| filter | 语义 |
| --- | --- |
| `institution` | 高校或科研机构 |
| `department` | 院系/部门 |
| `title` | 教授职称 |
| `industry` | 企业行业 |
| `year_range` | 论文/专利相关年份范围 |
| `patent_type` | 发明/实用新型/外观设计等 |
| `company_name` | 企业标准化名称查询 |
| `person_name` | 关键人物/发明人/作者姓名查询 |
| `education_filter` | 教育背景相关结构化筛选 |
| `research_direction` | 教授研究方向或论文技术方向 |

### 4.5 统一 `evidence` 字段

各域必须使用统一的 `evidence` 字段（不再使用 `sources`），支持来源可追溯。

每条对象的 `evidence` 为以下结构的数组：

```json
[
  {
    "source_type": "official_site | xlsx_import | public_web | academic_platform | manual_review",
    "source_url": "https://example.com/page",
    "source_file": "qimingpian_export_202603.xlsx",
    "fetched_at": "2026-03-15T10:30:00Z",
    "snippet": "可选证据片段",
    "confidence": 0.95
  }
]
```

字段说明：

- `source_type`：必填，枚举值
- `source_url` 或 `source_file`：至少有一个
- `fetched_at`：必填，ISO 8601 时间
- `snippet`：可选，支撑关键事实的原文片段
- `confidence`：可选，0-1 浮点数

### 4.6 服务层查询接口契约

共享规范不强制 SQL 风格接口，而是定义逻辑接口语义。**当前实现**（`apps/miroflow-agent/src/data_agents/service/retrieval.py`）：

```python
class RetrievalService:
    def retrieve(
        self,
        query: str,
        *,
        domains: tuple[str, ...],      # 目前 _VALID_DOMAINS = {"professor", "paper"}
        filters: dict | None = None,
        candidate_limit: int = 30,     # ANN 候选数
        final_top_k: int = 10,         # rerank 后返回数
    ) -> list[Evidence]:
        ...
```

实际召回链路：query embedding → 并发多域 ANN 召回（Milvus）→ filter → reranker（Qwen3-Reranker-8B）→ top_k。`mode` 字段已内化——检索路径默认走"向量召回 + rerank 融合"的 hybrid 范式，不再以参数暴露。

**仍属契约层的逻辑接口语义**（未来扩展目标，非当前代码直接签名）：

```python
# 单对象获取（当前由各域 admin API 如 /api/professor/<id> 承担）
get_object(domain, object_id) -> dict

# 跨域关系查询（当前由 canonical/relations 表 + ad-hoc SQL 承担）
get_related_objects(
    source_domain, source_id,
    target_domain, relation_type,
    limit=20,
) -> list[dict]
```

是否内部用 SQL、adapter、domain API、还是多段检索，由各域实现自行决定。逻辑模式仍保留 `exact` / `semantic` / `hybrid` 三种语义分类，以便未来规范化扩展。

**域覆盖扩展**：company / patent 接入 `retrieve` 的计划见 [plans/2026-04-20-003](./plans/2026-04-20-003-agentic-rag-execution-plan.md) M3 与 [plans/2026-04-17-005](./plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md)。在接入前，这两域的语义检索走 `service/search_service.py` 的结构化回退。

---

## 五、各域强制规则

### 5.1 企业域

企业域共享强制规则：

- 主骨架数据以 `企名片导出 xlsx` 为准
- 自写爬虫为主，Web Search 为辅助
- 标准化公司名称是主去重锚点
- `credit_code` 为可选补充字段，不是主去重锚点，也不是 Phase 契约必填
- 必须预生成：
  - `profile_summary`
  - `evaluation_summary`
  - `technology_route_summary`
- `key_personnel` 必须是可检索结构化字段，而不是仅展示字段

### 5.2 教授域

教授域共享强制规则：

- 覆盖目标是深圳高校教授
- 主来源必须是深圳各高校官网、教师目录、教师主页
- Scholar、个人主页、实验室主页、Web Search 是辅助补充和验证源
- 教授-企业关联不得再把 `企名片 API` 作为默认关联方式
- `company_roles` 应主要来自企业库匹配与公开证据

**强制质量门控（Round 7.17 / Round 8c 起）**：

- `canonical_name_zh` ↔ `canonical_name_en` 必须通过 `professor/name_identity_gate.py` LLM 核验（confidence ≥ 0.8）后才能共存；未通过者 `canonical_name_en` 必须置 NULL。详见 [plans/2026-04-18-007](./plans/2026-04-18-007-name-identity-gate.md)。
- `professor_paper_link` 必须通过 `professor/paper_identity_gate.py` 核验（默认 `CONFIDENCE_THRESHOLD = 0.8`）才能标记为 `verified`；未通过者置为 `link_status = candidate` 并记录 `topic_consistency_score` / `institution_consistency_score`，低置信项入 `pipeline_issue` 表。
- 教授发布前必须过 `professor/quality_gate.py` 的学科敏感质量门（STEM / HSS 阈值不同，详见 `quality/threshold_config.py`）。

### 5.3 论文域

论文域共享强制规则：

- 周期性论文采集必须从深圳教授 roster 出发
- 论文库不是开放式全文献抓取器
- 每篇论文在归属置信度足够时必须建立 `professor_ids`
- 论文既是独立检索对象，也是教授画像更新信号
- 论文信号必须参与教授：
  - `research_directions`
  - `profile_summary`
  - 近期研究重点判断
- 任意显式论文标题查询可由线上服务走实时外部 fallback，不要求离线论文库全覆盖全球论文

**多源策略（Round M2 / Paper Multi-Source）**：

- 主页权威论文优先（M2.1 `paper/homepage_http.py` 抽取 + M2.2 `title_resolver.py` 消歧）；兜底走 OpenAlex / Crossref / Semantic Scholar / ORCID / arXiv。
- 全文抓取通过 `paper/full_text_fetcher.py` 触发并缓存到 V011 `paper_full_text` 表。
- 标题归一化结果走 V011 `paper_title_resolution_cache`，避免重复 LLM 调用。
- 多源优先级 Phase A 已落地；Phase B（证据权重与权威源切换）排队中，见 [plans/2026-04-08-001](./plans/2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md) 与 [plans/2026-04-22-001](./plans/2026-04-22-001-m3-retrieval-service-paper-first.md)。

### 5.4 专利域

专利域共享强制规则：

- 主骨架数据以平台导出 `xlsx` 为准
- 第一阶段默认全量导入导出数据
- 查询时再做筛选，不在入库前过窄裁剪
- 必须生成用户可读的解释性摘要字段
- 必须支持 company / professor 关联字段

---

## 六、物理存储与向量化建议

### 6.1 物理 schema 原则

允许各域独立设计物理 schema，但必须按**四层**组织：

1. **原始层（Raw）**
   - 保存导入行、原网页、原 PDF、原始响应
   - 各域独立 schema（如 `company_raw`、`professor_source_page` 等）
2. **标准化层（Normalized）**
   - 保存清洗后的事实字段、关系字段、域内去重结果
   - 仍可各域独立 schema；`data_agents/normalization.py` 提供共享工具
3. **规范化主 schema 层（Canonical）** — V003–V011 新增，**对外契约的实际承载层**
   - 实现在 `apps/miroflow-agent/src/data_agents/canonical/`：`common.py`、`company.py`、`paper.py`、`professor.py`、`relations.py`、`source.py`
   - Postgres 表通过 alembic V003 / V004 / V005a / V005b / V006 / V007 / V009 / V010 / V011 建立
   - 该层输出结构即 §4.2 最小对外对象契约（含 `run_id` / `canonical_name_zh` / `quality_status` / `evidence` 等）
4. **发布层（Published / Serving）**
   - 面向线上服务暴露稳定对外契约字段（SQL view / Milvus collection / 发布快照）
   - 包括 `professor_profiles`、`paper_chunks` 等 Milvus collection 以及各域 admin API 的 DTO

共享规范真正关心的是**第 3 层 canonical 主 schema** 和**第 4 层发布层**。第 1-2 层允许各域自由演进，只要最终在第 3 层汇合到契约字段。

### 6.2 向量化对象建议

推荐的主向量对象如下：

| 数据域 | 主向量文本 | 当前 collection | 状态 |
| --- | --- | --- | --- |
| 教授 | `profile_summary` | `professor_profiles` | ✅ 已建并回填 |
| 企业 | `profile_summary` | （规划中） | 🚧 M3 目标 |
| 论文 | `summary_text` / chunk 分片 | `paper_chunks` | ✅ 已建；`run_milvus_backfill.py` 写入；支持 `chunk_type`（abstract / intro / conclusion 等）、`segment_index` 维度 |
| 专利 | `summary_text` | （规划中） | 🚧 未启动 |

论文 chunk 分片由 `paper/chunker.py` 产生；retrieval 时以 query embedding + `paper_chunks` 多 chunk_type ANN → rerank 为主路径。

如果某域需要多 collection，可按以下逻辑拆分：

- 主画像 collection
- 技术路线 / 研究方向 collection
- 长文摘要 collection

共享规范不强制 collection 名称，但要求服务层能明确知道每个 collection 的语义，并在 `storage/milvus_collections.py` 中集中定义常量与 schema。

---

## 七、数据质量与验证

### 7.1 质量维度

共享质量维度统一为：

| 维度 | 含义 |
| --- | --- |
| 完整度 | 契约必填字段是否齐全 |
| 准确度 | 事实是否与可信来源一致 |
| 新鲜度 | 是否能反映最近更新状态 |
| 唯一性 | 是否存在重复对象或错误合并 |
| 可追溯性 | 是否能追到来源和证据 |

### 7.2 最小自动化校验

**共享契约级校验（所有域）**：

- `run_id` 必须非空（Round 7.16 phase 1 起；legacy 行允许 `legacy_backfill` 占位）
- `quality_status` 必须为 4 个 canonical 值之一：`ready` / `needs_review` / `low_confidence` / `needs_enrichment`
- 不满足 `ready` 的对象不得进入默认检索池；`needs_enrichment` 与 `low_confidence` 的失败原因必须写入 `pipeline_issue` 表（V006 起）供管道验证台回看

#### 企业

- `name` 不能为空
- `normalized_name` 必须可生成
- `profile_summary` / `evaluation_summary` / `technology_route_summary` 不得缺失
- `credit_code` 若存在则做格式校验

#### 教授

- `institution` 必须在深圳高校名单内
- 必须至少有一个官方来源
- `profile_summary` 不得缺失
- 论文反哺后的 `research_directions` 应与近年论文主题一致（由 `topic_consistency_score` 量化）
- **Round 7.17 身份门**：`canonical_name_zh` 必填；`canonical_name_en` 仅在通过 `name_identity_gate` 核验时赋值，否则 NULL
- **Round 8c paper 身份门**：`professor_paper_link` 进入 verified 状态必须 `confidence ≥ 0.8`（`paper_identity_gate`）；未通过项标 candidate 并入 `pipeline_issue`
- **学科敏感质量门**：通过 `professor/quality_gate.py` + `quality/threshold_config.py` 的 STEM / HSS 差异阈值

#### 论文

- `title`、`authors`、`year` 不能为空
- `summary_zh` 与 `summary_text` 不得缺失
- 若论文来自教授 roster 采集，应尽量有 `professor_ids`
- **Round 7.x 质量门**：`title_quality` / `topic_quality` 子校验不得失败；低分入 `pipeline_issue`

#### 专利

- `title`、`patent_type`、`filing_date` 或 `publication_date` 至少有一项可用
- `summary_text` 不得缺失
- 若能归属公司或教授，应写入关联字段

### 7.3 MiroThinker 验证与补采

共享验证流程建议如下：

1. 抽样或定向挑选低置信对象（候选池来自 `pipeline_issue` 表 + `quality_status != ready` 行）
2. 让 MiroThinker 基于现有搜索/抓取/抽取工具复核关键事实
3. 对冲突事实做人工或规则复判（管道验证台 `/browse` 三 tab：provenance / coverage / review，见 [plans/2026-04-18-006](./plans/2026-04-18-006-pipeline-verification-console.md)）
4. 回写修正结果并记录验证报告；复判结果必须带 `run_id` 写回 canonical 层

重点验证对象包括：

- 新增或大幅更新对象
- 低质量对象（`quality_status in {needs_review, low_confidence, needs_enrichment}`）
- 重名、高歧义对象（`name_identity_gate` 未通过项）
- 低置信关联（`professor_paper_link.link_status = candidate`）
- 关键关联对象
  - 教授-企业
  - 教授-论文
  - 企业-专利
  - 教授-专利

### 7.4 验收标准规范

各域的验收标准必须满足以下模板要求（详见 [术语表](./index.md#验收标准模板)）：

- **测试集来源**：明确指向哪组测试数据或标注集
- **样本量**：抽样检验需注明最小样本量（建议 ≥ 50）
- **评判标准**："准确"的具体定义
- **评审方式**：自动化 / 人工抽检 / 混合

不满足上述要求的验收指标视为草稿，不作为正式交付标准。

---

## 八、更新与发布

### 8.1 更新节奏

共享规范只约束“可独立更新”，不强制所有域用一个统一周期。

允许：

- 企业域独立更新
- 教授域独立更新
- 论文域依赖最新教授 roster 更新
- 专利域独立更新

如果某域本轮未更新，不应阻塞其他域发布。

### 8.2 对外发布要求

每个域发布时至少输出：

- 最新发布快照或发布层表/视图
- 向量索引同步结果
- 数据质量报告
- 更新范围说明
- 错误与异常记录

### 8.3 契约变更要求

任何会影响服务层的变更，都必须同步更新：

- 本共享规范
- 对应域 PRD
- 若影响用户查询行为，还需同步更新 [Agentic-RAG-PRD.md](./Agentic-RAG-PRD.md)

**同步时限**：alembic migration（V00x）合入主干后，本 Spec 相关章节必须在 **1 周内**完成同步（涉及 §4 契约字段、§5 强制规则、§6.1 物理层、§7.2 校验的任何变更）。未及时同步的迁移视为文档漂移，应被 code review 拦截。

---

## 九、与下游系统的关系

本数据采集智能体群为以下下游能力提供数据：

| 下游能力 | 消费方式 |
| --- | --- |
| 查教授 | 消费教授域发布层 + 论文关联信号 |
| 查企业 | 消费企业域发布层 + 专利关联信号 |
| 查论文 | 消费论文域发布层 + 教授关联 |
| 查专利 | 消费专利域发布层 + 公司/教授关联 |
| 跨域聚合问答 | 由线上服务层跨域编排、融合、rerank |

共享规范要求的是：

- 数据域可独立演进
- 服务层可稳定消费
- 最终问答效果能对齐总 PRD 与测试集目标

而不是：

- 所有域在一个 PostgreSQL 里共享一套表
- 所有域必须通过同一条 SQL 被访问
