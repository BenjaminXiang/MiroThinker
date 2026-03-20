# 导师信息抓取清洗智能体 — 产品需求文档

## 一、为什么需要一个"智能体"而不是一个"爬虫"

在正式展开需求之前，有必要先说清楚一个根本性的问题：为什么一个传统爬虫无法完成这项工作，以至于我们需要构建一个 LLM 驱动的智能体。

传统爬虫的工作模式是"给定 URL → 抓取页面 → 按预定义规则解析字段 → 入库"。这个模式在面对大学导师信息采集时，至少在三个地方彻底失效：

**第一，信息源的不可预知性。** 爬虫能抓取的是校内教师主页，但校内主页往往只是冰山一角。真正有价值的信息——最新的研究方向、近期论文、项目经历——往往在教师自己维护的个人网站、Google Scholar 主页、实验室主页上。这些外部链接有的出现在校内主页里，有的根本没有。爬虫无法"判断"应该去哪里找更多信息，但 LLM 可以——它能从校内主页的文本中识别出外部链接，甚至在没有链接的情况下决定通过 Web Search 去寻找。

**第二，信息结构的不可预知性。** 不同大学、不同院系的教师主页模板千差万别。有的用表格展示基本信息，有的用自由文本，有的是纯英文，有的中英混杂。为每所大学编写定制化的解析规则成本极高且维护困难。LLM 天然具备从非结构化文本中提取结构化信息的能力，无需为每个模板编写规则。

**第三，信息的歧义性。** "张伟"这个名字在深圳的高校里可能出现不止一次。当我们通过 Web Search 或 Google Scholar 搜索一位教师时，返回的结果中可能混杂着同名不同人的信息。爬虫无法处理这种歧义，但 LLM 可以通过交叉验证（机构、研究方向、合作者等多信号比对）来判断哪些信息属于同一个人。

因此，这个系统的本质是：**爬虫负责"手"（抓取网页），LLM 负责"脑"（判断抓什么、怎么理解、如何消歧、生成什么摘要）。** 两者协作，才能从散乱的互联网信息中构建出一个高质量的导师信息库。

---

## 二、核心目标

**一句话目标：** 给定一批大学教师列表页 URL，自动产出结构化的导师信息并入库，为下游 RAG 检索提供数据基础。

这里有两个关键约束需要始终牢记：

**约束一：数据是给 RAG 用的，不是直接给人看的。** 这意味着数据模型的设计要围绕"如何让向量检索更准确"来优化，而不是围绕"如何让人类阅读更舒适"。具体来说，每位导师需要一段语义丰富的自然语言画像摘要（用于 Embedding 和语义检索），而不仅仅是一堆结构化字段。结构化字段用于精确筛选（如按学校、职称过滤），画像摘要用于语义匹配（如用户问"深圳有谁在做具身智能"时，能通过语义相似度召回相关教师）。

**约束二：不过度设计，只做 P0 和 P1。** 这个智能体的价值在于快速跑通"URL → 结构化数据 → RAG 可用"的链路，而不是构建一个完美的数据治理平台。能用就上，后续迭代。

---

## 三、目标高校与教授范围

### 3.1 高校范围

核心 8-10 所深圳本地及在深有实体研究机构的高校，包括但不限于：

| 类别 | 高校 |
| --- | --- |
| 深圳本地 | 南方科技大学、深圳大学、香港中文大学(深圳)、哈尔滨工业大学(深圳) |
| 在深研究机构 | 清华大学深圳国际研究生院、北京大学深圳研究生院、中国科学院深圳先进技术研究院 |
| 其他 | 深圳技术大学、深圳北理莫斯科大学等（视实际情况调整） |

### 3.2 教授范围

- **全量教师采集**，不限院系，预计 5000+ 人
- 包含所有在编教师（教授、副教授、助理教授、讲师、研究员等）
- 教师列表来源：各高校官网教师目录页

### 3.3 本期不做

| 不做的事 | 理由 |
| --- | --- |
| 合作网络图谱 | 有价值但不是一期核心，可从论文数据中后续推导 |
| 非深圳高校教授 | 聚焦深圳，外地教授不在采集范围 |

---

## 四、教授数据模型

### 4.1 字段定义

字段来源不做预设绑定——Agent 在迭代采集过程中从官网、个人主页、Google Scholar、Web Search 等任何可用数据源动态发现并填充字段。`sources` 字段记录每条数据实际来自哪些源，确保可溯源。

