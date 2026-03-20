# 数据采集智能体群 — 共享技术规范

本文档定义 Company-Data-Agent、Professor-Data-Agent 和 Paper-Data-Agent 共享的技术规范，包括整体架构、数据库设计、接口约定和质量保证框架。

---

## 一、整体架构

### 1.1 三个智能体 + 五阶段流水线

```
┌─────────────────────────────────────────────────────────┐
│                     调度层 (Cron)                         │
│  每月触发 → Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 │
└──────────────────────┬──────────────────────────────────┘
                       │
  Phase 0: Company-Data-Agent
  ┌────────────────────▼──────────────────────┐
  │ 输入: 全深圳企业列表 (Excel/CSV) + 企名片 API │
  │ 过程: 批量导入骨架 → 企名片补充 → Web Crawling │
  │       充实 → LLM 生成画像 → embedding + 入库   │
  │ 输出: companies.jsonl + raw/                │
  └────────────────────┬──────────────────────┘
                       │
  Phase 1: Professor-Data-Agent
  ┌────────────────────▼──────────────────────┐
  │ 输入: 高校教师列表页 URL                    │
  │ 过程: 爬取官网 + Scholar + 企名片           │
  │ 输出: professors.jsonl + raw/              │
  └────────────────────┬──────────────────────┘
                       │
  Phase 2: Paper-Data-Agent
  ┌────────────────────▼──────────────────────┐
  │ 输入: 教授 ID + 姓名 + 机构列表            │
  │ 过程: Arxiv/Scholar/DBLP + PDF解析 + 摘要  │
  │ 输出: papers.jsonl + pdfs/ + raw/          │
  └────────────────────┬──────────────────────┘
                       │
  Phase 3: 反哺 + 入库
  ┌────────────────────▼──────────────────────┐
  │ 过程:                                      │
  │  1. 论文关键词 → 教授研究方向精细化         │
  │  2. LLM 生成教授/企业 profile_summary       │
  │  3. BGE-M3 计算所有 embedding              │
  │  4. 导入 PostgreSQL + 建索引               │
  │  5. 生成采集报告                           │
  └────────────────────┬──────────────────────┘
                       │
  Phase 4: MiroThinker 验证 + 补采
  ┌────────────────────▼──────────────────────┐
  │ 过程:                                      │
  │  1. 抽样 + 定向验证教授/企业信息准确性      │
  │  2. 验证论文-教授关联正确性                │
  │  3. 低质量数据由 MiroThinker 深度补采       │
  │  4. 修正数据回写 + 输出验证报告            │
  └───────────────────────────────────────────┘
```

### 1.2 执行依赖关系

- **Phase 0 必须先于 Phase 1 完成**：教授 Agent 采集时需通过企名片 API 关联企业信息（写入 `company_roles`），因此企业库必须先就绪
- Phase 2 依赖 Phase 1 产出的教授 ID 列表
- Phase 3 依赖 Phase 0 + Phase 1 + Phase 2 的全部数据
- Phase 4 依赖 Phase 3 入库完成
- Phase 0 中各企业采集任务、Phase 1 中各教授采集任务、Phase 2 中各论文采集任务互相独立，可并行

---

## 二、数据库选型

### 2.1 方案：PostgreSQL + pgvector（单库）

**选型理由**（从查询链路出发）：

1. **LLM 生成 SQL 的准确率最高**：下游 RAG 智能体需要将用户自然语言转换为数据库查询。LLM 生成 PostgreSQL SQL 的能力远优于生成 Elasticsearch DSL 或其他查询语言——这是查询链路中最关键的准确率瓶颈。

2. **一条 SQL 实现多路召回**：pgvector 允许在同一条 SQL 中同时完成向量语义检索 + 结构化筛选 + 关联查询，无需跨库协调。

3. **数据规模不需要分布式**：5000 教授 + 25 万论文的向量检索在 pgvector HNSW 索引上 < 10ms，远低于 5s 的 SLA 要求。专用向量数据库（Milvus/Qdrant）为百万/亿级设计，此处过度。

