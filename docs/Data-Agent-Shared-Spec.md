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

### 2.1 长期架构

长期架构统一为：

- `PostgreSQL + Milvus`

设计目标是：

- 教授、企业、论文、专利可各自独立维护 PostgreSQL 库
- 每个数据域可各自维护一组 Milvus collection
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
   - 发布到对外契约层，做抽样验证、定向补采、生成报告

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

当前与数据采集 Agent 最相关的实现基线包括：

- [`pipeline.py`](../apps/miroflow-agent/src/core/pipeline.py)
  - 统一任务入口，负责拼装 `ToolManager`、`Orchestrator`、`OutputFormatter`
- [`orchestrator.py`](../apps/miroflow-agent/src/core/orchestrator.py)
  - 多轮 agent loop、上下文压缩、rollback、防重复查询
- [`tool_executor.py`](../apps/miroflow-agent/src/core/tool_executor.py)
  - 参数修正、重复调用检测、空结果回滚、工具结果后处理
- [`settings.py`](../apps/miroflow-agent/src/config/settings.py)
  - Hydra 配置到 MCP 工具的映射
- [`mirothinker_1.7_keep5_max200.yaml`](../apps/miroflow-agent/conf/agent/mirothinker_1.7_keep5_max200.yaml)
  - 当前单智能体 search + scrape/extract + python 的高信号配置范式
- [`search_and_scrape_webpage.py`](../libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/search_and_scrape_webpage.py)
  - 搜索、重试、URL 过滤
- [`jina_scrape_llm_summary.py`](../libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/jina_scrape_llm_summary.py)
  - 抓取后抽取、Jina + Python fallback
- [`common_benchmark.py`](../apps/miroflow-agent/benchmarks/common_benchmark.py)
  - 可复用的任务批量执行与日志框架

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
| Web Search | `search_and_scrape_webpage` / `tool-google-search` / `tool-sogou-search` | Web Search 是辅助能力，不是主骨架 |
| 网页抓取 | `search_and_scrape_webpage` / `jina_scrape_llm_summary` | 支持网页抓取与信息抽取 |
| PDF/长文抽取 | `jina_scrape_llm_summary` | 适合论文、专利、报告类页面 |
| 结构化清洗/标准化 | `tool-python` + 离线脚本 | 用于实体标准化、去重辅助、字段解析 |
| 任务执行 | `pipeline.py` + `Orchestrator` | 适合 task-style 采集 Agent |
| 评估与日志 | `common_benchmark.py` + `TaskLog` | 可复用到验证与补采环节 |

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
| `quality_status` | 可选，表示 `ready` / `needs_review` / `low_confidence` 等状态 |

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
- `technology_route_summary`
- `key_personnel`
- `last_updated`
- `evidence`

#### 教授

最低对外字段必须包含：

- `id`
- `name`
- `institution`
- `department`
- `title`
- `research_directions`
- `profile_summary`
- `evaluation_summary`
- `company_roles`
- `last_updated`
- `evidence`

教授的代表论文不再作为 professor 对象上的原始字段发布。
如需展示代表论文，必须通过 `verified professor_paper_link` 关联到 canonical `paper` 对象后再派生。

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
- `evidence`

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

共享规范不再强制 SQL 风格接口，而是定义逻辑接口语义：

```python
search_domain(
    domain: str,
    query: str,
    filters: dict | None = None,
    mode: str = "hybrid",
    limit: int = 10,
) -> list[dict]

get_object(
    domain: str,
    object_id: str,
) -> dict

get_related_objects(
    source_domain: str,
    source_id: str,
    target_domain: str,
    relation_type: str,
    limit: int = 20,
) -> list[dict]
```

逻辑模式统一为：

- `exact`
- `semantic`
- `hybrid`

是否内部用 SQL、adapter、domain API、还是多段检索，由各域实现自行决定。

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

允许各域独立设计物理 schema，但建议按三层组织：

- 原始层
  - 保存导入行、原网页、原 PDF、原始响应
- 标准化层
  - 保存清洗后的事实字段、关系字段、去重结果
- 发布层
  - 面向线上服务暴露稳定对外契约字段

发布层是共享规范真正关心的部分。

### 6.2 向量化对象建议

推荐的主向量对象如下：

| 数据域 | 主向量文本 |
| --- | --- |
| 教授 | `profile_summary` |
| 企业 | `profile_summary` |
| 论文 | `summary_text` |
| 专利 | `summary_text` |

如果某域需要多 collection，可按以下逻辑拆分：

- 主画像 collection
- 技术路线 / 研究方向 collection
- 长文摘要 collection

共享规范不强制 collection 名称，但要求服务层能明确知道每个 collection 的语义。

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

#### 企业

- `name` 不能为空
- `normalized_name` 必须可生成
- `profile_summary` / `evaluation_summary` / `technology_route_summary` 不得缺失
- `credit_code` 若存在则做格式校验

#### 教授

- `institution` 必须在深圳高校名单内
- 必须至少有一个官方来源
- `profile_summary` 不得缺失
- 论文反哺后的 `research_directions` 应与近年论文主题一致

#### 论文

- `title`、`authors`、`year` 不能为空
- `summary_zh` 与 `summary_text` 不得缺失
- 若论文来自教授 roster 采集，应尽量有 `professor_ids`

#### 专利

- `title`、`patent_type`、`filing_date` 或 `publication_date` 至少有一项可用
- `summary_text` 不得缺失
- 若能归属公司或教授，应写入关联字段

### 7.3 MiroThinker 验证与补采

共享验证流程建议如下：

1. 抽样或定向挑选低置信对象
2. 让 MiroThinker 基于现有搜索/抓取/抽取工具复核关键事实
3. 对冲突事实做人工或规则复判
4. 回写修正结果并记录验证报告

重点验证对象包括：

- 新增或大幅更新对象
- 低质量对象
- 重名、高歧义对象
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