| 字段 | 类型 | 必填 | 采集策略 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | TEXT | 是 | 系统生成 | 唯一标识，格式 `PROF-{hash}`。优先使用 ORCID，无则用姓名+机构哈希 |
| `name` | TEXT | 是 | Agent 首轮从列表页/官网主页提取 | 中文姓名 |
| `name_en` | TEXT | 否 | Agent 从官网/Scholar/个人主页任一源提取 | 英文姓名 |
| `institution` | TEXT | 是 | 从列表页 URL 对应的高校确定 | 所属高校全称 |
| `department` | TEXT | 否 | Agent 从官网主页或院系页面提取 | 所属院系 |
| `title` | TEXT | 否 | Agent 从官网/个人主页提取 | 职称（教授/副教授/助理教授/讲师/研究员等） |
| `email` | TEXT | 否 | Agent 从官网/个人主页提取 | 邮箱 |
| `homepage` | TEXT | 否 | Agent 从官网提取或 Web Search 发现 | 个人主页链接 |
| `scholar_id` | TEXT | 否 | Agent 访问 Google Scholar 时获取 | Google Scholar author ID，用于消歧锚点和 Phase 2 论文精确采集入口 |
| `semantic_scholar_id` | TEXT | 否 | Agent 访问 Semantic Scholar 时获取 | Semantic Scholar author ID，同上 |
| `research_directions` | TEXT[] | 否 | Phase 3 论文反哺：从论文关键词聚类生成 | 精细化研究方向标签（非官网笼统描述） |
| `education` | TEXT | 否 | Agent 从官网/个人主页提取 | 教育背景（原文） |
| `education_structured` | JSONB | 否 | Agent 从官网/个人主页提取 | 结构化教育经历，格式 `[{institution, degree, year, field}]`，支持按学校/学位精确筛选 |
| `h_index` | INTEGER | 否 | Agent 从 Scholar/Semantic Scholar 获取 | H-index |
| `citation_count` | INTEGER | 否 | Agent 从 Scholar/Semantic Scholar 获取 | 总引用数 |
| `top_papers` | JSONB | 否 | Phase 3 从论文库筛选 | 代表论文 Top-10，格式 `[{title, year, citations, doi}]` |
| `company_roles` | JSONB | 否 | Agent 从企名片 API 或企业库反向匹配获取 | 关联企业及角色，格式 `[{company_id, role, source_url}]` |
| `patent_ids` | TEXT[] | 否 | Agent 从专利库反向匹配获取 | 关联专利 ID 列表 |
| `awards` | JSONB | 否 | Agent 从官网/个人主页/学术平台提取 | 奖励荣誉，格式 `[{title, year, issuer, source_url}]` |
| `academic_positions` | TEXT[] | 否 | Agent 从官网/个人主页提取 | 学术兼职与社会职务 |
| `projects` | JSONB | 否 | Agent 从官网/个人主页/Web Search 提取 | 主持/参与项目，格式 `[{name, role, source, source_url}]` |
| `work_experience` | JSONB | 否 | Agent 从官网/个人主页提取 | 工作经历，格式 `[{organization, role, start_year, end_year, description}]` |
| `evaluation_summary` | TEXT | 否 | Phase 3 由 LLM 综合事实维度生成 | 100-150 字事实性评价摘要，支撑"大牛"等评价性查询 |
| `profile_summary` | TEXT | **是** | Phase 3 由 LLM 综合所有数据源生成 | 200-300 字画像摘要，语义检索用 |
| `profile_embedding` | VECTOR | **是** | Phase 3 由 Embedding 模型（见 [共享技术规范](./Data-Agent-Shared-Spec.md) 可配置组件）计算 | 画像摘要的向量表示 |
| `sources` | TEXT[] | 是 | 系统自动记录 Agent 实际访问的数据源 | 数据来源列表（官网/Scholar/企名片等） |
| `completeness_score` | INTEGER | 是 | DataCleaner 阶段程序化计算 | 数据完整度评分 0-100 |
| `last_updated` | TIMESTAMP | 是 | 系统记录 | 最后更新时间 |
| `raw_data_path` | TEXT | 是 | 系统记录 | 原始数据存储路径 |

### 4.2 画像摘要规范

`profile_summary` 是教授记录中最重要的字段——它直接决定了向量检索的质量。

**生成时机**：在论文数据采集完成后（Phase 3），综合所有数据源生成。

**生成输入**：
- 官网基础信息（姓名、职称、院系）
- 结构化教育经历（`education_structured`，如有）
- 工作经历（`work_experience`，如有）
- 论文推断的精细研究方向（从近 5 年论文关键词聚类）
- 代表论文 Top-10（标题 + 摘要）
- 学术指标（H-index、引用数）
- 奖励荣誉（如有）
- 学术兼职（如有）
- 主持/参与项目（如有）
- 关联企业及角色/专利（如有）

**输出要求**：200-300 字中文自然语言段落，包含足够的语义信号以支持多样化的检索查询。禁止使用"等""相关"等模糊表述，用具体技术词汇替代。