4. **运维最简**：一个数据库，一套备份策略，一个连接池。避免多库数据同步。

### 2.2 扩展

- **pgvector**：向量存储与检索（HNSW 索引，余弦距离）
- **pg_trgm**：模糊文本匹配（三字母组相似度）
- **zhparser**（可选）：中文全文检索分词

---

## 三、数据库 Schema

```sql
-- 企业表
CREATE TABLE companies (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    credit_code         TEXT NOT NULL UNIQUE,
    legal_representative TEXT,
    registered_capital  TEXT,
    establishment_date  DATE,
    registered_address  TEXT,
    industry            TEXT,
    business_scope      TEXT,
    product_description TEXT,
    tech_tags           TEXT[],
    industry_tags       TEXT[],
    financing_round     TEXT,
    financing_amount    TEXT,
    investors           TEXT[],
    patent_count        INTEGER,
    team_description    TEXT,
    key_personnel      JSONB,       -- [{name, role, education: [{institution, degree, year, field}]}]
    website             TEXT,
    profile_summary     TEXT NOT NULL,
    profile_embedding   VECTOR,
    sources             TEXT[] NOT NULL,
    completeness_score  INTEGER NOT NULL,
    last_updated        TIMESTAMP DEFAULT NOW(),
    raw_data_path       TEXT NOT NULL
);

-- 教授表
CREATE TABLE professors (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    name_en             TEXT,
    institution         TEXT NOT NULL,
    department          TEXT,
    title               TEXT,
    email               TEXT,
    homepage            TEXT,
    research_directions TEXT[],
    education           TEXT,
    education_structured  JSONB,       -- [{institution, degree, year, field}]
    h_index             INTEGER,
    citation_count      INTEGER,
    recent_paper_count  INTEGER,
    top_papers          JSONB,
    company_roles       JSONB,       -- [{company_id, role, source_url}]
    patent_ids          TEXT[],
    awards              JSONB,       -- [{title, year, issuer, source_url}]
    academic_positions  TEXT[],
    projects            JSONB,       -- [{name, role, source, source_url}]
    work_experience       JSONB,       -- [{organization, role, start_year, end_year, description}]
    evaluation_summary    TEXT,         -- LLM 生成的事实性评价摘要（大牛判断用）
    profile_summary     TEXT NOT NULL,
    profile_embedding   VECTOR,          -- 维度由 embedding 模型配置决定
    sources             TEXT[],
    completeness_score  INTEGER,
    last_updated        TIMESTAMP DEFAULT NOW(),
    raw_data_path       TEXT
);

-- 论文表
CREATE TABLE papers (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    title_zh            TEXT,
    authors             JSONB NOT NULL,
    professor_ids       TEXT[],
    year                INTEGER NOT NULL,
    venue               TEXT,
    arxiv_id            TEXT,
    arxiv_version       TEXT,
    doi                 TEXT,
    abstract            TEXT,
    summary_zh          JSONB,
    summary_text        TEXT,
    summary_type        TEXT NOT NULL DEFAULT 'pending',
    keywords            TEXT[],
    pdf_path            TEXT,
    full_text           TEXT,
    citation_count      INTEGER,
    summary_embedding   VECTOR,          -- 维度由 embedding 模型配置决定
    status              TEXT NOT NULL DEFAULT 'discovered',
    last_updated        TIMESTAMP DEFAULT NOW()
);

-- 专利表
CREATE TABLE patents (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    patent_number       TEXT,
    applicant           TEXT,
    inventors           TEXT[],
    type                TEXT,            -- 发明/实用新型/外观设计
    status              TEXT,            -- 已授权/申请中/已失效
    filing_date         DATE,
    publication_date    DATE,
    grant_date          DATE,
    abstract            TEXT,
    technical_scheme    TEXT,
    ipc_codes           TEXT[],
    claims              JSONB,
    llm_summary         TEXT,
    source              TEXT,
    last_updated        TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_prof_embedding ON professors
    USING hnsw (profile_embedding vector_cosine_ops);
CREATE INDEX idx_prof_institution ON professors(institution);
CREATE INDEX idx_prof_title ON professors(title);
CREATE INDEX idx_prof_directions ON professors
    USING GIN (research_directions);
CREATE INDEX idx_prof_education_structured ON professors
    USING GIN (education_structured);
CREATE INDEX idx_prof_work_experience ON professors
    USING GIN (work_experience);

CREATE INDEX idx_paper_embedding ON papers
    USING hnsw (summary_embedding vector_cosine_ops);
CREATE INDEX idx_paper_professor ON papers
    USING GIN (professor_ids);
CREATE INDEX idx_paper_keywords ON papers
    USING GIN (keywords);
CREATE INDEX idx_paper_year ON papers(year);
CREATE INDEX idx_paper_venue ON papers(venue);
CREATE INDEX idx_paper_arxiv ON papers(arxiv_id);
CREATE INDEX idx_paper_doi ON papers(doi);

CREATE INDEX idx_company_embedding ON companies
    USING hnsw (profile_embedding vector_cosine_ops);
CREATE INDEX idx_company_industry ON companies(industry);
CREATE INDEX idx_company_tech_tags ON companies
    USING GIN (tech_tags);
CREATE INDEX idx_company_industry_tags ON companies
    USING GIN (industry_tags);
CREATE INDEX idx_company_key_personnel ON companies
    USING GIN (key_personnel);

CREATE INDEX idx_patent_applicant ON patents(applicant);
CREATE INDEX idx_patent_inventors ON patents
    USING GIN (inventors);
CREATE INDEX idx_patent_ipc ON patents
    USING GIN (ipc_codes);
CREATE INDEX idx_patent_type ON patents(type);
CREATE INDEX idx_patent_status ON patents(status);
```

