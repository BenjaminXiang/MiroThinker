# 教授数据采集管线 v2 — 设计规范

> 本文档定义教授数据采集管线的全面改造方案，目标是将当前纯 regex 解析管线升级为
> MiroThinker agent loop 驱动的智能采集管线，使教授数据能够支撑深圳科创智能体的
> 自然语言检索和多轮对话问答。

## 一、第一性原理

本系统的用户通过微信公众号用自然语言提问，系统在教授域中检索并返回结构化、可追溯的回答。

**一切设计决策必须回到这个用户场景**：

- "深圳哪些教授在做大模型？" → 需要精准的 `research_directions` 支撑语义检索
- "介绍一下南科大的张三" → 需要有料的 `profile_summary`，不是套话
- "深圳做芯片的大牛有哪些？" → 需要事实性的 `evaluation_summary`
- "张三发了哪些论文？" / "他有没有创办公司？" / "他有什么专利？" → 需要跨域关联

**因此**：`research_directions`、`profile_summary`、`evaluation_summary`、跨域关联字段
是核心价值字段，设计时按对用户价值排序投入精力，而不是追求全字段完整率。

### 1.1 论文优先原则

**论文是教授画像最准确、最有时效性的信息源，官网信息往往滞后。**

- 官网可能写"人工智能、机器学习"（过于粗泛、多年未更新）
- 但从教授近 5 年论文的标题/摘要/关键词聚类，可以得出"大语言模型安全对齐、RLHF 训练策略、多模态推理"
- 论文还能提供 h-index、引用数、代表成果等客观指标，这些官网通常不展示

因此数据流的逻辑应该是：
```
官网 → 身份锚定（谁、在哪）
论文 → 研究画像（做什么、多厉害、最近在干嘛）
```

### 1.2 一鱼两吃原则

教授域采集过程中获取的论文数据，必须同时写入论文域的 staging 区。教授域是论文域的数据生产者，不仅仅是消费者。这避免了论文域重复采集同一批论文，同时保证论文域以深圳教授为锚点建立完整覆盖。

## 二、当前问题诊断

当前管线（v1）是纯规则解析器（regex + HTMLParser），完全没有 LLM 参与：

| PRD 要求 | v1 现状 |
|----------|---------|
| LLM 负责非结构化网页理解、抽取 | 仅 regex，无 LLM |
| 论文反哺 research_directions | 空 |
| Scholar / Semantic Scholar 辅助来源 | 未调用 |
| education_structured / work_experience | 硬编码 `[]` |
| h_index / citation_count | 硬编码 `None` |
| top_papers / company_roles / patent_ids | 硬编码 `[]` |
| 200-300字有内容的 profile_summary | 模板拼凑套话 |
| 事实性 evaluation_summary | 模板拼凑套话 |

**根因**：`profile.py` 只能匹配固定 label 格式（如 `职称：xxx`），面对千差万别的高校页面模板，大量字段提取不到。`release.py` 用拼模板方式生成摘要，内容全是"已整理N条可追溯来源"之类的元信息，而不是关于教授本人的实质信息。

## 三、方案选择

**选定方案：Per-Professor MiroThinker Agent Loop**

- 复用 MiroThinker 的 `runtime.py` 结构化输出能力
- 每位教授是一个独立的 agent task，自主决策调用哪些工具补充信息
- regex 保留为前置快速筛选层，减少 LLM 调用量
- LLM 分层：本地 Qwen3.5-35B 先跑，质量不达标的升级到在线 qwen3.6-plus
- **能爬就爬，API 是爬不到时的兜底**，充分利用本地算力
- **论文优先采集**，作为教授研究画像的核心信息源，同时反哺论文域

## 四、整体架构与阶段划分