### 4.3 跨教授评价能力

下游 RAG 智能体可能遇到"大牛""比较厉害""谁更资深"等评价性查询。这类查询不能靠排名或主观评分回答，而应基于事实由 LLM 综合判断。

**数据支撑**：

| 事实维度 | 源字段 | 说明 |
| --- | --- | --- |
| 学术指标 | `h_index`, `citation_count` | 提供领域内相对水平参考（如有对比数据） |
| 奖项级别 | `awards` | 按国家级/省部级/学会级分类呈现 |
| 学术头衔 | `academic_positions` | 如 IEEE Fellow、长江学者等 |
| 项目级别 | `projects` | 主持国家级重大/重点项目的数量和级别 |

**实现机制**：

- 在 Phase 3 入库阶段，综合上述事实维度由 LLM 生成一段客观的事实性评价描述（100-150 字），写入教授记录的 `evaluation_summary` 字段（可选 TEXT）
- `evaluation_summary` 仅呈现事实（如"主持国家自然科学基金重点项目 2 项，获 IEEE Fellow 称号"），不做主观排名
- 下游 RAG 智能体在回答评价性查询时，检索多位候选教授的 `evaluation_summary`，由 LLM 基于事实综合判断并给出回答
- 设计要点：不存储排名分数，不预设权重，避免引入偏见

---

## 五、采集管道设计

### 5.1 整体流程

采集分为五个阶段。**Phase 0 必须先于 Phase 1 完成**：教授 Agent 采集时需通过企名片 API 关联企业信息（写入 `company_roles`），因此企业库必须先就绪。Phase 2 按高校粒度流水线启动——某高校的 Phase 1 完成后即可触发该校的 Phase 2，无需等待所有高校的 Phase 1 全部完成。Phase 3 在所有 Phase 0 + Phase 1 + Phase 2 完成后执行，Phase 4 在入库后持续运行。

```
Phase 0: 企业数据采集 (Company-Data-Agent) — 必须首先完成
  输入 → 全深圳企业列表 (Excel/CSV) + 企名片 API
  过程 → 批量导入企业骨架 → 企名片 API 补充工商数据 → Web Crawling 充实描述 → LLM 生成画像
  输出 → companies.jsonl + raw/

Phase 1: 教授基础信息采集 (Agent 驱动)
  输入 → 高校教师列表页 URL (手动配置，8-10 所) + Phase 0 产出的企业库
  过程 → BatchScheduler 发现教授列表 → Per-Professor Agent 迭代采集 → DataCleaner 清洗
  输出 → Agent 原始 JSON + professors.jsonl + raw/

Phase 2: 论文深度采集 (独立 Agent，独立存储，Per-School 流水线)
  输入 → Phase 1 产出的教授 ID + 姓名 + 机构 + scholar_id/semantic_scholar_id
  触发 → 某高校的 Phase 1 全部完成后，该校的 Phase 2 即刻启动
  过程 → Paper-Data-Agent 独立运行（见独立 PRD）
  输出 → 论文库 (独立数据库) + pdfs/

Phase 3: 合并反哺与入库
  输入 → Phase 0 + Phase 1 + Phase 2 的全部数据
  过程 → 论文聚类出研究方向 → 生成 profile_summary → 计算 embedding → 入库
  输出 → PostgreSQL 数据就绪

Phase 4: 验证与补采 (本地 MiroThinker 服务)
  输入 → Phase 3 入库后的数据
  过程 → 本地部署 MiroThinker → 批量验证 + 低质量数据补采
  输出 → 修正后的数据 + 验证报告
```

**Phase 0 的核心职责**：构建深圳科创企业全景数据库（详见 [Company-Data-Agent-PRD](./Company-Data-Agent-PRD.md)），为教授 Agent 的 `company_roles` 字段采集提供关联锚点。

**Phase 1 的核心变化**：不再是传统爬虫按预定义规则逐站点抓取，而是为每位教授启动一个独立的 Agent 循环——LLM 在 system prompt 中获得目标数据模型 schema，自主决定需要访问哪些数据源、何时信息足够完整可以停止。采集完成后由独立的 DataCleaner 阶段做字段标准化和质量评分。

**Phase 2 的流水线触发**：Phase 2 不必等所有高校的 Phase 1 完成。以高校为粒度，某校 Phase 1 全部教授采集完毕后，该校即可进入 Phase 2。这大幅缩短了全流程的端到端耗时。

**Phase 4 的核心变化**：不依赖在线 MiroThinker 服务，而是本地部署 MiroThinker 开源框架，以批量任务的形式执行验证和补采。

### 5.1.1 Phase 间数据契约