---

## 四、可配置组件

以下技术组件在系统中应作为可配置项，PRD 不绑定具体实现，只定义能力需求。

### 4.1 配置项清单

| 组件 | 能力需求 | 配置方式 |
| --- | --- | --- |
| **Embedding 模型** | 中文语义向量化，输出维度需与 DB VECTOR 列一致 | 模型名称 + 维度 + 部署地址 |
| **LLM** | 结构化信息提取、摘要生成、研究方向聚类等 | 模型名称 + API 地址 + 密钥 |
| **Web Search API** | 教授信息补充搜索、MiroThinker 验证 | 服务商 + API 密钥 |
| **学术平台爬取** | Scholar/Semantic Scholar 学术指标获取 | 爬虫实现 + 代理 API（可选） |
| **PDF 解析** | 论文全文提取（含公式、表格） | VLM 模型 + 部署地址 |
| **企名片 API** | 企业工商数据、融资、股东等结构化补充 | API 密钥 + 缓存策略 |
| **Web Crawling** | 企业官网、PR 稿件等非结构化数据爬取 | 爬虫框架 + 代理（可选） |

### 4.2 配置文件示例

```yaml
# config.yaml — 所有外部依赖均通过此文件配置

embedding:
  # 向量维度需与 DB Schema 中 VECTOR(N) 一致
  # 更换模型时需同步更新 DB Schema 和重建索引
  model: "BAAI/bge-m3"
  dimension: 1024
  endpoint: "http://localhost:8080/embed"

llm:
  model: "deepseek-v3"
  endpoint: "http://localhost:8081/v1"
  api_key: "${LLM_API_KEY}"

web_search:
  provider: "serper"  # serper / bing / sogou / ...
  api_key: "${SEARCH_API_KEY}"

pdf_parser:
  model: "marker"  # marker / nougat / ...
  endpoint: "http://localhost:8082/parse"

scholar:
  primary: "self_crawler"        # 自写爬虫
  fallback: "serpapi"            # 付费代理降级
  serpapi_key: "${SERPAPI_KEY}"

qimingpian:
  api_key: "${QIMINGPIAN_API_KEY}"
  endpoint: "https://api.qimingpian.com"
  cache_ttl_days: 7
  rate_limit: "100 req/min"

crawling:
  max_concurrency: 3
  delay_range: [2, 5]            # 秒
  timeout: 30                    # 秒
```