```
                    教授域采集
                   ┌──────────┐
  Seed URLs ──────>│ Stage 1  │──> roster.jsonl
                   │ Roster   │
                   └────┬─────┘
                        │
                   ┌────▼─────┐
                   │ Stage 2a │──> 身份字段（regex 预抽取）
                   │ Identity │
                   └────┬─────┘
                        │
                   ┌────▼─────┐
                   │ Stage 2b │──> enriched.jsonl（教授完整记录）
                   │ Papers   │──> paper_staging.jsonl ──────────┐
                   │ (核心)   │                                  │
                   └────┬─────┘                                  │
                        │                                        ▼
                   ┌────▼─────┐                          ┌──────────────┐
                   │ Stage 2c │                          │  论文域       │
                   │ Agent补全│                          │  Paper Agent  │
                   │(其余字段)│                          │  消费 staging │
                   └────┬─────┘                          └──────┬───────┘
                        │                                       │
                   ┌────▼─────┐                                 │
                   │ Stage 3  │                                 │
                   │ Summary  │<── 论文域发布后回填 paper_id ───┘
                   └────┬─────┘
                        │
                   ┌────▼─────┐
                   │ Stage 4  │──> professor_records.jsonl
                   │ Release  │──> released_objects.jsonl
                   └──────────┘    + Milvus
```

### Stage 1 — Roster Discovery（现有，微调）

- **输入**：`教授 URL.md` 中的 seed URLs（~50 个学院入口）
- **输出**：`roster.jsonl` — `(name, institution, department, profile_url, source_url)`
- **改动**：基本不动。仅为新增 seed URL（深圳技术大学等）补充 roster 解析规则

### Stage 2 — Per-Professor Enrichment（核心新建，三步）

- **输入**：`roster.jsonl`
- **输出**：`enriched.jsonl` + `paper_staging.jsonl`

分三步，顺序至关重要：

1. **Step 2a — Regex Pre-extract（身份锚定）**：沿用 `profile.py`，提取 name、institution、department、title、email 等身份字段
2. **Step 2b — 论文采集（研究画像核心）**：全量爬取该教授的论文列表，分析研究方向、计算学术指标、筛选代表论文。论文同时写入 `paper_staging.jsonl` 供论文域消费
3. **Step 2c — Agent 补全（其余字段）**：按需触发 agent task，补全论文无法覆盖的字段（education、work_experience、awards、company、patent）

### Stage 3 — Summary Generation（新建）

- **输入**：`enriched.jsonl`
- **输出**：`summarized.jsonl` — 补充了 `profile_summary` + `evaluation_summary`
- 走了 agent loop 的教授，摘要在 agent task 内直接生成。Stage 3 只处理跳过 agent 的教授

### Stage 4 — Quality Gate & Release（改造现有）

- **输入**：`summarized.jsonl`
- **输出**：`professor_records.jsonl` + `released_objects.jsonl` + Milvus 向量

## 五、Stage 2 详细设计

### 5.1 Step 2a — Regex Pre-extract（身份锚定）

沿用现有 `profile.py` 的 HTMLParser + regex，提取身份类字段。这一步的定位是**零成本快速筛选**，能提取到的直接用，提不到的留给后续步骤。

提取字段范围：name、institution、department、title、email、office、homepage、research_directions（官网版本）。

### 5.2 Step 2b — 论文采集（研究画像核心）

这是整个管线中信息增量最大的步骤。对每位教授执行：

**采集流程**（爬虫优先）：

```
1. 构造搜索锚点: "{教授姓名}" + "{英文名}" + "{学校英文名}"

2. 爬 Semantic Scholar 作者页
   → semanticscholar.org/search?q={name}+{institution}
   → 找到匹配作者 → 爬作者详情页 → 获取:
     - h-index, citation_count, paper_count
     - 全量论文列表（标题、年份、venue、引用数、DOI、摘要）
   → 反爬失败时降级到 API: /graph/v1/author/search

3. 爬 DBLP 作者页
   → dblp.org/search/author/api?q={name}
   → 解析论文列表（标题、年份、venue、合作者）
   → 与 Semantic Scholar 结果交叉补充

4. 爬 arXiv 搜索
   → arxiv.org/search/?query={name}&searchtype=author
   → 获取预印本列表（标题、摘要、分类标签）

5. 三源论文合并去重
   → 以 DOI 为主键去重，无 DOI 则用 title + year 模糊匹配
   → 保留各源中最完整的记录
```

**同名消歧**（在论文采集阶段执行）：

```
1. affiliation 匹配: 作者机构中包含目标学校名（中英文）
2. 合作者验证: 该作者论文的合作者中是否有同校已知教授
3. 研究方向一致性: 该作者论文主题与官网页面研究方向是否吻合
4. 全部不满足 → 不关联，标记为低置信
```