各 Phase 之间通过明确的数据契约解耦，确保独立开发和测试：

| 交接点 | 生产方 | 消费方 | 数据格式 | 必含字段 |
| --- | --- | --- | --- | --- |
| Phase 0 → Phase 1 | Company-Data-Agent | Professor-Data-Agent | companies 表 | `id`, `name`, `credit_code` |
| Phase 1 → Phase 2 | DataCleaner | Paper-Data-Agent | `professors.jsonl` | `id`, `name`, `name_en`, `institution`, `scholar_id`(可选), `semantic_scholar_id`(可选) |
| Phase 1 → Phase 3 | DataCleaner | 合并反哺模块 | `professors.jsonl` + `raw/` | 4.1 全部已采集字段 |
| Phase 2 → Phase 3 | Paper-Data-Agent | 合并反哺模块 | 论文库（独立数据库） | `professor_id`, `title`, `year`, `citations`, `keywords`, `abstract`, `doi` |
| Phase 3 → Phase 4 | 入库模块 | MiroThinker 验证 | PostgreSQL 表 | 4.1 全部字段 + `completeness_score` |

**契约原则**：
- 每个 Phase 的输出是自包含的，不依赖其他 Phase 的运行时状态
- 数据契约变更需要同步更新生产方和消费方
- 每个交接点都可以独立做集成测试

### 5.2 Phase 1 详细流程

Phase 1 采用两层架构：**BatchScheduler** 负责任务发现与调度，**ProfessorOrchestrator** 负责单个教授的迭代深度采集。采集完成后由独立的 **DataCleaner** 做数据清洗。

#### 5.2.1 BatchScheduler — 任务发现与调度

**入口 URL 配置**：每所高校的教师列表页 URL 通过配置文件手动维护，不做自动发现。原因：列表页数量有限（8-10 所高校），手动配置更可靠，且列表页结构多变、自动发现容易遗漏。

```
for each 高校 (from config):
  1. 爬取教师列表页 → 获取全量教师 URL 列表
  2. 为每位教师创建采集任务 (初始信息: 姓名、所属高校、主页 URL)
  3. 按并发策略分发任务给 ProfessorOrchestrator 实例
```

BatchScheduler 的职责边界：
- 读取配置文件中的入口 URL 列表
- 教师列表页的爬取与解析（这部分是确定性的，用传统爬虫即可）
- 并发控制与限速（per-site rate limit）
- 任务状态管理（pending/running/done/failed）
- 失败重试调度
- 当某高校全部教授采集完成时，通知 Phase 2 可以启动该校的论文采集

#### 5.2.2 ProfessorOrchestrator — Agent 驱动的迭代采集

每位教授启动一个独立的 Agent 循环，借鉴 MiroThinker 的 Orchestrator 多轮推理模式。核心思想：LLM 拿到目标 schema 和初始信息后，自主决定需要调用哪些工具、访问哪些数据源，直到判断信息足够完整。

**System Prompt 设计**：

```
你是教授信息采集 Agent。你的任务是尽可能完整地采集一位教授的信息。

目标数据 Schema:
{name, name_en, institution, department, title, email, homepage,
 education, education_structured, h_index, citation_count, awards, academic_positions, projects,
 work_experience, company_roles, patent_ids, ...}

当前已知信息:
- 姓名: {name}
- 所属高校: {institution}
- 官网主页: {homepage_url}

采集规则:
1. 从官网主页开始，提取所有能获取的结构化字段
2. 识别页面中的外部链接（个人主页、实验室主页、Google Scholar 等）
3. 如果关键字段缺失，通过 Web Search 寻找补充信息源
4. 从 Google Scholar / Semantic Scholar 获取学术指标
5. 对于 Web Search 和 Scholar 返回的结果，交叉验证是否属于同一人
   （通过机构、研究方向、合作者等多信号比对）
6. 从官网/个人主页提取奖励荣誉（awards）、学术兼职（academic_positions）、主持/参与项目（projects）
7. 关联企业时，需记录具体角色（如"联合创始人"、"首席科学家"），不仅记录企业 ID
8. 当你判断已获取足够信息或无法再获取更多时，输出最终结果

消歧规则:
- 机构必须匹配（硬性条件）：搜索到的信息必须与已知的机构一致才能采纳
- 机构匹配后，至少一个辅助信号匹配才标记为 confirmed：辅助信号包括研究方向、合作者、邮箱后缀
- 仅机构匹配但无辅助信号的，标记为 uncertain
- 遇到同名不同人的情况，优先信任校内官网信息
- 不确定的信息标记为 uncertain，不要猜测

幻觉防护:
- 以下关键字段必须提供源 URL 作为证据：name_en, email, h_index, citation_count, scholar_id
- 没有源 URL 支撑的关键字段，不得填充，标记为缺失
- Agent 不得编造或推测任何字段值
```