### 4.3 约束

- **向量维度一致性**：Embedding 模型的输出维度必须与数据库 `VECTOR(N)` 列定义一致。更换 Embedding 模型时需重建向量列和索引。
- **LLM 能力下限**：所选 LLM 需具备从非结构化中文/英文网页中提取结构化 JSON 的能力，以及生成 200-300 字中文摘要的能力。
- **Web Search 覆盖**：所选搜索 API 需支持中文查询。

### 4.4 向量化对象

| 对象 | 源文本 | 用途 |
| --- | --- | --- |
| `professors.profile_embedding` | `profile_summary`（200-300 字画像摘要） | 教授语义检索 |
| `companies.profile_embedding` | `profile_summary`（200-300 字企业画像摘要） | 企业语义检索 |
| `papers.summary_embedding` | `summary_text`（四段式摘要拼接文本） | 论文语义检索 |

---

## 五、RAG 查询接口约定

### 5.1 查询函数定义

下游 RAG 智能体通过以下函数访问数据（具体实现可以是 SQL 生成或直接函数调用）：

```python
# 教授查询
search_professors(
    query: str,                    # 自然语言查询
    filters: dict = None,          # 可选结构化筛选
    # filters 支持: institution, title, research_directions
    mode: str = "hybrid",          # semantic / exact / hybrid
    limit: int = 10
) -> list[Professor]

get_professor(id: str) -> Professor

# 论文查询
search_papers(
    query: str,
    filters: dict = None,
    # filters 支持: professor_id, year_range, venue, keywords
    mode: str = "hybrid",
    limit: int = 10
) -> list[Paper]

get_paper(id: str) -> Paper

# 企业查询
search_companies(
    query: str,
    filters: dict = None,
    # filters 支持: industry, financing_round, tech_tags, industry_tags
    mode: str = "hybrid",
    limit: int = 10
) -> list[Company]

get_company(id: str) -> Company

# 专利查询
search_patents(
    query: str,
    filters: dict = None,
    # filters 支持: applicant, type, status, filing_date_range, ipc_codes
    mode: str = "hybrid",
    limit: int = 10
) -> list[Patent]

get_patent(id: str) -> Patent

# 关联查询
get_professor_papers(professor_id: str) -> list[Paper]
get_paper_professors(paper_id: str) -> list[Professor]
get_professor_companies(professor_id: str) -> list[Company]
get_company_patents(company_name: str) -> list[Patent]
```

### 5.2 查询模式说明

| 模式 | 实现 | 适用场景 |
| --- | --- | --- |
| `exact` | SQL WHERE 精确匹配 | "介绍清华的丁文伯" |
| `semantic` | pgvector 向量相似度 | "深圳有谁在做具身智能" |
| `hybrid` | 向量检索 + 结构化筛选 | "港中深做 NLP 的副教授以上" |

### 5.3 多路召回的 SQL 示例