**论文驱动的研究方向生成**：

```
research_directions 生成优先级:
1. 论文驱动（最高权重）: 近 5 年论文标题+摘要+关键词 → LLM 聚类为 3-7 个精细方向标签
2. 官网补充（次之）: 官网页面提到但论文未覆盖的方向
3. 合并去重: LLM 将两者合并为统一的方向列表，去除过于笼统的标签
```

**论文数据一鱼两吃 — 写入 `paper_staging.jsonl`**：

教授域采集的每篇论文，同时以论文域兼容格式写入 staging 文件：

```python
class PaperStagingRecord(BaseModel):
    """教授采集过程产出的论文，供论文域消费"""
    title: str
    authors: list[str]
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    doi: str | None = None
    citation_count: int | None = None
    keywords: list[str] = []
    source_url: str
    source: str                        # "semantic_scholar" | "dblp" | "arxiv"
    anchoring_professor_id: str        # 从哪位教授出发采集的
    anchoring_professor_name: str
    anchoring_institution: str
```

论文域的 Paper Data Agent 直接消费 `paper_staging.jsonl`，无需重复采集。

### 5.3 Step 2c — Agent 补全（其余字段）

**触发条件**：Step 2a + 2b 完成后，评估剩余缺口：

```python
# 论文采集后，以下字段已有值:
# - research_directions (论文驱动)
# - h_index, citation_count (Semantic Scholar)
# - top_papers (三源合并)

# 仍可能缺失的字段:
AGENT_TARGET_FIELDS = {
    "education_structured": 0.6,   # 教育经历 — 官网/搜索
    "work_experience": 0.6,        # 工作经历 — 官网/搜索
    "awards": 0.5,                 # 奖项 — 官网/搜索
    "academic_positions": 0.4,     # 学术兼职 — 官网/搜索
    "projects": 0.4,               # 项目 — 官网/搜索
    "company_roles": 0.8,          # 企业关联 — 搜索/爬虫（用户高频追问）
    "patent_ids": 0.5,             # 专利关联 — 搜索/爬虫
    "department": 0.8,             # 可能 regex 没提到
    "title": 0.8,                  # 可能 regex 没提到
}
# 缺口加权和 >= 0.5 → 触发 agent
# 缺口加权和 < 0.5 → 跳过 agent，直接进 Stage 3
```

**Agent Task Prompt 结构**：

```
## 任务目标
你是一个教授信息采集助手。以下教授的身份信息和学术画像已通过官网和论文采集获得，
请补全剩余缺失字段。

## 已有信息
姓名: {name}
学校: {institution}
院系: {department}
职称: {title}
研究方向: {research_directions}  ← 已由论文分析生成
h-index: {h_index} | 总引用: {citation_count}
代表论文: {top_5_papers}
官网页面 URL: {profile_url}

## 待补全字段
{gap_list — 仅列出论文步骤未覆盖的字段}

## 官网页面原文
{html_text_truncated_to_4000_chars}

## 工作指引
1. 首先从官网页面原文中提取教育经历、工作经历、奖项等信息
2. 对页面中确实没有的字段，使用工具补充:
   - 企业关联: web_search("{name} {institution} 创办 OR 联合创始人 OR 首席科学家")
     → 爬搜索结果中的天眼查/企查查/新闻页面
   - 专利关联: web_search("{name} {institution} 专利 发明人")
     → 爬搜索结果中的专利公开信息页
   - 其他履历: web_search 或爬个人主页/实验室主页
3. 优先用 web_scrape 直接爬目标页面，web_search 用于发现页面 URL
4. 不能编造信息。没有证据的字段留空

## 输出格式
严格按以下 JSON Schema 输出:
{json_schema}
```

### 5.4 Agent 工具箱

优先级：**爬虫 > web_search > 专用 API**。能爬就爬，节省 API 成本。