**多轮循环流程**：

```
Turn 1: 调用 playwright_scraper 爬取官网主页
Turn 2: LLM 解析页面内容 → 提取可用字段 → 识别外部链接
Turn 3: LLM 判断: "缺少 h_index 和 citation_count，需要查 Scholar"
Turn 4: 调用 scholar_scraper 查询 Google Scholar
Turn 5: LLM 合并 Scholar 数据 → 交叉验证确认是同一人
Turn 6: LLM 判断: "缺少个人主页，Web Search 补充"
Turn 7: 调用 web_search 搜索 "{name} {institution} homepage"
Turn 8: 调用 playwright_scraper 爬取发现的个人主页
Turn 9: LLM 合并全部信息 → 判断: "信息足够完整" → 输出结果
```

**关键机制（借鉴 MiroThinker）**：

| 机制 | 说明 |
| --- | --- |
| max_turns 兜底 | 设置最大迭代轮次（如 20 轮），防止无限循环 |
| 重复 URL 检测 | 已爬取过的 URL 不重复爬取，避免死循环 |
| 工具失败回滚 | 工具调用失败时回滚本轮，尝试替代方案（如 Scholar 被封则降级到 Semantic Scholar API） |
| 实时消歧 | LLM 在每轮合并外部信息时，通过机构+方向+合作者多信号交叉验证信息归属 |
| 上下文管理 | 单教授信息量有限，通常不需要上下文压缩；但保留机制以应对信息极丰富的情况 |

**终止条件**（以下任一触发终止）：
1. **LLM 自主判断**：LLM 认为当前信息已足够完整，不再请求工具调用
2. **max_turns 硬兜底**：达到 max_turns 上限时强制终止。终止前检查核心字段（`name`, `institution`, `department`, `title`）是否已填充；若核心字段缺失，追加 1-2 轮定向补充
3. **连续失败退出**：连续 3 轮工具调用失败或返回空结果

**Agent 结构化输出规范**：

Agent 循环结束时，LLM 必须以 JSON 格式输出完整的采集结果（所有已发现的字段，不做子集筛选）。使用 LLM 的 structured output / tool_use 机制强制输出格式：

```json
{
  "name": "张三",
  "name_en": "San Zhang",
  "institution": "南方科技大学",
  "department": "计算机科学与工程系",
  "title": "副教授",
  "email": "zhangs@sustech.edu.cn",
  "homepage": "https://example.com/zhangsan",
  "scholar_id": "abc123xyz",
  "semantic_scholar_id": "456789",
  "education": "2015年获MIT计算机科学博士学位，2010年获清华大学学士学位",
  "education_structured": [
    {"institution": "清华大学", "degree": "本科", "year": "2007-2011", "field": "电子工程"},
    {"institution": "清华大学", "degree": "博士", "year": "2011-2016", "field": "电子工程"}
  ],
  "h_index": 25,
  "citation_count": 3200,
  "awards": [
    {"title": "国家优秀青年科学基金", "year": 2023, "issuer": "国家自然科学基金委员会", "source_url": "https://faculty.sustech.edu.cn/zhangs"}
  ],
  "academic_positions": ["IEEE Senior Member", "中国计算机学会人工智能专委会委员"],
  "projects": [
    {"name": "国家自然科学基金重点项目", "role": "主持人", "source": "NSFC", "source_url": "https://faculty.sustech.edu.cn/zhangs"}
  ],
  "work_experience": [
    {"organization": "佐治亚理工学院", "role": "博士后", "start_year": 2016, "end_year": 2019, "description": "博士后研究"},
    {"organization": "清华大学深圳国际研究生院", "role": "助理教授", "start_year": 2019, "end_year": 2022, "description": "清华-伯克利深圳学院"},
    {"organization": "清华大学深圳国际研究生院", "role": "副教授", "start_year": 2022, "end_year": null, "description": "数据与信息研究院"}
  ],
  "company_roles": [
    {"company_id": "comp_abc123", "role": "首席科学家", "source_url": "https://www.qimingpian.com/firm_abc123"}
  ],
  "patent_ids": ["CN202310000001.1"],
  "fields_confidence": {
    "name": {"level": "confirmed", "source_url": "https://faculty.sustech.edu.cn/zhangs"},
    "email": {"level": "confirmed", "source_url": "https://faculty.sustech.edu.cn/zhangs"},
    "h_index": {"level": "uncertain", "source_url": "https://scholar.google.com/citations?user=abc123xyz"},
    "awards": {"level": "confirmed", "source_url": "https://faculty.sustech.edu.cn/zhangs"},
    "education_structured": {"level": "confirmed", "source_url": "https://faculty.sustech.edu.cn/zhangs"},
    "work_experience": {"level": "confirmed", "source_url": "https://faculty.sustech.edu.cn/zhangs"},
    "company_roles": {"level": "confirmed", "source_url": "https://www.qimingpian.com/firm_abc123"}
  },
  "sources_visited": [
    "https://faculty.sustech.edu.cn/zhangs",
    "https://scholar.google.com/citations?user=abc123xyz",
    "https://www.qimingpian.com/firm_abc123"
  ],
  "notes": "Scholar 上有两个同名作者，已通过机构和研究方向确认为第一个；企名片确认其为 comp_abc123 联合创始人"
}
```