```sql
-- 混合查询: 语义 + 结构化筛选
SELECT id, name, institution, title, research_directions,
       1 - (profile_embedding <=> $query_embedding) AS relevance
FROM professors
WHERE institution LIKE '%深圳%'
  AND title IN ('教授', '副教授')
ORDER BY relevance DESC
LIMIT 10;

-- 关联查询: 教授的论文
SELECT p.*
FROM papers p
WHERE $professor_id = ANY(p.professor_ids)
ORDER BY p.year DESC, p.citation_count DESC
LIMIT 20;

-- 论文语义检索 + 时间筛选
SELECT id, title, title_zh, summary_zh, year, venue,
       1 - (summary_embedding <=> $query_embedding) AS relevance
FROM papers
WHERE year >= 2023
ORDER BY relevance DESC
LIMIT 10;

-- 企业语义检索 + 行业筛选
SELECT id, name, industry, financing_round, product_description,
       1 - (profile_embedding <=> $query_embedding) AS relevance
FROM companies
WHERE industry LIKE '%机器人%'
ORDER BY relevance DESC
LIMIT 10;

-- 专利按申请人查询
SELECT id, title, patent_number, type, status, applicant, filing_date
FROM patents
WHERE applicant LIKE '%优必选%'
ORDER BY filing_date DESC
LIMIT 20;

-- 教授关联企业查询
SELECT c.*
FROM companies c, professors p
WHERE p.id = $professor_id
  AND p.company_roles IS NOT NULL
  AND c.id = ANY(
    SELECT elem->>'company_id'
    FROM jsonb_array_elements(p.company_roles) elem
  );
```

---

## 六、数据质量保证框架

### 6.1 三维度质量模型

| 维度 | 含义 | 自动化检查 |
| --- | --- | --- |
| 完整度 | 必填字段不为空 | 入库时检查，计算 `completeness_score` |
| 准确度 | 数据与真实世界一致 | 规则校验 + MiroThinker 抽样验证 |
| 唯一性 | 无重复记录 | 去重逻辑 + 唯一约束 |

### 6.2 自动化校验规则

**教授数据**：
1. `institution` 必须在目标高校列表中
2. `research_directions` 与其论文的 `keywords` 重叠率 ≥ 30%
3. `h_index` 不超过 150（超出标记异常）
4. 近 5 年论文数不超过 50 篇/年（超出可能是同名人混入）

**论文数据**：
1. `year` 不晚于当前年份
2. `authors` 不为空
3. `summary_zh` 包含完整的 what/why/how/result 四段
4. `keywords` 至少 2 个标签

**企业数据**：
1. `credit_code` 格式校验（18 位）
2. `name` 不能为空
3. `profile_summary` 长度 150-400 字
4. 融资金额格式校验

### 6.3 completeness_score 计算

| 字段 | 权重 | 说明 |
| --- | --- | --- |
| name + institution | 12 | 必填，缺则不入库 |
| profile_summary | 12 | 必填 |
| title + department | 7 | 重要但非致命 |
| email + homepage | 7 | 联系方式 |
| h_index + citation_count | 10 | 学术指标 |
| research_directions | 10 | 需论文反哺后才有 |
| awards | 9 | 奖励荣誉，对"大牛"判断等评估类查询关键 |
| academic_positions | 7 | 学术兼职，体现学术影响力 |
| projects | 6 | 主持/参与项目，体现科研实力 |
| education_structured | 5 | 结构化教育经历（新增） |
| work_experience | 5 | 工作经历（新增） |
| company_roles / patent_ids | 4 | 关联数据，有则加分 |
| evaluation_summary | 6 | 事实性评价摘要（新增） |

**企业 completeness_score 权重**：

| 字段 | 权重 |
| --- | --- |
| name + credit_code | 20（必填） |
| profile_summary | 15（必填） |
| product_description + tech_tags | 15 |
| financing_round + investors | 15 |
| legal_representative + registered_capital | 10 |
| team_description + key_personnel | 10 |
| website + patent_count | 10 |
| 其他 | 5 |

### 6.4 MiroThinker 验证抽样策略

| 类别 | 数量 | 验证内容 |
| --- | --- | --- |
| 随机抽样 | 5%（约 250 人） | 全面验证所有字段 |
| 低质量记录 | `completeness_score < 70` 全部 | 验证 + 补全缺失字段 |
| 同名教授 | 全部 | 消歧验证 |
| 月度增量 | 全部 | 新增/变更数据验证 |

---