| 工具名 | 输入 | 实现方式 | 优先级 |
|--------|------|----------|--------|
| `web_scrape` | `url: str` | 复用 `fetch_html_with_fallback`（requests → Playwright → Jina Reader） | 最高 |
| `web_search` | `query: str` | 复用 Serper `WebSearchProvider` | 高 |
| `semantic_scholar_scrape` | `author_name: str, institution: str` | 爬 `semanticscholar.org` 页面解析 | 中 |
| `dblp_scrape` | `author_name: str` | 爬 `dblp.org` 页面解析 | 中 |
| `arxiv_scrape` | `query: str` | 爬 `arxiv.org/search/` 页面解析 | 中 |
| `semantic_scholar_api` | `author_name: str` | Semantic Scholar REST API | 低（fallback） |
| `dblp_api` | `author_name: str` | DBLP REST API | 低（fallback） |
| `arxiv_api` | `query: str` | arXiv API | 低（fallback） |

**爬虫优先策略**：
- Semantic Scholar 公开作者页面包含 h-index、citation count、论文列表，直接爬比 API 更完整
- DBLP 公开页面结构清晰稳定，直接 HTML 解析即可
- arXiv 搜索结果页可直接解析标题、作者、摘要
- 天眼查/企查查的公开信息页可爬取企业关联
- 只在爬虫被反爬拦截或页面结构解析失败时，降级到 API

### 5.5 LLM 分层执行策略

```
Per-Professor Task (Stage 2b 论文分析 + Stage 2c Agent 补全)
    │
    ├── 第一轮: 本地 Qwen3.5-35B-A3B (免费、快)
    │   ├── 成功 (Pydantic 校验通过 + 核心字段非空) → 进 Stage 3
    │   └── 失败 (校验失败 OR research_directions 仍为空)
    │       │
    │       └── 第二轮: 在线 qwen3.6-plus (阿里百炼)
    │           ├── 成功 → 进 Stage 3
    │           └── 失败 → quality_status="needs_review", 用已有结果兜底
    │
    └── 跳过 agent (Step 2c 缺口加权和 < 0.5) → 直接进 Stage 3
```

### 5.6 输出数据模型

```python
class EnrichedProfessorProfile(BaseModel):
    """Stage 2 输出 — 完整教授档案"""
    name: str
    name_en: str | None = None
    institution: str
    department: str | None = None
    title: str | None = None
    email: str | None = None
    homepage: str | None = None
    office: str | None = None
    research_directions: list[str] = []       # 论文驱动 + 官网补充
    research_directions_source: str = ""      # "paper_driven" | "official_only" | "merged"
    education_structured: list[EducationEntry] = []
    work_experience: list[WorkEntry] = []
    h_index: int | None = None
    citation_count: int | None = None
    paper_count: int | None = None
    top_papers: list[PaperLink] = []
    awards: list[str] = []
    academic_positions: list[str] = []
    projects: list[str] = []
    company_roles: list[CompanyLink] = []
    patent_ids: list[PatentLink] = []
    # 元信息
    enrichment_source: str                    # "regex_only" | "paper_enriched" | "agent_local" | "agent_online"
    evidence_urls: list[str] = []
    field_provenance: dict[str, str] = {}
    # ^ "regex" | "paper_analysis" | "semantic_scholar" | "dblp" | "arxiv" | "agent_official" | "web_search"
```

## 六、跨域关联设计

### 6.1 设计原则

教授域是跨域关联的枢纽。用户的追问路径始终以教授为锚点：

```
"张三发了哪些论文？"     → 教授 → 论文域
"他有没有创办公司？"     → 教授 → 企业域
"他有什么专利？"         → 教授 → 专利域
"他的公司做什么的？"     → 教授 → 企业 → 企业画像
```

关联设计遵循三个原则：
1. **教授域在采集时"顺手"建立关联**，不依赖其他域先发布
2. **关联中的跨域 ID 初始为空**，等对应域发布后异步回填
3. **教授域是论文域的数据生产者**，采集的论文同时供论文域消费

### 6.2 关联数据模型