关键设计：
- **`fields_confidence`**：对每个从外部源合并的字段标注置信度（`confirmed` / `uncertain`）和来源 URL。关键字段（`name_en`, `email`, `h_index`, `citation_count`, `scholar_id`, `awards`, `company_roles`, `academic_positions`, `projects`）必须有 `source_url`，否则不得填充。`uncertain` 的字段会在 Phase 4 优先验证。
- **`sources_visited`**：记录 Agent 实际访问过的 URL，供溯源和 DataCleaner 使用。
- **`notes`**：Agent 的消歧判断过程记录，供人工审核时参考。
- **完整输出**：Agent 输出所有已发现的字段，不做子集筛选。DataCleaner 负责后续的格式校验和标准化。
- 输出校验：DataCleaner 对 Agent 输出做 JSON Schema 校验，缺少必填字段或格式不合法的记录标记为 failed 并重试。

#### 5.2.3 DataCleaner — 采集后独立清洗

Agent 循环输出的是原始采集数据（raw_data），需要独立的清洗阶段做标准化处理：

- **字段标准化**：职称映射统一（如"Prof."→"教授"）、机构全称统一、邮箱格式校验
- **completeness_score 计算**：基于已填充字段的数量和重要性加权评分（0-100）
- **数据去重**：检测同一教授是否被采集了多次（基于姓名+机构+邮箱匹配）
- **输出**：写入 professors.jsonl + 保存原始 Agent JSON 到 raw/ 目录

**并发控制**：
- BatchScheduler 层面：每所高校的教授采集任务按配置并发数执行
- 工具层面：每个数据源独立限速，官网 3-5 并发，间隔 1-3 秒随机延迟
- Scholar 爬取严格限速，避免被封

### 5.3 Phase 3 反哺与入库

这是数据质量的关键环节——论文数据反哺教授画像。Phase 3 分为四个子步骤顺序执行。

#### 5.3.1 研究方向精细化

从教授近 5 年论文的关键词和摘要中，由 LLM 聚类归纳出 3-7 个精细研究方向标签，替代官网上"人工智能""计算机科学"这类过于笼统的描述。

**处理流程**：
1. 从论文库中检索该教授近 5 年的所有论文（通过 `scholar_id` 或 `semantic_scholar_id` 精确匹配）
2. 提取每篇论文的标题、关键词、摘要
3. 将论文集合输入 LLM，prompt 要求：
   - 从论文中归纳 3-7 个具体研究方向标签
   - 每个标签应是学术界通用的细粒度术语（如"视觉语言模型"而非"人工智能"）
   - 标签按论文数量/重要性降序排列
4. 输出写入 `research_directions` 字段

**对无论文的教授**：保留 Phase 1 Agent 从官网采集的粗粒度方向（如有），或标记为空。

#### 5.3.2 生成 profile_summary

综合所有数据源，由 LLM 生成 200-300 字的教授画像摘要（规范见 4.2 节）。

**输入组装**：将以下信息拼接为 LLM prompt 的上下文：
- Phase 1 采集的基础信息（姓名、职称、院系、教育背景）
- 5.3.1 产出的精细研究方向标签
- 代表论文 Top-3（标题 + 引用数 + 摘要前 100 字）
- 学术指标（H-index、引用数、近 5 年论文数）
- 关联企业/专利信息（如有）

**LLM Prompt 要点**：
- 以第三人称客观描述
- 必须包含：机构、职称、核心研究方向（用具体技术词汇）、代表性成果
- 禁止使用"等""相关""主要从事"等模糊表述
- 控制在 200-300 字
- 面向语义检索优化：确保不同角度的检索查询都能命中

**批量处理**：5000+ 教授逐条生成，可并发调用 LLM API。对生成失败或输出不合规的记录标记重试。

#### 5.3.2b 生成评价摘要

综合事实维度由 LLM 生成一段客观的事实性评价描述（100-150 字），写入 `evaluation_summary` 字段。用于支撑下游 RAG 智能体回答"大牛""比较厉害"等评价性查询。