## 七、自动化调度方案

### 7.1 月度执行计划

```
每月 1 号触发:
  Day 1-2:   Phase 0 — 企业数据采集（批量导入 + 企名片补充 + Web Crawling 充实）
  Day 2-4:   Phase 1 — 教授基础信息采集
  Day 4-10:  Phase 2 — 论文采集 + PDF解析 + 摘要生成
  Day 10-11: Phase 3 — 反哺 + 入库
  Day 11-12: Phase 4 — MiroThinker 验证 + 补采
  Day 12:    生成月度采集报告
```

### 7.2 采集报告内容

每月采集完成后自动生成报告，包含：

- 企业：总数、新增数、更新数、completeness_score 分布、企名片数据覆盖率
- 教授：总数、新增数、更新数、completeness_score 分布
- 论文：总数、新增数、PDF 下载成功率、摘要完成率
- 质量：自动化校验通过率、MiroThinker 验证发现的问题数
- 异常：采集失败记录、数据质量异常记录

### 7.3 错误处理

| 错误类型 | 处理策略 |
| --- | --- |
| 网络超时 | 重试 3 次，指数退避 |
| 数据源 API 限流 | 等待后重试，记录限流时间 |
| LLM 调用失败 | 重试 2 次，失败则标记待处理 |
| 解析异常 | 标记失败状态，降级处理 |

所有任务支持断点续传——记录每个教授/论文的处理状态，中断后可从上次断点继续。

---

## 八、数据交付格式

### 8.1 中间文件格式

```
output/
├── companies.jsonl         # 每行一条企业 JSON
├── professors.jsonl        # 每行一条教授 JSON
├── papers.jsonl            # 每行一条论文 JSON
├── embeddings/
│   ├── companies.npy       # 企业画像向量 (K x 1024)
│   ├── professors.npy      # 教授画像向量 (N x 1024)
│   └── papers.npy          # 论文摘要向量 (M x 1024)
├── pdfs/                   # 论文 PDF 文件
│   └── {arxiv_id}.pdf
├── raw/                    # 原始爬取数据（临时保存 3 个月）
│   ├── companies/
│   │   └── {company_id}/   # 每家企业的原始页面
│   ├── professors/
│   │   └── {prof_id}/      # 每位教授的原始页面
│   └── papers/
│       └── {paper_id}/     # 每篇论文的原始数据
└── reports/
    └── {yyyy-mm}_report.json  # 月度采集报告
```

### 8.2 入库脚本

独立的入库脚本负责：
1. 读取 JSONL + embeddings
2. 数据校验（完整度 + 去重）
3. 导入 PostgreSQL（upsert 语义：存在则更新，不存在则新增）
4. 重建索引
5. 生成导入报告（新增 N 条、更新 N 条、失败 N 条及原因）

---

## 九、与下游系统的关系

本数据采集智能体群为以下系统提供数据支撑：

| 下游系统 | 消费的数据 | 参考文档 |
| --- | --- | --- |
| 深圳科创检索增强智能体（模块一：查找教授） | professors 表 | [Agentic-RAG-PRD.md](./Agentic-RAG-PRD.md) |
| 深圳科创检索增强智能体（模块二：查找企业） | companies 表 | [Agentic-RAG-PRD.md](./Agentic-RAG-PRD.md) |
| 深圳科创检索增强智能体（模块三：查找论文） | papers 表 | [Agentic-RAG-PRD.md](./Agentic-RAG-PRD.md) |
| 深圳科创检索增强智能体（模块四：查找专利） | patents 表 | [Agentic-RAG-PRD.md](./Agentic-RAG-PRD.md) |
| 教授画像卡片展示 | professors + papers 关联查询 | [Agentic-RAG-PRD.md](./Agentic-RAG-PRD.md) |
| 企业画像卡片展示 | companies + patents 关联查询 | [Agentic-RAG-PRD.md](./Agentic-RAG-PRD.md) |