```python
class PaperLink(BaseModel):
    """教授记录中嵌入的论文关联（精简版，用于教授画像）"""
    paper_id: str | None = None      # PAPER-xxx, 论文域发布后回填
    title: str
    year: int | None = None
    venue: str | None = None
    citation_count: int | None = None
    doi: str | None = None
    source: str                       # "semantic_scholar" | "dblp" | "arxiv" | "web_scrape"

class CompanyLink(BaseModel):
    """教授 → 企业"""
    company_id: str | None = None     # COMP-xxx, 企业域发布后回填
    company_name: str
    role: str                         # "联合创始人" | "首席科学家" | "董事" | ...
    evidence_url: str | None = None
    source: str                       # "web_scrape" | "web_search" | "company_domain"

class PatentLink(BaseModel):
    """教授 → 专利"""
    patent_id: str | None = None      # PAT-xxx, 专利域发布后回填
    patent_title: str
    patent_number: str | None = None
    role: str = "发明人"
    source: str                       # "web_scrape" | "web_search" | "patent_domain"

class PaperStagingRecord(BaseModel):
    """教授采集过程产出的论文完整记录，供论文域消费（一鱼两吃）"""
    title: str
    authors: list[str]
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    doi: str | None = None
    citation_count: int | None = None
    keywords: list[str] = []
    source_url: str
    source: str                        # "semantic_scholar" | "dblp" | "arxiv"
    anchoring_professor_id: str        # 从哪位教授出发采集的
    anchoring_professor_name: str
    anchoring_institution: str
```

### 6.3 采集策略

**论文关联**（Stage 2b 论文采集阶段自然产出）：
- 爬 Semantic Scholar / DBLP / arXiv 作者页 → 全量论文列表
- 筛选 top 5 高引论文 → `top_papers: list[PaperLink]`
- 全部论文以完整格式 → `paper_staging.jsonl`

**企业关联**（Stage 2c Agent 补全阶段）：
- `web_search("{name} {institution} 创办 公司 OR 联合创始人 OR 首席科学家")`
- 爬搜索结果中的天眼查/企查查/新闻页面
- 提取企业名称、角色、证据 URL → `company_roles: list[CompanyLink]`

**专利关联**（Stage 2c Agent 补全阶段）：
- `web_search("{name} {institution} 专利 发明人")`
- 爬搜索结果中的专利公开信息页
- 提取专利标题、专利号、角色 → `patent_ids: list[PatentLink]`

### 6.4 跨域 ID 回填机制

教授域先发布带空 ID 的关联：

```
教授域发布: top_papers: [{title: "xxx", paper_id: null}]
论文域发布后 → 用 title + year + author_name 匹配 → 回填 paper_id = "PAPER-xxx"
企业域发布后 → 用 company_name 匹配 → 回填 company_id = "COMP-xxx"
专利域发布后 → 用 patent_number 或 title + inventor_name 匹配 → 回填 patent_id = "PAT-xxx"
```

### 6.5 回填触发摘要刷新

回填后不一定重新生成摘要。阈值：新增 >= 3 条论文关联 或 新增任意企业关联时触发 `profile_summary` 刷新。

### 6.6 关联信息在 Agentic RAG 中的使用

教授记录中的 `top_papers` 是**快速回答路径**（"他最有影响力的论文包括..."），不是完整论文库。用户追问"张三发了哪些论文"时，RAG 应：

1. 从教授记录取 `name` + `institution` 作为锚点
2. 在论文域 Milvus 中用教授名做 filter 检索
3. 返回完整论文列表

企业和专利关联同理：快速路径用教授记录中的嵌入关联，深度追问走跨域检索。

## 七、Summary Generation 设计

### 7.1 `profile_summary` 生成规则

200-300 字中文，面向语义检索和对话回答。**论文驱动的研究描述应占主体篇幅。**

```
LLM 指令要点:
- 第一句: 姓名 + 学校 + 院系 + 职称（身份锚定，来自官网）
- 第二部分（最大篇幅）: 具体研究方向和最近研究趋势
  - 来自论文分析，使用领域术语
  - 到"基于Transformer的蛋白质结构预测"粒度，不要"人工智能"大词
  - 如有近 2 年的新方向转变，明确提及
- 第三部分: 代表性成果和学术影响力
  - 高引论文、顶会/顶刊、h-index（来自论文采集）
  - 重要奖项、重点项目（来自官网/搜索）
- 第四部分: 教育背景和关键履历（如有，来自官网/搜索）
- 禁止: 套话、模糊表述、对缺失信息做推测
- 缺少信息的维度直接跳过，不用"暂未获取"填充
```

**信息权重**：
- 身份信息（官网）→ 第一句
- 研究画像（论文驱动）→ 主体段落（最大篇幅）
- 学术影响力（论文 + Scholar）→ 第三部分
- 背景履历（官网 + 搜索）→ 末尾补充