**输入组装**：将以下信息拼接为 LLM prompt 的上下文：
- 学术指标（H-index、总引用数、近 5 年论文数）
- 奖项荣誉（按国家级/省部级/学会级分类）
- 学术兼职与社会职务
- 主持/参与项目（级别与数量）

**LLM Prompt 要点**：
- 仅呈现事实，不做主观排名或评分
- 重点呈现：学术指标相对水平、重要奖项及级别、学术头衔、主持重大项目的级别
- 使用具体数据（如"h_index 35""主持国家自然科学基金重点项目 2 项"）
- 控制在 100-150 字
- 避免使用"最优秀""顶尖"等主观判断词

**批量处理**：与 5.3.2 同批处理，可并发调用 LLM API。无足够事实数据的教授可跳过此步（`evaluation_summary` 留空）。

#### 5.3.3 计算 embedding

使用 Embedding 模型（见 [共享技术规范](./Data-Agent-Shared-Spec.md) 可配置组件，本地部署，1024 维）对 `profile_summary` 做向量化。

**批量处理**：支持批量 embedding 调用（如 batch size 64），5000 条预计数分钟内完成。

#### 5.3.4 入库

写入 PostgreSQL + pgvector：
- **表结构**：按 4.1 字段定义建表
- **向量索引**：使用 HNSW 索引（`lists` 参数根据数据量调整，5000 条建议 `ef_construction=128, m=16`）
- **辅助索引**：`institution`、`department`、`title` 建 B-tree 索引，支持结构化筛选
- **写入策略**：UPSERT by `id`，支持增量更新不丢失已有数据

### 5.4 Phase 4 验证与补采（本地 MiroThinker 服务）

本地部署 MiroThinker 开源框架，以批量任务的形式对 Phase 3 入库后的数据进行质量验证和缺失补全。MiroThinker 的在线深度研究能力（多轮搜索、信息交叉验证、上下文推理）天然适合验证场景。

**部署方式**：本地部署 MiroThinker 服务，不依赖外部在线 API。通过批量任务接口逐条提交验证请求。

**验证任务**：
1. **信息准确性验证**：抽样教授记录，MiroThinker 搜索网络交叉验证姓名、机构、职称等信息
2. **论文关联验证**：检查论文是否确实属于该教授（同名消歧校验）
3. **数据补全**：对 `completeness_score < 70` 的教授，MiroThinker 深度搜索补全缺失字段

**抽样策略**：
- 随机抽样 5%（约 250 人）做全面验证
- `completeness_score < 70` 的教授全部验证并补采
- 同名教授（消歧风险高）全部验证
- 每月增量更新的数据全部验证

**执行方式**：作为独立的批处理阶段，本地 MiroThinker 服务读取入库后的数据 → 逐条验证/补采 → 输出验证报告 → 修正数据回写数据库。

---

## 六、系统能力要求

本章定义系统需要具备的核心能力，不约束具体实现技术选型。

### 6.1 Agent 能力要求

| 能力 | 要求 | 说明 |
| --- | --- | --- |
| 多轮推理 | Agent 能进行多轮工具调用与结果分析循环 | 每轮可调用工具、解析结果、判断下一步 |
| 结构化输出 | Agent 输出符合预定义 JSON Schema | 可通过 LLM structured output 或后处理保证 |
| 自主终止判断 | Agent 能判断信息完整度并决定何时停止 | 配合 max_turns 硬兜底 |
| 实时消歧 | Agent 能在采集过程中交叉验证信息归属 | 通过机构+辅助信号判定 |
| 幻觉防护 | 关键字段必须有源 URL 支撑，不得编造 | 无证据的字段留空 |

### 6.2 工具能力要求

系统需要具备以下类别的工具能力，具体工具实现和协议由实现方决定：

| 能力类别 | 功能 | 备注 |
| --- | --- | --- |
| 网页爬取 | 模拟浏览器访问，处理 JS 渲染页面 | 支持动态加载的大学官网 |
| Web 搜索 | 通用互联网搜索，发现补充信息源 | 用于找个人主页、实验室等 |
| 学术数据查询 | 查询 Google Scholar / Semantic Scholar | 获取 H-index、引用数、论文列表 |
| 数据处理 | 格式转换、文本清洗等通用计算 | 辅助 Agent 做数据预处理 |

### 6.3 调度能力要求

| 能力 | 要求 |
| --- | --- |
| 并发控制 | 支持 per-site 并发数限制和全局限速 |
| 任务管理 | 支持任务状态追踪（pending/running/done/failed） |
| 失败重试 | 支持可配置的重试策略 |
| 限速管理 | 不同数据源独立限速，防止被封 |
| 流水线触发 | 某高校 Phase 1 完成后自动触发该校 Phase 2 |