### 7.2 `evaluation_summary` 生成规则

100-150 字，纯事实性：

```
仅使用客观信息:
- 人才称号（国家杰青、长江学者等）
- 学术指标（h-index、总引用数、论文总数）
- 代表论文影响力（顶会/顶刊、引用数）
- 重要奖项、重大项目
- 学术兼职（期刊编委、学会职务）
禁止主观评价。没有数据的维度直接跳过。
```

### 7.3 执行策略

- 走了 agent loop 的教授：摘要在 agent task 内直接生成（省一次 LLM 调用，此时 agent 拥有最完整的上下文）
- 跳过 agent 的教授：Stage 3 单独用 LLM 生成
- 分层：本地 Qwen3.5-35B 批量 → 质量不达标（无具体研究术语、长度不达标）升级到 qwen3.6-plus

## 八、Quality Gate、向量化与发布

### 8.1 三级校验

**L1 — 硬性拦截**（不通过则不发布）：
- `name` 非空
- `institution` 非空且属于深圳高校范围
- `evidence_urls` 中至少有一条 official_site 来源
- `profile_summary` 200-300 字且不含模板套话关键词（"暂未获取"、"持续补全"、"仍在完善"）

**L2 — 质量标记**（发布但标记 `quality_status`）：
- `research_directions` 为空 → `quality_status = "incomplete"`
- `profile_summary` 中无具体研究术语 → `quality_status = "shallow_summary"`
- `enrichment_source = "regex_only"` 且无论文数据 → `quality_status = "needs_enrichment"`
- 其余 → `quality_status = "ready"`

**L3 — 统计告警**（全量评估）：
- `ready` 占比 < 70% → 告警
- 某高校覆盖率 vs 官网教师总数差异 > 20% → 告警
- 同名教授 > 5% → 需人工抽检

### 8.2 向量化

embedding 对象为 `profile_summary`（信息浓缩后的自然语言，最适合语义检索），
另用 `research_directions` 拼接为一句话做独立 embedding 用于研究方向精确检索。

```python
profile_vector = embed(profile_summary)                    # 通用语义检索
direction_vector = embed("，".join(research_directions))   # 研究方向精确检索
```

- 模型：本地 Qwen3-Embedding-8B（`http://172.18.41.222:18005/v1/embeddings`）
- 批量：每次 50-100 条
- 向量维度：4096

### 8.3 Milvus Collection Schema

```
collection: professor_profiles
fields:
  - id: VARCHAR(64), primary key
  - name: VARCHAR(128)
  - institution: VARCHAR(128)
  - department: VARCHAR(128)
  - title: VARCHAR(64)
  - research_directions: VARCHAR(1024)  # JSON array string
  - profile_summary: VARCHAR(2048)
  - evaluation_summary: VARCHAR(1024)
  - quality_status: VARCHAR(32)
  - profile_vector: FLOAT_VECTOR(4096)
  - direction_vector: FLOAT_VECTOR(4096)
indexes:
  - profile_vector: HNSW, COSINE, M=16, efConstruction=256
  - direction_vector: HNSW, COSINE, M=16, efConstruction=256
  - institution: TRIE
  - quality_status: TRIE
```

## 九、并发控制与成本

### 9.1 规模估算

- Seed URLs: ~50 个学院入口
- 教授总量: 3000-5000 人
- 论文采集（Stage 2b）: 全量教授，每人爬 3 个学术源页面 ≈ 9000-15000 次爬虫
- 需要 agent（Stage 2c）: ~50%（论文采集后缺口缩小），约 1500-2500 个 agent task

### 9.2 并发配置

```yaml
professor_pipeline_v2:
  stage2a:
    max_concurrent_regex: 16          # regex 无外部依赖，可高度并行
  stage2b:
    max_concurrent_paper_crawl: 8     # 学术源爬虫并发
    crawl_delay_range: [1, 3]         # 爬虫间隔（秒）
    local_llm_qps: 4                  # 论文→研究方向聚类用本地 LLM
  stage2c:
    max_concurrent_agents: 8
    local_llm_qps: 4
    online_llm_qps: 2
    web_search_qps: 2
    html_fetch_delay_range: [1, 3]
  stage3:
    max_concurrent_summary: 16
    local_llm_qps: 8
  stage4:
    embedding_batch_size: 50
```