### 6.4 数据能力要求

| 能力 | 要求 |
| --- | --- |
| 向量存储 | 支持向量索引和相似度检索（用于 RAG） |
| 结构化筛选 | 支持按 institution/department/title 等字段精确筛选 |
| UPSERT | 支持增量更新不丢失已有数据 |
| 溯源 | 每条数据可追溯到原始数据源 URL |

---

## 七、数据源与采集策略

### 7.1 可用数据源

Agent 在采集过程中可使用以下数据源，但不预设固定优先级——由 Agent 根据每位教授的实际情况自主决定访问顺序和组合：

| 数据源 | 可获取内容 | 获取方式 |
| --- | --- | --- |
| 高校官网教师主页 | 姓名、职称、院系、邮箱、研究方向、教育背景 | 浏览器模拟爬取 + LLM 解析 |
| Google Scholar | H-index、引用数、论文列表、author ID | 爬取 + SerpAPI 降级 |
| Semantic Scholar | 论文列表、作者 ID、机构信息 | 免费 API（100 req/5min） |
| DBLP | CS 方向论文列表 | 免费 API |
| 企名片 | 教授关联企业（法人/股东/高管） | 付费 API |
| 专利库 | 教授关联专利（发明人匹配） | 现有企业库反向匹配 |
| 百度学术/知网 | 中文论文、中文引用数据 | 爬取/API |
| 个人主页/实验室主页 | 研究方向、项目经历、学生信息 | Agent 从官网或 Web Search 发现后爬取 |

**Agent 自主决策原则**：Agent 从官网主页开始，根据已获信息的缺失情况和页面中发现的外部链接，自主判断下一步应该访问哪个数据源。不同教授的采集路径可能完全不同。

### 7.2 降级策略

当数据源不可用时，Agent 应自动尝试替代方案：

| 场景 | 降级方案 |
| --- | --- |
| 官网主页 404 / 无内容 | Web Search 教授姓名+机构，找替代信息源 |
| Google Scholar 被封 | 切换到 Semantic Scholar API |
| 企名片 API 额度用完 | 仅使用企业库反向匹配，不做企名片正向查询 |
| 学术平台均无数据 | 标记 `completeness_score` 扣分，Phase 4 由 MiroThinker 补采 |

---

## 八、更新策略

- **频率**：每月执行一次全量增量更新
- **增量逻辑**：
  - 重新爬取高校教师列表页，与现有数据比对
  - 新增教师：全流程采集
  - 已有教师：全量重新采集并覆盖（大学页面含动态元素，变更检测成本高于重采成本）
  - 学术指标（H-index、引用数）：随教授重采同步刷新
- **原始数据保留**：临时保存 3 个月，确认无误后可清理

---

## 九、验收标准

### 9.1 数据完整度

| 指标 | 要求 |
| --- | --- |
| 教授总数 | ≥ 目标高校官网公示的教师总数的 95% |
| 必填字段完整率 | `name` + `institution` + `profile_summary` 100% 有值 |
| `completeness_score` ≥ 60 | ≥ 90% 的教授记录 |
| `completeness_score` ≥ 80 | ≥ 60% 的教授记录 |

### 9.2 数据准确度

| 指标 | 要求 |
| --- | --- |
| 抽样准确率 | 5% 抽样人工核对，准确率 ≥ 95% |
| 论文关联准确率 | 抽样验证论文确属该教授，准确率 ≥ 90% |
| 无重复记录 | 同一教授不存在两条记录 |

### 9.3 RAG 端到端验证

**正面查询**：

| 测试查询 | 验收标准 |
| --- | --- |
| "深圳有哪些做具身智能的教授" | Top-5 结果语义相关率 ≥ 85% |
| "介绍清华的丁文伯" | 返回完整教授画像，信息与官网一致 |
| "港中深做 NLP 方向的副教授以上" | 结构化筛选（机构+方向+职称）结果正确 |
| "谁在深圳搞机器人比较厉害" | 模糊查询返回合理结果 |

**负面查询**：

| 测试查询 | 验收标准 |
| --- | --- |
| "介绍一下张三丰教授"（不存在的教授） | 不返回错误信息或无关教授，明确告知无匹配结果 |
| "深圳做量子烹饪的教授"（不存在的研究方向） | 不返回不相关结果，不胡编教授信息 |
| "北京大学的某教授"（非深圳高校） | 不返回结果或提示不在采集范围内 |

### 9.4 采集性能

| 指标 | 要求 |
| --- | --- |
| 全量首次采集 | 5000+ 教授在 72 小时内完成 |
| 月度增量更新 | 24 小时内完成 |
| 单教授采集 | 平均 ≤ 2 分钟（含所有数据源） |