### 9.3 成本

- 本地模型 (Qwen3.5-35B): 免费，算力充足
- 在线模型 (qwen3.6-plus): ~15% 教授需升级 ≈ 500 人 × 15K token ≈ 7.5M token ≈ ¥30
- Serper web search: 免费额度 2500 次/月，主要用于企业/专利关联搜索
- 学术源爬虫: 免费（Semantic Scholar / DBLP / arXiv 公开页面）
- Semantic Scholar API (fallback): 免费

### 9.4 容错与断点恢复

- `enriched.jsonl` 和 `paper_staging.jsonl` 采用 append 写入，每完成一位教授立即写入
- 重跑时读取已有记录，跳过已完成的教授
- 失败任务记录到 `failed_tasks.jsonl`，支持 `--retry-failed` 单独重跑
- HTML 缓存沿用 `logs/debug/professor_fetch_cache/`，学术页面缓存同样按 URL hash 存储

## 十、代码变更范围

### 新增文件

```
apps/miroflow-agent/src/data_agents/professor/
├── agent_enrichment.py      # Stage 2c: per-professor agent task 编排
├── paper_collector.py       # Stage 2b: 论文采集、三源合并、研究方向聚类
├── completeness.py          # 缺口评估 + agent 触发判断
├── summary_generator.py     # Stage 3: LLM 摘要生成
├── quality_gate.py          # Stage 4: L1/L2/L3 校验
├── vectorizer.py            # Stage 4: embedding + Milvus
├── academic_tools.py        # 学术源爬虫（Semantic Scholar / DBLP / arXiv）+ API fallback
└── cross_domain.py          # PaperLink, CompanyLink, PatentLink, PaperStagingRecord
```

### 修改文件

```
apps/miroflow-agent/src/data_agents/professor/
├── models.py                # 扩展 EnrichedProfessorProfile
├── pipeline.py              # 串联四阶段入口（Stage 2 拆为 2a/2b/2c）
├── release.py               # 集成 LLM summary + quality gate
├── enrichment.py            # 保留 regex extract，增加完整度评估

apps/miroflow-agent/conf/data_agent/
├── default.yaml             # 增加 v2 配置项

apps/miroflow-agent/src/data_agents/providers/
├── (可能新增 dashscope.py)  # 阿里百炼 provider
```

### 不动文件

```
discovery.py, roster.py, profile.py, parser.py, name_selection.py, validator.py
```

## 十一、可用 API 资源

| 能力 | 提供方 | 端点 / 备注 |
|------|--------|-------------|
| LLM 强推理 | 阿里百炼 qwen3.6-plus | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| LLM 强推理 | 火山 doubao-seed-2.0-pro | `https://ark.cn-beijing.volces.com/api/v3`, model=`ep-20260331212828-jsxq8` |
| LLM 快速 | 本地 Qwen3.5-35B-A3B | `http://star.sustech.edu.cn/service/model/qwen35/v1` |
| LLM 快速 | 本地 Gemma-4-26B | `http://172.18.41.222:18331/v1` |
| LLM 混合路由 | 火山混合模型 | `ep-20260331213507-8db88` |
| Web Search | Serper | `https://google.serper.dev/search` |
| Embedding | 本地 Qwen3-Embedding-8B | `http://172.18.41.222:18005/v1/embeddings`，4096 维 |
| Rerank | 本地 Qwen3-Reranker-8B | `http://172.18.41.222:18006/v1/rerank` |

## 十二、发布产物

```
logs/data_agents/professor/
├── roster.jsonl              # Stage 1 — 教授名单
├── enriched.jsonl            # Stage 2 — 完整教授档案
├── paper_staging.jsonl       # Stage 2b — 论文数据（供论文域消费）
├── summarized.jsonl          # Stage 3 — 含摘要的教授档案
├── professor_records.jsonl   # Stage 4 — 最终发布（ProfessorRecord）
├── released_objects.jsonl    # Stage 4 — 通用 ReleasedObject
├── quality_report.json       # Stage 4 — L3 统计告警
├── failed_tasks.jsonl        # 失败任务记录（支持重跑）
└── run_meta.json             # 运行元信息（时间、seed 数、各阶段统计）
```
