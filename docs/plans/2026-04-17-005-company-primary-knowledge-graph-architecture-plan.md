---
title: Shenzhen Sci-Tech Knowledge Graph — Company-Primary Architecture and Refactor Plan
date: 2026-04-17
status: active
owner: claude
revisions:
  - 2026-04-17 initial draft
  - 2026-04-17 r2: 过度设计裁剪 + dashboard 补 Browse 场景 + professor 整合策略落实
supersedes:
  - docs/plans/2026-04-17-004-shenzhen-stem-knowledge-graph-retrieval-and-ops-architecture-plan.md
origin:
  - docs/plans/2026-04-17-004-shenzhen-stem-knowledge-graph-retrieval-and-ops-architecture-plan.md
  - docs/plans/2026-04-17-003-professor-stem-issue-closure-plan.md
  - docs/solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md
  - docs/Agentic-RAG-PRD.md
  - docs/Company-Data-Agent-PRD.md
  - docs/专辑项目导出1768807339.xlsx
  - docs/测试集答案.xlsx
---

# Shenzhen Sci-Tech Knowledge Graph — Company-Primary Architecture and Refactor Plan

> 本文档**取代** `2026-04-17-004-shenzhen-stem-knowledge-graph-...`。004 仍可查阅，但不再是执行目标。

## 0. 文档阅读指南

- 如果你是**第一次接触本项目**：从 §1 读到 §5，理解产品定位和离线/在线边界。
- 如果你要**写 crawler / cleaner / importer**：§6（Canonical Schema）是蓝图，每个字段明确了语义、允许来源、必填性。
- 如果你要**实施重构**：§9（代码重构方案）+ §10（迁移路径）是可执行单元。
- 如果你要**运营/审查数据**：§8（Dashboard 设计）。
- 如果你要**审阅战略**：§1 + §2 + §12（与 004 差异）。

---

## 1. 目标与定位（北极星）

**一句话**：以深圳科创企业为主域、教授作为精度补强、以离线证据图谱为核心价值、以在线检索作为新鲜度补丁的问答底座。

### 1.1 三层职责分离

| 层 | 能力 | 价值主张 |
|---|---|---|
| **离线证据图谱** | 稳定构建 company / professor / paper / patent 四域的 canonical facts、verified relations、受控 taxonomy | **核心壁垒**——别人反复在线 search 拼出来的，我们已经结构化存好 |
| **离线检索投影** | 从 canonical 派生 answer_pack、FTS 索引、向量索引 | 让智能体秒级回答 95% 基础问题 |
| **在线新鲜度补丁** | 针对时间敏感查询做一次 web search + LLM 整合，结果只进 citation 不进 canonical | 补覆盖，不拼事实 |

### 1.2 五个可测量目标

替代原 plan 里只有 `workbook-answerability` 一个测量目标的问题。每个都有量化指标：

1. **企业采集完整度**：xlsx batch 解析成功率 ≥ 99%；canonical company 数 / xlsx unique company 数 ≥ 99%
2. **企业新鲜度**：高优先级企业（top 200）近 14 天新闻覆盖率 ≥ 80%
3. **教授采集精度**：深圳 STEM 高校 targeted E2E 通过率 100%；professor_paper_link verified 召回率 ≥ 70%，误检率 ≤ 2%
4. **检索本地命中率**：真实 query 中 不触发 online_freshness_patch 就能完整作答的比例 ≥ 80%
5. **测试集答案.xlsx** 扩样 70 题（A–G 家族各 10 题）综合通过率 ≥ 75%，且每道失败题必须有结构化 `blocking_gap`

---

## 2. Non-Goals / Out of Scope（显式列出）

本次重构**明确不做**以下事项，加入后必须新建 plan：

1. ❌ 非深圳 STEM 高校教师发现（scope = 南科大、深圳大学、港中大深圳、哈工大深圳、清华深圳、中大深圳、北大深研院、深职大、深技大、其他明确列入的 STEM 院系）
2. ❌ paper-to-paper 引用图（只存 paper→person）
3. ❌ 实时（秒级/分钟级）新闻推送；高优先级日级、普通周级
4. ❌ 用户个性化、收藏、账户体系
5. ❌ 多轮迭代 web search（"搜完再搜"）；在线每 query 最多一次 search
6. ❌ 跨语言同名 alias resolution（只做 zh/en）
7. ❌ 非 Shenzhen 企业的批量采集（region 过滤：广东省-深圳市；允许异常样本进 needs_review）
8. ❌ 自动写回 canonical 的 agent 动作；任何 canonical 修改必须由离线 pipeline 或人工 verify
9. ❌ 历史数据考古（xlsx 早于当前 batch 的版本仅保留 snapshot 不建完整时间序列）
10. ❌ 商业用户授权/计费体系

---

## 3. 四层架构

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 4. Serving                                                 │
│  ─────────────────                                                │
│  主路径：offline canonical + answer_pack → agent answer          │
│  旁路：online_freshness_patch（独立 citation，不写回 canonical）  │
├──────────────────────────────────────────────────────────────────┤
│  Layer 3. Offline Projection                                      │
│  ──────────────────────                                           │
│  answer_pack (多态单表) / FTS / pgvector / 事件时间线视图         │
│  ← 只从 Layer 2 派生，不独立承载事实                              │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2. Offline Canonical Graph                                 │
│  ──────────────────────────────                                   │
│  Entities:  company(主) + professor(精) + paper + patent          │
│  Relations: verified/candidate/rejected 三态                      │
│  Taxonomy:  受控词表（industry、technology_route、data_route...）│
├──────────────────────────────────────────────────────────────────┤
│  Layer 1. Offline Source & Evidence                               │
│  ─────────────────────────────                                    │
│  seed: xlsx(主) + roster(精度) + company_official_site + news    │
│  lineage: import_batch + source_row_lineage + source_page        │
│  不包含：agent runtime 触发的 live search 结果                    │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Online Freshness Patch（旁路，不与 Canonical 共表）              │
│  只有 Serving 层调用；结果：                                      │
│   - 写 answer 的 live_citation                                    │
│   - 写 offline_enrichment_queue（下一轮离线消化 + verify）        │
└──────────────────────────────────────────────────────────────────┘
```

**关键变化（对比 004）**：在线路径从"fallback 写 candidate 经 verify promotion"改为"旁路增量，物理隔离"。消除了"live 写 canonical 候选→污染图谱"的风险。

---

## 4. 离线与在线的硬边界

这是本文档**最重要的产品主张**，必须写死不允许漂移。

### 4.1 离线职责

| 数据类型 | 来源 | 默认刷新 |
|---|---|---|
| 企业身份、工商、团队、融资维度 | `company_xlsx`（企名片专辑导出） | 有新 xlsx 到达时 |
| 企业官网信息、产品、技术路线 | `company_official_site` crawl | 每月 |
| 企业新闻与事件 | `company_news_feed`（RSS + 官网新闻页 + 权威媒体） | 高优先级日级，普通周级 |
| 教授身份与画像 | 高校官方 `roster` + `official_profile` | 每季度 |
| 教授 research topic / CV | `personal_homepage` / `cv_pdf` / `lab_homepage` | 每季度 |
| 教授论文关系 | `official_publication_page` / `cv_pdf` / academic API | 每月 |
| 专利 | `patent_xlsx` | 有新 xlsx 到达时 |
| Taxonomy 归类 | LLM 基于 canonical 抽取 + 受控词表 | 事实写入时 |

### 4.2 在线职责

**触发条件（必须满足其一）**：

1. Query 包含时间敏感 token：`最近` / `今天` / `本周` / `最新` / `刚` / `本月` / `昨天`
2. Retrieval Planner 判定命中的实体上一次相关事件已超过 SLA（例如公司融资问题，但 `company_signal_event.event_type=funding` 最新一条 > 30 天）
3. 查询类型为 PRD Type E（开放性知识问答，"具身智能有几种数据采集路线"）
4. 查询明确点名 offline 覆盖不全的外部实体（经 Retrieval Planner 判定 entity_lookup 失败且 query 明显是事实性问题）

**硬规则**：

| 规则 | 说明 |
|---|---|
| 只在 serving 层调用 | 离线 pipeline **不允许**调用 live search（避免 crawler 循环） |
| 每 query 最多一次 | 同一 query 不允许多轮反复 search |
| **结果绝不写 canonical 表** | `company` / `company_snapshot` / `company_fact` / `professor*` / `*_link` 全部禁止 |
| 可写两处 | ① answer 的 `live_citation` 字段（仅本次对话）② `offline_enrichment_queue`（供下一轮离线消化） |
| citation 标注 | 每条引用必须带 `source=live_web_search`、`fetched_at=T`、`cannot_be_verified_offline=true` |
| 不做基础信息 fallback | 问 "教授 X 是谁"、"公司 Y 做什么" 不触发 live search——基础信息缺失是离线采集的锅 |

### 4.3 在线→离线回写协议

```
user query
  ↓
Retrieval Planner 判定需要 freshness patch
  ↓
online_freshness_patch(query, scope_entity_id?) 
  ├─ web search (google/bing API) → top 5 results
  ├─ LLM 整合 results + canonical 片段 → answer 片段
  ├─ 写 answer.live_citations[]
  └─ 写 offline_enrichment_queue  
       (triggered_by_query, live_source_url, suggested_entity_type,
        suggested_entity_id?, suggested_fact_type, extracted_evidence_span)
  ↓
[下一轮离线 cycle]
Offline Enrichment Worker
  ├─ 读 offline_enrichment_queue (status=pending)
  ├─ 正常的 crawl + extract + identity resolution
  ├─ 走正常 verification 路径
  └─ 更新 queue.status = processed / rejected
```

这样保留了"用户立刻看到新答案"的体验，同时避免图谱被单次对话污染。

---

## 5. Seed 分类学

| seed_kind | scope_key 示例 | 发现什么 | 刷新 |
|---|---|---|---|
| `company_xlsx` | `qimingpian-shenzhen-2026-04` | company + snapshot + team_member raw | 每次新 xlsx |
| `patent_xlsx` | `patent-db-2025-12` | patent + applicants/inventors raw | 每次新 xlsx |
| `teacher_roster` | `sustech-faculty-cs` | professor 候选 + official_profile 入口 | 每季度 |
| `department_hub` | `sustech-cse-homepage` | roster 页面上游 | 每季度 |
| `company_official_site` | `company:{company_id}` | product / technology_route / contact | 每月 |
| `company_news_feed` | `company:{company_id}:news` | news_item → signal_event | 高优先级日级/普通周级 |

**重要**：`seed_registry` 是 ingestion 的唯一入口。所有 crawler / importer 都必须指向 `seed_id`，不允许硬编码 URL。

---

## 6. Canonical Schema（蓝图）

此节每张表都给出：**字段清单 + 语义 + 允许来源 + 必填 / 可空 / 默认值**。这是 crawler / cleaner / importer 的**直接蓝图**——字段存在，就意味着采集需要填；字段不存在，就不采集不清洗。

### 6.0 约定

- 主键：`{TYPE}-{12-char short hash}`，如 `COMP-a1b2c3d4e5f6`、`PROF-...`、`PAPER-...`、`PAT-...`
- 时间字段：`timestamptz`，默认 `now()`
- JSON 字段：`jsonb`
- 所有 `canonical_*` 表的每次写入必须同时写 `admin_audit_log`（如果是人工）或 `pipeline_run.run_id` 引用（如果是自动）
- **受控词表字段命名约定**：以 `_code` 结尾的字段必须 FK 到 `taxonomy_vocabulary.code`

### 6.1 Source Layer

#### `seed_registry`
```sql
seed_id              text PK
seed_kind            text NOT NULL   -- enum: company_xlsx | patent_xlsx | teacher_roster 
                                     --       | department_hub | company_official_site | company_news_feed
scope_key            text NOT NULL
source_uri           text NOT NULL   -- 对 xlsx 是 file path；对 roster 是 URL
priority             int NOT NULL DEFAULT 100
refresh_policy       text NOT NULL   -- enum: manual | daily | weekly | monthly | quarterly | on_batch
status               text NOT NULL DEFAULT 'active'  -- enum: active | paused | deprecated
last_processed_at    timestamptz
config               jsonb           -- kind-specific (e.g. 高校 roster 的 html 选择器配置)
created_at / updated_at timestamptz
UNIQUE (seed_kind, scope_key)
```
**采集蓝图作用**：任何 crawler 启动前必须先 upsert 这一行。发现"某高校 roster 没进 seed_registry"就意味着没人知道要抓它。

#### `import_batch`
```sql
batch_id             uuid PK
seed_id              text NOT NULL FK seed_registry
source_file          text NOT NULL       -- 绝对路径
file_content_hash    text NOT NULL       -- sha256(file)，用来判重
started_at           timestamptz NOT NULL
finished_at          timestamptz
rows_read            int
records_parsed       int
records_new          int                 -- 新建 canonical
records_updated      int                 -- 更新已有 canonical
records_merged       int                 -- 触发合并决策
records_failed       int
run_status           text NOT NULL       -- enum: running | succeeded | partial | failed | reverted
error_summary        jsonb
triggered_by         text                -- cron | manual | dependency
UNIQUE (seed_id, file_content_hash)      -- 同文件二次导入直接跳过
```

#### `source_row_lineage`
```sql
lineage_id           uuid PK
batch_id             uuid NOT NULL FK import_batch
source_row_number    int NOT NULL
target_entity_type   text NOT NULL       -- enum: company | patent | ...
target_entity_id     text                -- NULL 表示未解析或失败
resolution_status    text NOT NULL       -- enum: matched | created | merged | failed | skipped
resolution_reason    text
raw_row_jsonb        jsonb NOT NULL      -- 整行原始内容保留（审计 + 防 xlsx 格式漂移）
created_at
```
**采集蓝图作用**：用户问"这条数据从哪来"时，通过 `target_entity_id` 反查这里。`raw_row_jsonb` 保留原始值，让 cleaner 可以随时重跑。

#### `source_page`
```sql
page_id              uuid PK
url                  text NOT NULL UNIQUE
url_host             text GENERATED ALWAYS AS (lower(substring(url from '//([^/]+)')))
page_role            text NOT NULL       -- enum: roster_seed | department_hub | official_profile 
                                         --       | personal_homepage | lab_homepage 
                                         --       | official_publication_page | cv_pdf 
                                         --       | official_external_profile | company_official_site 
                                         --       | company_news_article | unknown
owner_scope_kind     text                -- enum: institution | department | professor | company | global
owner_scope_ref      text                -- e.g. professor_id / company_id / institution 名
fetched_at           timestamptz NOT NULL
http_status          int
content_hash         text                -- sha256(clean_text)
title                text
clean_text_path      text NOT NULL       -- 文件系统路径；不把全文塞 DB
is_official_source   bool NOT NULL DEFAULT false   -- 严格由 url_host allow-list 决定
fetch_run_id         uuid FK pipeline_run
created_at
```
**关键规则**：
- `page_role` 由 rule-based classifier 决定（URL 正则 + anchor text），不由 LLM 直接决定
- `is_official_source` 严格 allow-list：`.edu.cn`、`.gov.cn`、公司 canonical website 的 host → true；其他一律 false
- 防止 `https://www.sustech.edu.cn/zh/letter/` 被误当 `official_profile` 的硬机制

> **r2 裁剪**：原 §6.1 的 `page_link_candidate` 独立表已删除。现有 `professor/discovery.py` 的递归发现不依赖此表，多加一层只会增加维护成本。若将来确需记录递归决策，放 `pipeline_run.run_scope` jsonb 足够。

#### `pipeline_run`（合并 004 的四张 run 表）
```sql
run_id               uuid PK
run_kind             text NOT NULL       -- enum: import_xlsx | roster_crawl | profile_enrichment 
                                         --       | news_refresh | team_resolver 
                                         --       | paper_link_resolver | projection_build 
                                         --       | answer_readiness_eval | quality_scan
run_scope            jsonb NOT NULL      -- kind-specific，e.g. {"seed_id":"X"} 或 
                                         -- {"entity_type":"company","entity_ids":[...]}
seed_id              text FK seed_registry
parent_run_id        uuid FK pipeline_run
started_at           timestamptz NOT NULL
finished_at          timestamptz
status               text NOT NULL       -- enum: running | succeeded | partial | failed
items_processed      int
items_failed         int
error_summary        jsonb
triggered_by         text                -- cron | manual | dependency | upstream_run
created_at
```
**简化点**：所有异步任务共享一张表。dashboard 按 `run_kind` 过滤即可。

#### `offline_enrichment_queue` **[Phase 5+]**
```sql
-- 仅在 Phase 5 online_freshness_patch 实装时建表。Phase 0-4 不需要。
queue_id             uuid PK
triggered_by_query   text NOT NULL
triggered_by_user    text                -- 可空，微信用户不一定有 id
triggered_at         timestamptz NOT NULL
live_source_url      text NOT NULL
suggested_entity_type text
suggested_entity_id  text                -- 若能关联到现有 canonical
suggested_fact_type  text                -- 若是结构化事实
suggested_value      text
extracted_evidence_span text
status               text NOT NULL DEFAULT 'pending'  -- enum: pending | processing | processed | rejected | duplicate
processed_at / processed_by_run_id uuid FK pipeline_run
notes                text
```

### 6.2 Company Canonical（主域，直接映射 xlsx 42 列）

#### `company`
```sql
company_id           text PK              -- COMP-{12-char-hash(unified_credit_code | normalized_name)}
unified_credit_code  text UNIQUE          -- 统一社会信用代码；xlsx 没给但将来可补
canonical_name       text NOT NULL
registered_name      text                 -- xlsx 公司名称原值（繁简体、括号等可能和 canonical_name 不同）
aliases              text[] NOT NULL DEFAULT '{}'  -- 简称、英文名、历史名
website              text
website_host         text GENERATED ALWAYS AS (lower(...))  -- 用来和 source_page.url_host 对齐
hq_province          text
hq_city              text
hq_district          text
is_shenzhen          bool NOT NULL DEFAULT false
country              text NOT NULL DEFAULT '国内'
identity_status      text NOT NULL DEFAULT 'resolved'  -- enum: resolved | needs_review | merged_into | inactive
merged_into_id       text FK company (merged_into_id)  -- 若被合并
first_seen_batch_id  uuid FK import_batch
first_seen_at        timestamptz
last_refreshed_at    timestamptz
created_at / updated_at
```

#### `company_snapshot`（**核心：每次 xlsx 批次形成一条追加快照**）
```sql
snapshot_id          uuid PK
company_id           text NOT NULL FK company
import_batch_id      uuid NOT NULL FK import_batch
snapshot_kind        text NOT NULL        -- enum: xlsx_import | website_crawl
source_row_number    int                  -- 对 xlsx_import 必填

-- ===== 直接映射 xlsx 42 列 =====
-- 项目 / 行业
project_name         text                 -- [1] 项目名称
industry             text                 -- [2] 行业领域
sub_industry         text                 -- [3] 子领域
business             text                 -- [4] 业务
region               text                 -- [5] 地区 "广东省-深圳市"
description          text                 -- [15] 简介（长文本）
logo_url             text                 -- [16] Logo链接
star_rating          int                  -- [17] 星级
status_raw           text                 -- [18] 状态
remarks              text                 -- [19] 备注
is_high_tech         bool                 -- [14] 高新企业

-- 公司基础
company_name_xlsx    text NOT NULL        -- [20] 公司名称 (原值)
country_xlsx         text                 -- [21] 国别
established_date     date                 -- [22] 成立日期
years_established    int                  -- [29] 成立年限
website_xlsx         text                 -- [23] 网址
legal_representative text                  -- [24] 法人代表 (PII)
registered_address   text                  -- [26] 注册地址
registered_capital   text                  -- [13] 注册资金 (free-text，如 "100万人民币")
contact_phone        text                  -- [27] 企业联系电话 (PII — 受可见性控制)
contact_email        text                  -- [28] 联系邮箱 (PII — 受可见性控制)

-- 报告统计（均为 reported，不是 verified；作"xlsx 声称"保留）
reported_insured_count       int           -- [30] 参保人数
reported_shareholder_count   int           -- [31] 股东数
reported_investment_count    int           -- [32] 投资数
reported_patent_count        int           -- [33] 专利数
reported_trademark_count     int           -- [34] 商标数
reported_copyright_count     int           -- [35] 著作权
reported_recruitment_count   int           -- [36] 招聘数
reported_news_count          int           -- [37] 新闻数
reported_institution_count   int           -- [38] 机构方数量
reported_funding_round_count int           -- [39] 融资总次数
reported_total_funding_raw   text          -- [40] 融资总额 (free-text，如 "1900")
reported_valuation_raw       text          -- [41] 估值

-- 最近一轮融资（xlsx 每行记一轮最近的）
latest_funding_round      text             -- [6]  投资轮次
latest_funding_time_raw   text             -- [7]  投资时间 (原文 "2020.7.7" / "-")
latest_funding_time       date             -- 解析后
latest_funding_amount_raw text             -- [8]  投资金额 (free-text "数千万人民币")
latest_funding_cny_wan    numeric(20,2)    -- [9]  参考转化金额（万人民币）
latest_funding_ratio      text             -- [10] 比例
latest_investors_raw      text             -- [11] 投资方 (自由文本)
latest_fa_info            text             -- [12] FA信息

-- Raw 待解析字段
team_raw                  text             -- [25] 团队 (单独 parser)

snapshot_created_at       timestamptz NOT NULL DEFAULT now()
raw_row_jsonb             jsonb NOT NULL   -- 整行原始 snapshot 保留
```

**采集蓝图作用**：
1. importer 必须对齐这 42 个字段。缺字段 = bug。
2. 不允许"覆盖写 company"——company 表只有身份核心，其他都在 snapshot 里追加。
3. `reported_*` 字段与我们自己 verify 得到的字段**物理分离**（后者在 `company_fact` / `company_patent_link` / `company_news_item` 里）。

#### `company_team_member`（从 team_raw 抽出，**不自动升 person**）
```sql
member_id            uuid PK
company_id           text NOT NULL FK company
snapshot_id          uuid NOT NULL FK company_snapshot
member_order         int NOT NULL            -- 原 xlsx 里顺序
raw_name             text NOT NULL           -- 如 "王博洋"
raw_role             text                    -- 如 "CEO&联合创始人"
raw_intro            text                    -- 如 "王博洋，旭宏医疗CEO&联合创始人。"
normalized_name      text                    -- 标准化后（全角→半角、去空格）
resolution_status    text NOT NULL DEFAULT 'unresolved'
                                             -- enum: unresolved | candidate | matched | rejected
resolved_professor_id text FK professor       -- 解析成功才填
resolution_confidence numeric(3,2)
resolution_reason    text
resolution_evidence  jsonb                   -- e.g. {"match_kind":"exact_name_same_inst", "page_id":"..."}
resolved_at          timestamptz
created_at
```
**核心规则**：
- 每个 xlsx 团队条目都建一行 `company_team_member`，无论后续是否能连上 professor
- 单独的离线 `team_resolver` job 扫这张表，只在高置信匹配上 professor 时才升格 `resolved_professor_id` 并建 `professor_company_role`
- **80% 的团队成员预期保持 `unresolved` 状态**——他们本来就不是深圳 STEM 教授

> **r2 裁剪**：原 `company_official_page_ref` 小表已删除。company 与 source_page 的关联通过 `source_page.owner_scope_kind='company'` + `owner_scope_ref=company_id` 表达即可，无需加一张连接表。page_kind 细分（homepage / about_us / product_page 等）放在 `source_page.page_role` 枚举里扩展。

#### `company_fact`（结构化事实，**强制用受控词表**）
```sql
fact_id              uuid PK
company_id           text NOT NULL FK company
fact_type            text NOT NULL           -- enum: industry_tag | product_tag | technology_route 
                                             --       | data_route_type | real_data_method 
                                             --       | synthetic_data_method | movement_data_need 
                                             --       | operation_data_need | customer_type 
                                             --       | founder_background | business_model | certification
value_raw            text                    -- LLM 抽取原文
value_code           text FK taxonomy_vocabulary   -- ⚠ 必须映射到受控词，否则 status=pending_taxonomy
status               text NOT NULL DEFAULT 'active'  -- enum: active | pending_taxonomy | deprecated | superseded
source_kind          text NOT NULL           -- enum: xlsx | official_website | news | llm_from_official | human_reviewed
source_ref           text NOT NULL           -- snapshot_id / page_id / news_id / audit_log_id
confidence           numeric(3,2) NOT NULL
evidence_span        text                    -- 原文摘录
created_at / updated_at
```
**硬规则**：`value_code` 为空的 fact 不进 `company_answer_pack`；这样保证查询 "深圳做服务机器人的公司" 的过滤不被自由文本污染。

#### `company_news_item`
```sql
news_id              uuid PK
company_id           text NOT NULL FK company
source_page_id       uuid FK source_page
source_url           text NOT NULL UNIQUE
source_domain        text NOT NULL
source_domain_tier   int NOT NULL            -- 1-5，从 source_domain_tier_registry
published_at         timestamptz
fetched_at           timestamptz NOT NULL
title                text NOT NULL
summary_clean        text                    -- LLM 生成 ≤ 200 字
content_clean_path   text                    -- 全文在文件系统
is_company_confirmed bool NOT NULL DEFAULT false   -- title/content 是否明确点名公司（非"同名猜测"）
refresh_run_id       uuid FK pipeline_run
confidence           numeric(3,2) NOT NULL
created_at
```

#### `company_signal_event`
```sql
event_id             uuid PK
company_id           text NOT NULL FK company
primary_news_id      uuid FK company_news_item
event_type           text NOT NULL           -- enum: funding | product_launch | partnership | policy 
                                             --       | hiring | order | patent_grant | award 
                                             --       | expansion | executive_change
event_date           date NOT NULL
event_subject_normalized jsonb NOT NULL      -- 结构化 payload，按 event_type schema
                                             -- funding: {round, amount_cny_wan, lead_investor, other_investors[]}
                                             -- product_launch: {product_name_code, version}
                                             -- executive_change: {person_raw, role, direction (joined|departed)}
event_summary        text NOT NULL           -- ≤ 80 字短描述
confidence           numeric(3,2) NOT NULL
corroborating_news_ids uuid[] NOT NULL DEFAULT '{}'  -- 多源印证
dedup_key            text NOT NULL           -- f(company_id, event_type, event_subject_normalized, 
                                             --   date_trunc by event_type)
status               text NOT NULL DEFAULT 'active'  -- enum: active | deprecated | deduped_into
deduped_into_id      uuid FK company_signal_event
UNIQUE (company_id, event_type, dedup_key)
```
**dedup_key 规则**（取代 004 的未定义 `normalized_subject`）：
- `funding` → `hash(round || amount_cny_wan_rounded || ± 14 days window)`
- `product_launch` → `hash(product_name_code || ± 7 days)`
- `partnership` → `hash(partner_company_id_or_name_code || ± 7 days)`
- ... 每个 type 一个明确公式

### 6.3 Professor Canonical（精度域，限定深圳 STEM）

#### `professor`
```sql
professor_id         text PK              -- PROF-{hash(canonical_name || primary_affiliation)}
canonical_name       text NOT NULL
canonical_name_en    text
aliases              text[] NOT NULL DEFAULT '{}'
discipline_family    text NOT NULL        -- enum: computer_science | electrical_engineering 
                                          --       | mechanical_engineering | materials 
                                          --       | biomedical | mathematics | physics | chemistry 
                                          --       | interdisciplinary | other
primary_official_profile_page_id uuid FK source_page
identity_status      text NOT NULL DEFAULT 'resolved'
merged_into_id       text FK professor
first_seen_at / last_refreshed_at / created_at / updated_at
```

**关键约束**：
- `primary_official_profile_page_id` 必填且必须是 `source_page.page_role='official_profile'` 且 `is_official_source=true`
- 没有这个锚点的 professor 不能 `identity_status='resolved'`

#### `professor_affiliation`
```sql
affiliation_id       uuid PK
professor_id         text NOT NULL FK professor
institution          text NOT NULL         -- 规范：南方科技大学、深圳大学、... (校名白名单)
department           text
title                text                  -- 教授 / 副教授 / 助理教授 / 讲师 / 研究员 / 访问学者
employment_type      text                  -- full_time | visiting | emeritus | joint_appointment
is_primary           bool NOT NULL DEFAULT false
is_current           bool NOT NULL DEFAULT true
start_year           int
end_year             int
source_page_id       uuid NOT NULL FK source_page
created_at / updated_at
```
**规则**：
- 一个 professor 可有多条 affiliation（多校任职）
- 每次 roster refresh 必须重新计算 `is_current`：本次 refresh 的 roster 里有 → true，没有 → false（但不删历史行）
- `is_primary` 规则：高校官方把此人列为专职 → primary=true；访问 / 兼职 → primary=false

#### `professor_fact`
```sql
fact_id              uuid PK
professor_id         text NOT NULL FK professor
fact_type            text NOT NULL         -- enum: research_topic | education | work_experience 
                                           --       | award | academic_position | contact 
                                           --       | homepage | external_profile | publication_count_reported
value_raw            text NOT NULL
value_normalized     text
value_code           text FK taxonomy_vocabulary   -- 仅 research_topic 用
source_page_id       uuid NOT NULL FK source_page
evidence_span        text NOT NULL         -- 原文摘录
confidence           numeric(3,2) NOT NULL
status               text NOT NULL DEFAULT 'active'
created_at / updated_at
```
**重点**：每条 fact 必须指向一个 `source_page`，没 source 的 fact 不准存。

### 6.4 Paper / Patent

#### `paper`
```sql
paper_id             text PK              -- PAPER-{hash(doi | openalex_id | normalize(title)+year)}
title_clean          text NOT NULL        -- 主显示字段
title_raw            text                 -- 审计用；可含 MathML / HTML
doi                  text UNIQUE
arxiv_id             text
openalex_id          text
semantic_scholar_id  text
year                 int
venue                text
abstract_clean       text
authors_display      text                 -- "张三, 李四, ..."
authors_raw          jsonb                -- 原始结构化 authors 数组
citation_count       int
canonical_source     text NOT NULL        -- enum: openalex | semantic_scholar | crossref | official_page | manual
first_seen_at / updated_at
```

#### `patent`
```sql
patent_id            text PK              -- PAT-{hash(patent_number)}
patent_number        text UNIQUE NOT NULL
title_clean          text NOT NULL
title_raw            text
title_en             text
applicants_raw       text                 -- 原文 (多人用 ; 分隔)
applicants_parsed    jsonb                -- [{name, parsed_role, matched_company_id?}]
inventors_raw        text
inventors_parsed     jsonb                -- [{name, parsed_affiliation?, matched_professor_id?}]
filing_date          date
publication_date     date
grant_date           date
patent_type          text                 -- enum: 发明 | 实用新型 | 外观 | PCT
status               text
abstract_clean       text
technology_effect    text
ipc_codes            text[] NOT NULL DEFAULT '{}'
first_seen_at / updated_at
```

### 6.5 Verified Relation Layer

#### `professor_paper_link`（**废弃 `PaperRecord.professor_ids`**）
```sql
link_id              uuid PK
professor_id         text NOT NULL FK professor
paper_id             text NOT NULL FK paper
link_status          text NOT NULL DEFAULT 'candidate'  -- enum: verified | candidate | rejected
evidence_source_type text NOT NULL       -- enum: official_publication_page | personal_homepage 
                                         --       | cv_pdf | official_external_profile 
                                         --       | academic_api_with_affiliation_match
evidence_page_id     uuid FK source_page
evidence_api_source  text                -- e.g. "openalex:W12345"
match_reason         text NOT NULL
author_name_match_score       numeric(3,2) NOT NULL
topic_consistency_score       numeric(3,2)
institution_consistency_score numeric(3,2)
is_officially_listed bool NOT NULL DEFAULT false   -- 是否出现在官方 publication_page
verified_by          text                -- enum: rule_auto | llm_auto | rule_and_llm 
                                         --       | human_reviewed | xlsx_anchored
verified_at          timestamptz
rejected_at          timestamptz
rejected_reason      text
created_at / updated_at
UNIQUE (professor_id, paper_id)
```

**Promotion 规则**（硬写死）：
```
candidate → verified 要求同时满足：
  1. evidence_source_type ∈ {official_publication_page, personal_homepage, cv_pdf, official_external_profile}
     或 (academic_api_with_affiliation_match 且 institution_consistency_score ≥ 0.9)
  2. author_name_match_score ≥ 0.85
  3. topic_consistency_score ≥ 0.5 (或 NULL 但 evidence 为 official_*)
  4. 无 institution 冲突 (conflict → 不自动 verify)
否则保持 candidate，或进入 needs_review 队列
```

#### `professor_company_role`（**只存强角色，不存一般雇员**）
```sql
role_id              uuid PK
professor_id         text NOT NULL FK professor
company_id           text NOT NULL FK company
role_type            text NOT NULL        -- enum: founder | cofounder | chief_scientist 
                                          --       | advisor | board_member
link_status          text NOT NULL DEFAULT 'candidate'
evidence_source_type text NOT NULL        -- enum: company_official_site | professor_official_profile 
                                          --       | trusted_media | xlsx_team_with_explicit_role 
                                          --       | gov_registry
evidence_url         text NOT NULL
evidence_page_id     uuid FK source_page
match_reason         text NOT NULL
source_ref           text
verified_by          text
start_year           int
end_year             int
is_current           bool
verified_at / rejected_at / rejected_reason
created_at / updated_at
UNIQUE (professor_id, company_id, role_type)
```
**注意**：一般雇员关系不建行，保留在 `company_team_member.resolved_professor_id`（无 role_type）即可。

#### `professor_patent_link`
```sql
link_id              uuid PK
professor_id         text NOT NULL FK professor
patent_id            text NOT NULL FK patent
link_role            text NOT NULL        -- enum: inventor | applicant_represented_person
link_status          text NOT NULL DEFAULT 'candidate'
evidence_source_type text NOT NULL        -- enum: patent_xlsx_inventor_match 
                                          --       | company_official_site | personal_homepage
match_reason         text
verified_by          text
verified_at
UNIQUE (professor_id, patent_id, link_role)
```

#### `company_patent_link`
```sql
link_id              uuid PK
company_id           text NOT NULL FK company
patent_id            text NOT NULL FK patent
link_role            text NOT NULL        -- enum: applicant | assignee
link_status          text NOT NULL DEFAULT 'candidate'
evidence_source_type text NOT NULL        -- enum: patent_xlsx_applicant_exact_match 
                                          --       | patent_xlsx_applicant_normalized_match 
                                          --       | gov_registry | company_official_site
match_reason         text
verified_by          text
verified_at
UNIQUE (company_id, patent_id, link_role)
```

> **r2 裁剪**：原 `entity_merge_decision` 独立表已删除。所有合并/拆分决策通过 `admin_audit_log` 承载：
> - `action = 'merge_entity'` 或 `'split_entity'`
> - `entity_type` / `entity_id` = winner
> - `before` / `after` jsonb 放 loser_id、decision_reason_code、evidence_refs、actor 等
>
> 若 Phase 5+ 发现 audit log 查询不便（比如要做"某公司被哪些别名合并过"的交叉查询），再抽独立表。初期一张表够。

### 6.6 Projection Layer（投影）

#### `answer_pack`（**多态单表**，取代 004 的 4 张独立 pack 表）
```sql
-- Phase 1 最小字段集
pack_id              uuid PK
entity_type          text NOT NULL        -- enum: company | professor | paper | patent
entity_id            text NOT NULL
body                 jsonb NOT NULL       -- 按 entity_type schema，详见下
evidence_summary     jsonb NOT NULL       -- {source_counts_by_kind, total_evidence, freshest_at, oldest_at}
freshness            jsonb NOT NULL       -- {last_canonical_change_at, last_news_at, is_stale, staleness_reason}
built_at             timestamptz NOT NULL
projection_version   int NOT NULL
UNIQUE (entity_type, entity_id)

-- Phase 2+ 追加（按需启用）：
-- fts_text             text GENERATED   -- 中文 FTS；Phase 2b 决策 zhparser 部署后启用
-- fts                  tsvector GENERATED ALWAYS AS (to_tsvector('chinese_zhparser', fts_text)) STORED
-- embedding            vector(1024)     -- pgvector；Phase 2b ADR 决策 embedding 模型后启用
-- INDEX gin(fts)
-- INDEX hnsw(embedding vector_cosine_ops)
```

> **r2 裁剪**：Phase 1-2a 只做 `body jsonb` 查询（`body->>'canonical_name' ILIKE '%xxx%'` + `body @> '{...}'` 已能覆盖 entity_lookup + graph_traversal 两种 MVP 检索）。FTS 和 embedding 等到 Phase 2b 补齐——届时有真实 query miss 分布可指导中文分词器和 embedding 模型选型。

**`body` 按类型的 schema**：

```
company.body = {
  canonical_name, aliases, website, hq_city, is_shenzhen,
  industry_primary, industry_tags: [code], 
  product_tags: [code], technology_routes: [code],
  data_route_tags: [code],
  description_summary,            // LLM 从 xlsx description 生成 ≤200 字
  technology_route_narrative,     // LLM 从 company_fact 生成 ≤300 字
  evaluation_synthesis: {          // 取代废弃的 evaluation_summary 字段，显式声明是派生
    text,                          // LLM 从 canonical facts 合成
    sources: [fact_id, ...],       // 引用依据
    generated_at
  },
  linked_professors_verified: [{professor_id, canonical_name, role_type, evidence_url}],
  patents_verified_top: [{patent_id, patent_number, title_clean, year}],
  funding: {
    latest: {...}, 
    events_timeline: [{event_id, event_type, event_date, event_summary}]  // top 10
  },
  team_display: [{raw_name, raw_role, resolved_professor_id?}]
}

professor.body = {
  canonical_name, canonical_name_en, aliases, discipline_family,
  current_affiliation: {institution, department, title},
  all_affiliations: [...],
  research_topics: [{value_normalized, value_code?, evidence_page_id}],
  education: [...], work_experience: [...], awards: [...],
  verified_paper_count,                    // 不做 reported 声称
  verified_papers_top: [{paper_id, title_clean, year, venue, citation_count}],  // top 20
  verified_company_roles: [{company_id, canonical_name, role_type}],
  verified_patents_top: [{patent_id, patent_number}],                             // top 10
  bio_synthesis: { text, sources, generated_at }
}

paper.body = {
  title_clean, authors_display, venue, year, doi, arxiv_id,
  abstract_clean,
  linked_professors_verified: [{professor_id, canonical_name}]
}

patent.body = {
  patent_number, title_clean, filing_date, grant_date, patent_type,
  applicants_parsed, inventors_parsed,
  linked_company: {company_id, canonical_name},
  linked_professors_verified: [...]
}
```

### 6.7 Quality & Ops

> **r2 裁剪**：原 `data_quality_rule` 独立表已删除。规则以代码形式存在 `data_agents/quality/rules/R00X_*.py`，每条规则一个 Python 模块，暴露 `rule_id`、`name`、`severity`、`run(store) -> list[Issue]`。Phase 6 规则数超 15 条再考虑抽表（那时管理员可能要在 dashboard 里改规则配置）。

#### `data_quality_issue`
```sql
issue_id             uuid PK
rule_id              text NOT NULL         -- 对应 data_agents/quality/rules/ 模块 id（字符串自描述，无 FK）
rule_name            text NOT NULL         -- 冗余，方便 dashboard 展示
entity_type          text
entity_id            text
severity             text NOT NULL         -- enum: low | medium | high | critical
status               text NOT NULL DEFAULT 'open'   -- enum: open | acknowledged | resolved | ignored
evidence             jsonb NOT NULL
detected_at          timestamptz NOT NULL
detected_by_run_id   uuid FK pipeline_run
acknowledged_at / acknowledged_by
resolved_at / resolved_by / resolution_note
```

#### `answer_readiness_eval` **[Phase 5+]**
```sql
-- 仅在 Phase 5 answer_pack 和 retrieval planner 上线后建表。
eval_id              uuid PK
run_id               uuid NOT NULL FK pipeline_run
question_family      text NOT NULL        -- enum: A | B | C | D | E | F | G
question_id          text NOT NULL        -- 测试集 id 或 sample id
question_text        text NOT NULL
expected_answer      text
is_answerable        bool NOT NULL
blocking_gap         text                 -- enum: MISSING_ENTITY | MISSING_VERIFIED_RELATION 
                                          --       | STALE_NEWS | MISSING_TAXONOMY_TAG 
                                          --       | LOW_CONFIDENCE_ANSWER | NO_MATCHING_PROJECTION 
                                          --       | OUT_OF_SCOPE | OTHER
gap_evidence         jsonb
actual_answer_summary text
evaluated_at         timestamptz NOT NULL
UNIQUE (run_id, question_id)
```

#### `admin_audit_log`
```sql
log_id               uuid PK
user_id              text NOT NULL
action               text NOT NULL        -- enum: verify_link | reject_link | edit_fact 
                                          --       | trigger_rerun | merge_entity | split_entity 
                                          --       | ignore_issue | approve_batch | reject_batch
entity_type          text
entity_id            text
before               jsonb
after                jsonb
note                 text
timestamp            timestamptz NOT NULL DEFAULT now()
```

#### `taxonomy_vocabulary`（受控词表）
```sql
code                 text PK              -- 形如 "industry:robotics.service" / "data_route:real_world_collection"
namespace            text NOT NULL        -- industry | data_route | technology_route | ...
display_name         text NOT NULL
display_name_en      text
parent_code          text FK taxonomy_vocabulary
description          text
status               text NOT NULL DEFAULT 'active'
created_at / updated_at
```
**初始种子**：见 §11 附录 B。

#### `source_domain_tier_registry`
```sql
domain               text PK              -- e.g. "36kr.com", "sustech.edu.cn"
tier                 text NOT NULL        -- enum: official | trusted | unknown (3 档起步)
tier_reason          text
is_official_for_scope text                -- 若是 edu/gov，这里标 "official_for_institution_profile"
last_reviewed_at     timestamptz
```
**初始种子**：见 §11 附录 C。

> **r2 裁剪**：tier 从 5 档简化为 3 档（`official` / `trusted` / `unknown`）。5 档粒度（权威媒体/科技媒体/聚合器）在没有真实新闻数据时是臆测；等 Phase 2 积累若干批 news 后再按运维信号判断是否细分。

---

## 7. 检索架构

### 7.1 查询规划器（Retrieval Planner）

```
Query Understanding
  ├─ 实体词提取（NER + exact match against aliases）
  ├─ 查询类型分类（基于关键词规则 + 兜底 LLM）
  │    → PRD Type A / B / C / D / E / F / G
  └─ Freshness signal 检测（时间敏感 token 或事件查询）

→ Retrieval Plan:
  - entity_lookup (exact/alias/normalized/DOI/patent_number/website_host)
  - graph_traversal (沿 verified relation 展开 top-K)
  - lexical_search (FTS on answer_pack.fts_text)   [Phase 2+]
  - semantic_search (pgvector on answer_pack.embedding)   [Phase 2+]
  - event_timeline_query (company_signal_event 时间窗)   [Phase 2+]
  - online_freshness_patch (Phase 2+，见 §4.3)
```

### 7.2 MVP（Phase 1-2 仅实装）

- **entity_lookup**：90% 的 Type A 查询走这条
- **graph_traversal**：深度 1-2 跳的 Type C/D 查询

其他模式按数据和 query 反馈再加。

### 7.3 Answer Assembly

```
AnswerAssembler(query, retrieved_entities, freshness_patches) -> Answer
  - 先从 answer_pack 组装主答案
  - 按需从 canonical_facts / relations 补充
  - freshness_patches 作为独立段落附上（带明显的 "截至 T 从网络检索" 标注）
  - Citation Builder 汇总所有 source_ref
```

---

## 8. Dashboard 设计

### 8.1 双重定位

Dashboard 同时服务两类使用场景，不能偏废任一：

| 场景 | 谁 | 什么时候 | 典型问题 |
|---|---|---|---|
| **A. 数据浏览**（继承当前 web 控制台） | 产品、BD、内部用户 | 任何时候 | "我们库里有哪些机器人公司"、"云鲸智能长啥样"、"深圳 STEM 教授都有谁" |
| **B. 质量管控** | 运营/管理员 | 每日早 + 异常触发 | "昨夜有什么失败"、"这批 xlsx 进得对不对"、"哪些待审要我处理" |

**共用的组件**：Entity Detail 页。场景 A 进入默认看数据，场景 B 进入高亮问题。

### 8.2 四工作流 + 顶层导航

```
┌──────────────────────────────────────────────────────────────┐
│ [首页]  [数据]  [监控]              [🔍 全局搜索]   [👤 user] │
└──────────────────────────────────────────────────────────────┘
```

| Workflow | 路由 | 用途 |
|---|---|---|
| **W1 Home** | `/` | 首页告警卡 + 7 天活动时间线（场景 B 入口） |
| **W2 Data Browser** | `/data/{type}` + `/data/{type}/{id}` | 按域浏览列表、进入实体详情（场景 A 主入口，**继承当前 DomainList + RecordDetail**） |
| **W3 Monitor** | `/monitor/*` | 5 个 tab：Ingestion / Pipelines / Freshness / Anomaly / Readiness（场景 B 深入） |
| **W4 Entity Detail** | `/data/{type}/{id}` 或 `/entity/{type}/{id}` | 单实体三栏视图，W1/W2/W3 共用 |

### 8.3 W1 Home（场景 B 入口）

顶部 **4 张告警卡**（数字可点击入口，不是装饰）：

```
┌───────────────┬────────────────┬──────────────┬──────────────┐
│ 📥 待审 Batch │ 🔗 待审关系     │ ⚠ 采集异常   │ 🐛 质量告警   │
│  3 个新 batch │  47 个 candidate│  2 个 run 失败│ 5 个 anomaly │
│  12 合并冲突 │  link 等确认    │ (昨夜 02:14) │ 规则命中     │
└───────────────┴────────────────┴──────────────┴──────────────┘
```

**中部活动时间线**（最近 7 天）：按时间倒序显示
- xlsx batch 导入（+N 公司、±M 字段变化）
- 计划任务运行（professor enrichment / news refresh / projection rebuild）
- 管理员动作（谁手动 verify 了哪条关系、哪次合并）

**底部快速面板**：
- 今日测试集答案.xlsx 跑通情况（通过率、失败 question list）[Phase 5+]
- 本周 online_freshness_patch 调用次数（调用多说明离线有缺口）[Phase 5+]

### 8.4 W2 Data Browser（场景 A 主入口，**继承当前 web 控制台**）

这是现在 web 控制台**已经在做并且要继续做好**的部分——让人**自然地浏览离线收集到的数据**。

**路由**：

```
/data/companies              → 公司列表
/data/companies/{id}         → 公司详情（跳 W4）
/data/professors             → 教授列表
/data/professors/{id}
/data/papers                 → 论文列表
/data/papers/{id}
/data/patents                → 专利列表
/data/patents/{id}
```

**列表页** 设计（以 /data/companies 示例，继承当前 DomainList 能力但增强）：

```
┌────────────────────────────────────────────────────────────────┐
│ 公司 (1025 家，近 7 天新增 0)             [⚙列设置] [📥导出]   │
├────────────────────────────────────────────────────────────────┤
│ 搜索: [_______________]  行业: [全部 ▾]  区域: [深圳 ▾]        │
│ 高新: [全部 ▾]  新鲜度: [< 14 天 ▾]  质量: [✓ ready ▾]        │
├────────────────────────────────────────────────────────────────┤
│ 名称            行业        融资轮次  新闻(30d) 问题 最后更新  │
│ ─────────────────────────────────────────────────────────── │
│ 云鲸智能        服务机器人  A 轮     5          -   2d 前     │
│ 旭宏医疗        医疗健康    A 轮     2          1⚠  5d 前     │
│ 极智视觉        VR/AR       未披露   0          -   7d 前     │
│ ...                                                           │
│ [← 1 2 3 ... 21 →]                                            │
└────────────────────────────────────────────────────────────────┘
```

**与当前 DomainList 的差异**：
- ➕ 多维过滤（行业 / 区域 / 高新 / 新鲜度 / 质量）
- ➕ "问题" 列（命中 `data_quality_issue.status='open'` 的计数）→ 直接跳到问题详情
- ➕ "新鲜度" 列（近 N 天是否有 news / canonical 变动）
- ➕ 列设置 + 导出
- ✅ 保留：按列排序、分页、跳转详情
- ✅ 保留：原 PATCH 编辑能力（在 Phase 6+ 引入 auth 后按角色开放）

### 8.5 W3 Monitor（场景 B 深入）

5 个 tab，**角色与 §8.4 完全不同**——这里是"为什么数据会是这样"：

- **Tab 1 — Ingestion**：xlsx batch 列表 + 点入看 **Diff View**（按字段聚合变化）
- **Tab 2 — Pipelines**：最近 `pipeline_run`，按 `run_kind` 过滤；点入看失败 stack trace + 受影响实体
- **Tab 3 — Freshness**：按 stale 程度排序的实体列表；可一键触发 refresh
- **Tab 4 — Anomaly**：命中规则的实体/关系列表；可 acknowledge / ignore / drill-down
- **Tab 5 — Query Readiness** [Phase 5+]：测试集 + 采样真实 query 的 retrieval 日跑结果，失败题显示 `blocking_gap`

### 8.6 W4 Entity Detail（三栏共用页）

**进入路径**：
- 浏览场景 → W2 列表点击 → 默认 Canonical + Relations 展开，Quality 折叠
- 质量场景 → W1 告警 deeplink → Quality 展开并滚动定位到对应 issue

**页面结构**（和之前敲定的一致）：

```
╔════════════════════════════════════════════════════════════════╗
║ 🏢 深圳云鲸智能科技有限公司  [canonical]  quality: ✓ ready     ║
╠══════════╦═══════════════════════╦═════════════════════════════╣
║ 身份      ║ 字段 + 证据           ║ 关系                          ║
║ 工商码..  ║ 行业: "服务机器人"    ║ ✓ verified (12)              ║
║ 官网..    ║  源: 企名片 2026-04  ║   └ 专利:  3 件              ║
║ 规模..    ║  置信度: 0.95        ║   └ 关联教授: 张三(SUSTech)   ║
║          ║ 技术路线: "SLAM 导航" ║ ? candidate (5)              ║
║          ║  源: 官网 /tech/     ║   └ 新闻提到创始人 X         ║
║          ║  原文: "..."         ║ ✗ rejected (2)               ║
╠══════════╩═══════════════════════╩═════════════════════════════╣
║ 团队: 5 名未连人（3 已连 professor, 2 仅 xlsx 记录）            ║
║ 新闻事件: 23 条 / 最近 2026-04-15 (融资)  [查看时间线]           ║
║ 质量: 1 条 anomaly  [忽略] [标冲突]                              ║
║ 操作历史: [2026-04-14 lxiang verify professor_company_role]     ║
╚══════════════════════════════════════════════════════════════════╝
```

### 8.7 四个关键支撑组件

1. **Evidence Viewer** — 每条 fact / relation 旁必带：`源 URL` + `page_role` + `抓取时间` + `原文 span` + `置信度`。没这个组件"对不对"只能靠猜
2. **Diff View** — batch 到达时按**字段**聚合变化（industry 本次变 8 条、team 变 7 条），不是按行聚合 count
3. **Anomaly Rules** — 规则以代码形式存在 `data_agents/quality/rules/`（每条一个 `.py`），命中结果落 `data_quality_issue`；W3 Tab 4 按 rule_id 聚合显示
4. **Query Readiness Monitor** [Phase 5+] — 每日对测试集 + 采样真实 query 自动跑 retrieval，失败题给结构化 `blocking_gap` 枚举

### 8.8 完整路由清单

```
/                             → W1 Home（告警 + 活动时间线）
/data/companies               → W2 列表（场景 A 默认落地）
/data/companies/{id}          → W4 Entity Detail
/data/professors              → W2
/data/professors/{id}         → W4
/data/papers                  → W2
/data/papers/{id}             → W4
/data/patents                 → W2
/data/patents/{id}            → W4
/monitor/ingestion            → W3 Tab 1
/monitor/pipelines            → W3 Tab 2
/monitor/freshness            → W3 Tab 3
/monitor/anomaly              → W3 Tab 4
/monitor/readiness            → W3 Tab 5 [Phase 5+]

-- 全局搜索跨 type：
/search?q=...&type=...        → W2 结果页（多 type 混合）
```

---

## 9. 代码重构详细方案（file-level）

### 9.1 总体原则

1. **不立即删旧代码**。每个旧文件加 header 注释 `# LEGACY: compat-only until §10 cutover`，不改其行为，仅做 feature-flag 关停
2. **新写独立目录**，旧新并存一段时间
3. **数据库新库**，旧 SQLite 继续承载旧 released_objects 读路径直到 Phase 5 cutover
4. **每个模块有 repo.py + models.py 分离**：models 是 Pydantic；repo 是 DB 访问
5. **教授采集代码 0 改动**（r2 新增）：discovery / enrichment / name_selection / paper_collector / cross_domain_linker 完全保留。只在 release 阶段接 canonical_writer。这是 Phase 3 的硬约束
6. **不做 StorageEngine 抽象**（r2 裁剪）：直接写 `PostgresStore` 类。若 Phase 6+ 真需要 mock 或多后端适配，届时抽。初期多一层抽象只会增加 indirection

### 9.2 `apps/miroflow-agent/src/data_agents/` 目录重组

```
data_agents/
├── contracts/                  ← 新：替换旧 contracts.py 单文件
│   ├── __init__.py             (re-export)
│   ├── common.py               (Evidence, Enums, QualityStatus — 从旧 contracts 搬)
│   ├── company.py              (Company, CompanySnapshot, CompanyTeamMemberRaw, CompanyFact, ...)
│   ├── professor.py            (Professor, ProfessorAffiliation, ProfessorFact)
│   ├── paper.py
│   ├── patent.py
│   ├── relations.py            (ProfessorPaperLink, ProfessorCompanyRole, ...)
│   ├── projection.py           (AnswerPackBody* 按 entity_type)
│   └── quality.py              (DataQualityRule, DataQualityIssue, AuditLog)
│
├── storage/
│   ├── engine.py               ← 新：StorageEngine Protocol
│   ├── postgres/               ← 新：本次重构的落点
│   │   ├── __init__.py
│   │   ├── connection.py       (asyncpg/psycopg3 connection pool factory)
│   │   ├── company_repo.py
│   │   ├── professor_repo.py
│   │   ├── paper_repo.py
│   │   ├── patent_repo.py
│   │   ├── relation_repo.py
│   │   ├── source_repo.py      (seed_registry, import_batch, source_page, lineage)
│   │   ├── projection_repo.py  (answer_pack)
│   │   ├── quality_repo.py
│   │   └── schema/
│   │       ├── V001_init_source.sql
│   │       ├── V002_init_company.sql
│   │       ├── V003_init_professor.sql
│   │       ├── V004_init_paper_patent.sql
│   │       ├── V005_init_relations.sql
│   │       ├── V006_init_projection.sql
│   │       └── V007_init_quality.sql
│   ├── sqlite_store.py         ← 现有，header 加 LEGACY 注释
│   └── milvus_store.py         ← 现有，header 加 LEGACY；Phase 5 退役
│
├── seed/                       ← 新：统一的 seed 管理
│   ├── registry.py
│   └── triggers.py             (batch 触发 / manual trigger / cron hookup)
│
├── company/
│   ├── import_xlsx.py          ← 重写：见 §9.3
│   ├── team_parser.py          ← 新：解析 team_raw
│   ├── team_resolver.py        ← 新：team_member → professor 离线 job
│   ├── official_site_crawler.py ← 新：Phase 1 只占位
│   ├── news_refresh.py         ← 新：Phase 2 实装
│   ├── event_extractor.py      ← 新：Phase 2 实装
│   ├── models.py               ← 瘦身，Pydantic 类搬去 contracts/company.py
│   └── pipeline.py             ← 编排 importer → canonical 写入
│
├── professor/                  ← 采集逻辑完全保留，仅在输出端加 canonical_writer
│   ├── discovery.py            ← 现有，保留（1829 行，含 SIGS/HIT/CUHK 特化路由）
│   ├── enrichment.py           ← 现有，保留（extract_profile_record）
│   ├── name_selection.py       ← 现有，保留（select_canonical_name 处理同名冲突）
│   ├── paper_collector.py      ← 现有，保留（四源聚合 + disambiguation_confidence）
│   ├── cross_domain_linker.py  ← 现有，保留（v3 产物；Phase 4 移入 resolver/）
│   ├── pipeline_v2.py          ← 现有，保留（生产版）；release 阶段调 canonical_writer
│   ├── pipeline_v3.py          ← 现有，保留（实验版）；Phase 6+ 再做 cutover 决策
│   ├── release.py              ← 改写：同时写 canonical + 旧 ReleasedObject (双写过渡)
│   ├── publish_helpers.py      ← 微调：build_professor_record_from_enriched 增参
│   ├── canonical_writer.py     ← 新 (~200-300 行)：MergedProfessorProfile → 
│   │                              professor / professor_affiliation / professor_fact /
│   │                              professor_paper_link / professor_company_role 五表写入
│   └── models.py               ← 瘦身（Pydantic 类搬去 contracts/professor.py）
│
├── paper/
│   ├── crossref.py / openalex.py / semantic_scholar.py  ← 现有保留
│   ├── hybrid.py               ← 现有保留
│   ├── canonical_writer.py     ← 新：写入 paper 表 + professor_paper_link candidate
│   └── models.py
│
├── patent/
│   ├── import_xlsx.py          ← 重写：Phase 1 扩列，输出 patent 表 + applicants/inventors_parsed
│   ├── applicant_resolver.py   ← 新：match applicants → company candidate
│   ├── inventor_resolver.py    ← 新：match inventors → professor candidate
│   └── models.py
│
├── projection/                 ← 新
│   ├── builder.py              (answer_pack 构建入口)
│   ├── company_projection.py
│   ├── professor_projection.py
│   ├── paper_projection.py
│   ├── patent_projection.py
│   ├── fts_builder.py          (zhparser tsvector)
│   └── embedding_builder.py    (qwen/bge-small-zh → vector(1024))
│
├── retrieval/                  ← 新
│   ├── planner.py              (Query Understanding + Plan)
│   ├── entity_lookup.py
│   ├── graph_traversal.py
│   ├── lexical.py              (Phase 2+)
│   ├── semantic.py             (Phase 2+)
│   ├── event_query.py          (Phase 2+)
│   └── online_freshness_patch.py  (Phase 5)
│
├── quality/                    ← 新
│   ├── rules/
│   │   ├── R001_prof_paper_count_outlier.py
│   │   ├── R002_company_merge_suspicion.py
│   │   ├── R003_news_from_new_domain.py
│   │   └── ...
│   ├── runner.py
│   └── readiness_eval.py       (跑测试集答案.xlsx 扩样)
│
├── taxonomy/                   ← 新
│   ├── seed_data.py            (初始 taxonomy_vocabulary 行)
│   ├── classifier.py           (LLM + rule 混合)
│   └── domain_tier.py          (source_domain_tier_registry 初始数据)
│
├── normalization.py            ← 现有保留
├── runtime.py                  ← 现有保留
└── publish.py                  ← LEGACY 注释，Phase 5 退役
```

### 9.3 `company/import_xlsx.py` 重写要点

**当前问题**（基于实际读 docs/专辑项目导出1768807339.xlsx 得出）：
- 现 importer 只识别 25 列（HEADER_ALIASES），**遗漏 17 列**：FA信息、Logo链接、星级、状态、备注、成立年限、参保人数、股东数、投资数、商标数、著作权、招聘数、新闻数、机构方数量、融资总次数、融资总额、估值
- 当前输出 `CompanyImportRecord` 是一个扁平对象，带 FinancingEvent[]——和新 `company_snapshot` 表不对齐
- `team_raw` 字段只保留原文，未解析为结构化 team member

**重写后行为**：
```python
# 伪代码
def import_company_xlsx(xlsx_path: Path, *, seed_id: str) -> None:
    batch = PipelineRunRepo.start_run(run_kind='import_xlsx', seed_id=seed_id, source_file=xlsx_path)
    import_batch_id = ImportBatchRepo.create(batch, xlsx_path)
    
    rows = parse_xlsx_with_42_columns(xlsx_path)  # 扩展 HEADER_ALIASES
    for source_row_number, raw in rows:
        try:
            company_id = resolve_company_identity(
                unified_credit_code=raw.get('unified_credit_code'),  # 暂无
                website=raw.get('website'),
                registered_name=raw['company_name'],
            )
            is_new = company_id is None
            if is_new:
                company_id = CompanyRepo.create(raw)
            
            snapshot_id = CompanySnapshotRepo.insert(
                company_id=company_id,
                import_batch_id=import_batch_id,
                source_row_number=source_row_number,
                raw_row_jsonb=raw.as_dict(),
                **map_xlsx_to_snapshot_fields(raw),  # 全 42 列
            )
            
            team_members = TeamParser.parse(raw['team_raw'])  # 按 "姓名，职务：X，介绍：Y。" 模式
            for order, member in enumerate(team_members):
                CompanyTeamMemberRepo.insert(
                    company_id=company_id,
                    snapshot_id=snapshot_id,
                    member_order=order,
                    raw_name=member.name,
                    raw_role=member.role,
                    raw_intro=member.intro,
                    normalized_name=normalize_name(member.name),
                )
            
            # 最近一轮融资直接写 company_signal_event (event_type=funding)
            if raw['latest_funding_time']:
                SignalEventRepo.upsert(
                    company_id=company_id,
                    event_type='funding',
                    event_date=parse_date(raw['latest_funding_time_raw']),
                    event_subject_normalized={
                        'round': raw['latest_funding_round'],
                        'amount_raw': raw['latest_funding_amount_raw'],
                        'amount_cny_wan': raw['latest_funding_cny_wan'],
                        'investors_raw': raw['latest_investors_raw'],
                    },
                    primary_news_id=None,
                    confidence=0.95,  # xlsx 来源
                    dedup_key=hash_funding_dedup(...),
                )
            
            SourceRowLineageRepo.create(
                batch_id=import_batch_id,
                source_row_number=source_row_number,
                target_entity_type='company',
                target_entity_id=company_id,
                resolution_status='created' if is_new else 'matched',
                raw_row_jsonb=raw.as_dict(),
            )
        except Exception as e:
            SourceRowLineageRepo.create(..., resolution_status='failed', resolution_reason=str(e))
            PipelineRunRepo.bump_failed(batch)
    
    PipelineRunRepo.finish(batch, status='succeeded' if no_failures else 'partial')
```

**关键扩展**：
- `HEADER_ALIASES` 扩到 42 列（见 §6.2 `company_snapshot` 完整列表）
- `team_parser.py` 解析 `姓名，职务：X，介绍：Y。` 格式；失败的 team_raw 整段放 `company_team_member.raw_intro`
- 融资字段直接落 `company_signal_event`（一条 xlsx 记录 → 一条 funding event），而非原来的 `FinancingEvent` 嵌入

### 9.4 `professor/canonical_writer.py` 新写要点

**定位**：纯输出层。教授 pipeline 的采集代码（discovery / enrichment / name_selection / paper_collector / cross_domain_linker）**完全不改**，只在 release 阶段加一个写 canonical 的分支。

**基于现有代码事实**：
- 生产管道 = `pipeline_v2.py`；`pipeline_v3.py` 是实验版
- 现有已捕获 `evidence_urls[]` + 部分 `field_provenance` dict
- `paper_collector.py` 已有多源 confidence 评分（官方公开列表 0.99、ORCID/Scholar 0.95-0.97）—— 直接映射为 `professor_paper_link.verified/candidate` 判定依据
- `name_selection.py:select_canonical_name()` 已解决 "roster name vs extracted name" 冲突 —— canonical professor 的 `canonical_name` 直接用它

**接口**：
```python
# data_agents/professor/canonical_writer.py

def write_canonical_bundle(
    merged: MergedProfessorProfileRecord,      # pipeline_v2/v3 stage1-3 产出
    enriched: EnrichedProfessorProfile,        # stage2-3 富化结果
    paper_result: PaperEnrichmentResult,       # paper_collector 产出
    company_links: list[CompanyLinkCandidate], # 可选；v3 cross_domain_linker 产出
    *,
    store: PostgresStore,
    pipeline_run_id: UUID,
) -> CanonicalWriteReport:
    """分流写 5 张表，返回写入统计。幂等（基于 professor_id + source_ref）。"""
    professor_id = _derive_professor_id(merged.canonical_name, merged.primary_institution)
    
    # 1. source_page upsert（所有引用的页面）
    page_ids = _upsert_source_pages(enriched.evidence_urls, store)
    
    # 2. professor upsert
    store.professor_repo.upsert(
        id=professor_id,
        canonical_name=name_selection.select_canonical_name(...),
        canonical_name_en=merged.canonical_name_en,
        aliases=merged.aliases,
        discipline_family=_classify_discipline(merged),
        primary_official_profile_page_id=page_ids.get_primary_profile(),
        identity_status='resolved',
    )
    
    # 3. professor_affiliation（多校任职用多条）
    for aff in merged.affiliations:
        store.professor_repo.upsert_affiliation(professor_id=professor_id, ...)
    
    # 4. professor_fact（每个 fact_type 一行，带 provenance）
    _write_research_topics(enriched.research_directions, page_ids, store)
    _write_education(enriched.education_structured, page_ids, store)
    _write_awards(enriched.awards, page_ids, store)
    _write_contacts(enriched.email, enriched.homepage, page_ids, store)
    
    # 5. professor_paper_link（复用 paper_collector disambiguation_confidence）
    for paper in paper_result.papers:
        link_status = _derive_link_status(paper.disambiguation_confidence, paper.evidence_source)
        # ≥0.95 且官方公开列表 → verified；否则 candidate
        store.relation_repo.upsert_professor_paper_link(...)
    
    # 6. professor_company_role candidate（仅 v3 产物，可空）
    for link in company_links or []:
        store.relation_repo.upsert_professor_company_role(
            link_status='candidate',    # 一律先 candidate，不自动 verify
            ...
        )
    
    return CanonicalWriteReport(...)
```

**release.py 改写**：

```python
# data_agents/professor/release.py

def build_professor_release(
    enriched_records: list[EnrichedProfessorProfile],
    *,
    store: PostgresStore,
    legacy_sqlite_store: SqliteReleasedObjectStore | None = None,  # 双写过渡
    pipeline_run_id: UUID,
) -> ReleaseReport:
    for enriched in enriched_records:
        # 新路径：写 canonical
        canonical_writer.write_canonical_bundle(
            merged=..., enriched=enriched, paper_result=..., company_links=...,
            store=store, pipeline_run_id=pipeline_run_id,
        )
        
        # 旧路径（Phase 3-5 过渡期保留，Phase 5 cutover 后退役）
        if legacy_sqlite_store:
            legacy_released_obj = build_professor_record_from_enriched(enriched)
            legacy_sqlite_store.upsert_released_objects([legacy_released_obj])
    
    return ReleaseReport(...)
```

**双写窗口**：Phase 3-5 约 4 周。新路径写 canonical（供 W2 Data Browser、answer_pack 构建），旧路径继续写 `released_objects`（供 legacy dashboard 路由 + 对比校验）。Phase 5 cutover 后 `legacy_sqlite_store` 参数改默认 `None`，旧路径停止写入。

**注意**：
- Phase 3 期间 **不做 v2→v3 cutover**。canonical_writer 对 v2/v3 输出都兼容（接口吃 `MergedProfessorProfileRecord + EnrichedProfessorProfile + PaperEnrichmentResult`，这些在 v2 和 v3 里 shape 一致）。
- v3 的 `cross_domain_linker.py` 产物是可选输入；v2 走 canonical_writer 时 `company_links=None` 即可。
- Phase 4 `team_resolver.py` 从 company 侧反向产生 `professor_company_role` candidate，和 v3 正向产生的候选**同落一张表**，不冲突。

### 9.5 `apps/admin-console/` 重组

```
apps/admin-console/
├── backend/
│   ├── api/
│   │   ├── home.py             ← W1 告警 + 时间线
│   │   ├── data.py             ← W2 列表 + 过滤 + 分页（替代 domains.py 能力）
│   │   ├── entity.py           ← W4 实体详情（含 Evidence Viewer 所需字段）
│   │   ├── monitor/
│   │   │   ├── ingestion.py    ← W3 Tab 1（含 Diff View）
│   │   │   ├── pipelines.py    ← W3 Tab 2
│   │   │   ├── freshness.py    ← W3 Tab 3
│   │   │   ├── anomaly.py      ← W3 Tab 4
│   │   │   └── readiness.py    ← W3 Tab 5 [Phase 5+]
│   │   ├── actions.py          ← verify_link / reject_link / edit_fact / merge_entity
│   │   ├── search.py           ← 全局搜索跨 entity_type
│   │   └── auth.py             ← 新：basic auth / SSO 入口（Phase 6）
│   ├── dashboard.py            ← LEGACY 注释 + 只读兼容层
│   ├── domains.py              ← LEGACY 注释 + 保留 PATCH 编辑路径（Phase 6 迁移完再撤）
│   ├── deps.py                 ← 改为加载 PostgresStore（保留 SqliteReleasedObjectStore 作为 legacy 只读）
│   └── main.py                 ← 挂新路由 + legacy 路由
│
└── frontend/
    ├── src/
    │   ├── pages/
    │   │   ├── Home.tsx              ← 新 W1
    │   │   ├── DataList.tsx          ← 新 W2 列表（继承 DomainList 能力）
    │   │   ├── EntityDetail.tsx      ← 新 W4（三栏布局；浏览和质量场景共用）
    │   │   ├── Monitor.tsx           ← 新 W3（tab 容器）
    │   │   ├── Dashboard.tsx         ← LEGACY，重定向到 /
    │   │   ├── DomainList.tsx        ← LEGACY，重定向到 /data/{type}
    │   │   └── RecordDetail.tsx      ← LEGACY，重定向到 /data/{type}/{id}
    │   ├── components/
    │   │   ├── EvidenceViewer.tsx    ← 新（core UI primitive）
    │   │   ├── DiffView.tsx          ← 新
    │   │   ├── AlertCard.tsx         ← 新
    │   │   ├── RelationCard.tsx      ← 新
    │   │   ├── FilterBar.tsx         ← 新（多维过滤，DataList 用）
    │   │   └── FreshnessChip.tsx     ← 新（实体新鲜度徽章）
    │   └── api.ts                    ← 新 endpoint 对应
```

### 9.6 `apps/miroflow-agent/` 配置与依赖

**`apps/miroflow-agent/pyproject.toml`**：添加依赖
```toml
"psycopg[binary,pool] >= 3.2",
"pgvector >= 0.3",
"alembic >= 1.13",
"apscheduler >= 3.10",
"zhparser-py >= 0.1",  # 或等效 Chinese tokenizer
```

**`apps/admin-console/pyproject.toml`**：添加 psycopg + auth 相关
```toml
"psycopg[binary,pool] >= 3.2",
"authlib >= 1.3",  # SSO 预留
"pyjwt >= 2.8",
```

**`apps/miroflow-agent/conf/data_agent/postgres.yaml`**（新）：
```yaml
storage:
  kind: postgres
  dsn: ${oc.env:DATABASE_URL}
  pool:
    min_size: 2
    max_size: 10
scheduler:
  kind: apscheduler
  jobstore: postgres
embedding:
  model: bge-small-zh-v1.5
  dim: 1024
fts:
  tokenizer: zhparser
```

### 9.7 迁移工具

**新脚本** `apps/miroflow-agent/scripts/migrate_sqlite_to_postgres.py`：
- 只在 Phase 5 cutover 前跑一次
- 从旧 `released_objects` 表读全量 JSON payload
- 调 decomposer：`ReleasedObject → CanonicalBundle (company/professor/paper/patent + relations)`
- 写入新 Postgres
- 输出 reconciliation report（哪些成功、哪些冲突、哪些丢弃）

---

## 10. 迁移路径（Phase 0-6，~12 周）

### Phase 0 — 基础决策 (1 周)

**交付物**：
- 两个 `pyproject.toml` 更新完毕，`uv sync` 通过
- Postgres CI service（GitHub Actions postgres:16 + pgvector extension）
- `StorageEngine` Protocol（Pydantic-compatible 接口）
- `V001_init_source.sql` 可跑通
- Alembic 基线迁移
- `docs/architecture-decisions/` 目录，首批 ADR：
  - ADR-001: Postgres driver = psycopg3
  - ADR-002: Embedding model = bge-small-zh-v1.5, dim=1024
  - ADR-003: Chinese FTS = pgsql + zhparser
  - ADR-004: Scheduler = APScheduler (Postgres jobstore)
  - ADR-005: 合并 4 张 run 表为单 pipeline_run
- §11 附录 A/B/C（阈值 + taxonomy + domain tier）初稿

### Phase 1 — Company Canonical + XLSX Reimport (2 周)

**交付物**：
- `V002_init_company.sql` + migration 跑通
- `company/import_xlsx.py` 重写完成，42 列全映射
- `team_parser.py` 通过单测（含 docs/专辑项目导出1768807339.xlsx 全量样本）
- 跑通一次真实 xlsx 导入：1025 家公司 + ~2500 条 team_member + ~800 条 funding signal event
- 基础 `Entity Detail` 页（W2 最小版本）能展示 company

**验收**：
- `SELECT count(*) FROM company` = 1025 ± 5
- `SELECT count(*) FROM company_snapshot WHERE import_batch_id = ?` = 1025
- `SELECT count(*) FROM company_team_member` > 2000
- 数 `company_signal_event WHERE event_type='funding'` > 500（有融资历史的公司）
- dashboard `/entity/company/COMP-xxx` 返回结构化字段

### Phase 2 — Company News & Event Layer (2 周)

**交付物**：
- `V006_init_projection.sql` + 初版 `company_answer_pack`
- `company/news_refresh.py` 可按 `source_domain_tier_registry` 抓 top 200 company 的新闻
- `event_extractor.py` 用 LLM 从 news 抽 `company_signal_event`（结构化 payload）
- APScheduler 调度的日级 news refresh job
- Dashboard `Monitor / Freshness` 和 `Monitor / Pipelines` tab 可用

**验收**：
- Top 200 company 每家 ≥ 5 条近 30 天 news_item
- event timeline 能按 event_type 聚合显示
- event dedup_key 去重可验证（同一融资两条 news 只生成一个 event）

### Phase 3 — Professor Canonical (2 周)

**前提**：教授采集代码（discovery / enrichment / name_selection / paper_collector）**保持原状**，仅在输出端加 canonical_writer。不启动 v2→v3 cutover。

**交付物**：
- `V003_init_professor.sql`（professor / professor_affiliation / professor_fact 三表）
- `V005_init_relations.sql` 的 professor_paper_link 部分
- `professor/canonical_writer.py` 新写（~200-300 行，接口见 §9.4）
- `professor/release.py` 改写为双写（canonical + 旧 SQLite）
- `paper/canonical_writer.py` 写 paper 表 + professor_paper_link
- `source_page` rule-based page_role classifier（URL 正则 + anchor text 规则，不引 LLM）
- 跑通 `docs/教授 URL.md` 上所有深圳 STEM 高校
- `professor_answer_pack` 初版（仅 body jsonb，无 FTS/embedding）

**验收**：
- 深圳 STEM 高校覆盖率 100%（每校至少 1 位教授成功 `identity_status='resolved'`）
- 每位 resolved professor 至少有 `primary_official_profile_page_id` 非空
- `professor_paper_link` verified 行数 / (verified + candidate) 行数 ≥ 30%（前期保守指标）
- 旧 `released_objects` 中 `object_type='professor'` 条数 ≈ 新 `professor` 表条数（双写一致）
- targeted E2E 测试通过（现有 `run_professor_enrichment_v2_e2e.py` 加 canonical 断言）

### Phase 4 — 跨域 Resolvers (1.5 周)

**范围**：Phase 3 已做了 professor→paper；Phase 4 聚焦 **跨域连接**（professor↔company、professor↔patent、company↔patent）。

**交付物**：
- `company/team_resolver.py`：从 company 侧反向扫 `company_team_member.unresolved` → 匹配 professor，写 `professor_company_role` 或 `company_team_member.resolved_professor_id`
- 迁移 `professor/cross_domain_linker.py` → `data_agents/resolver/professor_to_company_resolver.py`：v3 正向产生的候选（教授→公司）也落同一张 `professor_company_role` 表
- `patent/import_xlsx.py` 扩列支持（如果 Phase 1 未做完）
- `patent/applicant_resolver.py`：patent.applicants_parsed → company candidate
- `patent/inventor_resolver.py`：patent.inventors_parsed → professor candidate
- `V005_init_relations.sql` 剩余部分（professor_company_role, professor_patent_link, company_patent_link）

**验收**：
- 跑完 team_resolver 后，`company_team_member.resolution_status='matched'` 召回 ≥ 80%（基于手工标注 100 对样本）
- `professor_company_role` 表同时接受 v3 正向产出 + team_resolver 反向产出，无重复（UNIQUE 约束生效）
- 典型跨域 query "深圳 STEM 教授创办的公司有哪些" 能从 graph_traversal 返回结果并带证据
- `company_patent_link` verified 召回率 ≥ 70%（基于 patent.applicants 精确匹配 company.registered_name）

### Phase 5 — Retrieval Planner + Online Freshness Patch (2 周)

**交付物**：
- `retrieval/planner.py` 实装 entity_lookup + graph_traversal
- `retrieval/online_freshness_patch.py` 集成 serper/google search
- `offline_enrichment_queue` 落库 + 每日处理 job
- `migrate_sqlite_to_postgres.py` 执行一次性迁移
- 旧 `released_objects` 转为只读
- 智能体端 hook：agent 读 `answer_pack` 优先于旧 SQLite

**验收**：
- 测试集答案.xlsx 扩样 70 题，综合通过率 ≥ 75%
- 失败题每题有 `blocking_gap` 结构化原因
- 真实 query 采样 online_freshness_patch 调用比例 ≤ 20%

### Phase 6 — Admin Console v2 (1.5 周)

**交付物**：
- W1 / W2 / W3 前后端全部完成
- `data_quality_rule` + `data_quality_issue` + 初始 10 条规则
- `admin_audit_log` 接入每个写动作
- Basic auth / SSO 预留接口
- 旧 Dashboard / DomainList / RecordDetail 保留可访问但加 banner "legacy view"

**验收**：
- 运营者能从 W1 进入待审 batch → 审核 → 提交
- 能搜索任一 canonical 实体并看到完整证据链
- Anomaly Tab 至少触发 3 条有效告警并能 drill-down
- Query Readiness Tab 每日自动跑一次

### Phase 7 — Hardening（post-MVP，持续）

- 新增 anomaly rule
- 扩充 taxonomy_vocabulary
- 补充 domain_tier_registry
- 扩展测试集样本
- PII 可见性策略（field-level visibility）
- SSO 正式接入
- `company_official_site_crawler` 正式实装

---

## 11. 附录

### 11.1 附录 A — 阈值与分数函数

| 字段 | 计算函数 | 初始阈值 |
|---|---|---|
| `author_name_match_score` | `max(jaro_winkler(canonical_name, author_name), jaro_winkler(canonical_name_en, author_name))` | ≥ 0.85 for auto verify |
| `topic_consistency_score` | cosine(embedding(paper.title_clean+abstract), embedding(aggregate(prof.research_topics))) | ≥ 0.5 for auto verify |
| `institution_consistency_score` | 1.0 若 paper 的 affiliation string 命中 professor.primary_affiliation 白名单；0.5 若命中别名；0.0 否则 | ≥ 0.9 for academic_api 渠道 auto verify |
| `professor_paper_link` promotion | 见 §6.5 硬规则 | — |
| `company_signal_event.confidence` | f(source_domain_tier, corroborating_news_count) | tier=1 单源 0.9；tier=3 需双源 ≥ 0.7；tier≥4 需三源 ≥ 0.6 |
| company merge 决策 | UNIFIED_CREDIT_CODE_MATCH > WEBSITE_HOST_MATCH > OFFICIAL_URL_MATCH > NAME_ALIAS_EXPLICIT | 前三者 auto，第四需人工 |

**校准来源**：每个阈值必须在 Phase 1-3 完成时用 ≥200 对人工标注样本验证（precision ≥ 0.95，recall 暂可调）。

### 11.2 附录 B — 受控词表初始种子（部分示例）

```
# namespace: industry
industry:robotics                      机器人
  industry:robotics.service            服务机器人
  industry:robotics.industrial         工业机器人
  industry:robotics.humanoid           人形机器人
  industry:robotics.surgical           手术机器人
industry:ai                            人工智能
  industry:ai.llm                      大语言模型
  industry:ai.vision                   计算机视觉
  industry:ai.speech                   语音
industry:vr_ar                         VR/AR
industry:healthcare                    医疗健康
  industry:healthcare.diagnostics      诊断设备
  industry:healthcare.devices          医疗器械
...

# namespace: data_route (直接服务 Question Family G)
data_route:real_world_collection                    真实世界采集
  data_route:real_world_collection.camera           相机采集
  data_route:real_world_collection.lidar            激光雷达
  data_route:real_world_collection.imu              惯导
  data_route:real_world_collection.teleoperation    遥操作采集
data_route:synthetic_generation                     合成生成
  data_route:synthetic_generation.simulation        仿真
  data_route:synthetic_generation.domain_randomization 域随机化
  data_route:synthetic_generation.generative_models 生成模型
data_route:hybrid_real_synthetic                    混合路线

# namespace: technology_route
technology_route:slam                               SLAM
  technology_route:slam.visual                      视觉 SLAM
  technology_route:slam.lidar                       激光 SLAM
technology_route:embodied_ai                        具身智能
  technology_route:embodied_ai.manipulation         操作层
  technology_route:embodied_ai.locomotion           运动层
technology_route:cloud_robotics                     云端机器人
...
```

**完整初始种子**：将在 Phase 0 交付，先保底覆盖 `docs/测试集答案.xlsx` 里的所有 taxonomy 答案词。

### 11.3 附录 C — `source_domain_tier_registry` 初始种子（3 tier 简化版）

| tier | 域名示例 | 含义 | 用途 |
|---|---|---|---|
| `official` | `*.edu.cn`, `*.gov.cn`, `miit.gov.cn`, `sipo.gov.cn`, `credit.szmqs.gov.cn`, 公司 canonical website host（动态） | 官方/工商 | `is_official_source=true` 唯一来源；可单源 verify |
| `trusted` | `xinhua.net`, `people.com.cn`, `21jingji.com`, `yicai.com`, `36kr.com`, `tmtpost.com`, `leiphone.com` | 权威/知名媒体 | 可作为 news_item 主源；需 ≥ 2 源印证才能升 event |
| `unknown` | 其他所有 | 未评估 | 仅作候选证据，不能单独支撑 canonical 写入 |

**扩展策略**：Phase 2 积累若干批真实 news 后，由运营在 W3 Anomaly Tab 观察信号（同一事件被哪些域名报道、哪些域名反复被标冲突）→ 手动把部分 `unknown` 升格 `trusted`，或把 `trusted` 内部细分 `trusted:authoritative` / `trusted:tech_press` 等 subtier。**初期不要猜**。

### 11.4 附录 D — Question Family 与表映射（修订版）

替换 004 的 QF 附录，显式 scope：

| QF | 含义 | canonical 表 | projection | retrieval |
|---|---|---|---|---|
| A | 单域精确事实 | company / professor / paper / patent | {entity}_answer_pack | entity_lookup |
| B | 单域语义+收窄 | company + company_fact | company_answer_pack (FTS+vector) | entity + lexical |
| C | 跨域串联 | + professor_company_role / company_patent_link | 双 answer_pack | entity + graph_traversal |
| D | 跨域聚合 | + 所有 verified relations | 多 answer_pack | entity + graph + aggregation |
| E | 开放性知识问答 | company_fact (taxonomy) + taxonomy_vocabulary | — | lexical + **online_freshness_patch** |
| F | 超范围 | — | — | reject with guidance |
| G | 歧义消解 | aliases + company.aliases / professor.aliases | — | entity + disambiguation prompt |

### 11.5 附录 E — 与 004 的差异清单

**保留**：四层架构思路 / verified 三态 / evidence 驱动 / seed-driven

**显著变化**：

| 004 | 005 |
|---|---|
| teacher-centered | company-primary + professor-precision |
| `person` 超表 | `professor` + `company_team_member` 分离 |
| live search → candidate → verify | live search = 旁路增量 + offline_enrichment_queue |
| 4 张 run 表 | 1 张 `pipeline_run` |
| 4 张 answer_pack 表 | 1 张多态 `answer_pack` |
| 4 张质量表 | 2 张：`data_quality_rule` + `data_quality_issue` + views |
| `query_facet_doc` 未定义 | 删除（Type E 靠 online patch） |
| `page_role` LLM 分类 | rules-based 主 + LLM 尾 |
| `is_official` 可由 LLM 决定 | 严格 url_host allow-list |
| dual-write + divergence alarm | **不做**；靠 xlsx 可重跑 |
| 7 阶段多季度 | Phase 0-6，~12 周 |
| 6 dashboard 视图独立页 | 3 工作流（W1/W2/W3） |
| 17 题 workbook gate | 70 题扩样 + blocking_gap 枚举 |
| 阈值未定义 | 附录 A 明确函数和初始值 |
| 受控词表未定义 | 附录 B 种子 |
| news source 信誉模糊 | `source_domain_tier_registry` + tier 公式 |
| event `normalized_subject` 未定义 | `dedup_key` 公式按 event_type 写死 |
| security/PII 空白 | field-level visibility 在 Phase 7；scope 显式写在 Non-Goals 第 10 条 |

**r2 增量裁剪（2026-04-17 修订）**：

| 项 | r1（initial） | r2（当前） |
|---|---|---|
| `page_link_candidate` 独立表 | 有 | **删除**；现有 discovery.py 不需要 |
| `company_official_page_ref` 独立表 | 有 | **删除**；用 source_page.owner_scope 表达 |
| `entity_merge_decision` 独立表 | 有 | **删除**；合并动作落 admin_audit_log |
| `data_quality_rule` 独立表 | 有 | **删除**；规则以 Python 模块代码形式存在 |
| `source_domain_tier_registry` 5 tier | 5 档 | **3 档**（official / trusted / unknown） |
| `answer_pack.embedding` / `fts` | Phase 1 必填 | **Phase 2+**，Phase 1 仅 body jsonb |
| `offline_enrichment_queue` | Phase 1 建表 | **Phase 5+** |
| `answer_readiness_eval` | Phase 1 建表 | **Phase 5+** |
| `StorageEngine` Protocol 抽象层 | 有 | **删除**；直接写 PostgresStore |
| `professor/pipeline_v4_canonical.py` 新写 | 有 | **删除**；改为 `canonical_writer.py` 纯输出层，不新建 pipeline |
| Dashboard 3 workflow | W1/W2/W3 | **4 workflow**：W1 Home + W2 Data Browser（继承当前 web 控制台） + W3 Monitor + W4 Entity Detail |

---

## 12. 开工顺序（执行 checklist）

按此顺序启动，前置项不通不开始下一项：

**Phase 0 — 基础决策**
- [ ] 0.1 两个 pyproject.toml 加 psycopg3 + pgvector + alembic + apscheduler，`uv sync` 通过（zhparser 放 Phase 2b）
- [ ] 0.2 CI 加 Postgres 16 + pgvector extension service
- [ ] 0.3 `alembic init` + V001 source layer DDL（不含 page_link_candidate、offline_enrichment_queue）
- [ ] 0.4 ADR-001 (psycopg3)、ADR-002 (暂定 embedding 推迟到 Phase 2b)、ADR-005 (合并 run 表)；FTS/embedding ADR 延到 Phase 2b
- [ ] 0.5 附录 A 阈值 → `data_agents/quality/threshold_config.py`；附录 B taxonomy 种子 → `data_agents/taxonomy/seed_data.py`；附录 C domain tier（3 档）→ `data_agents/taxonomy/domain_tier.py`
- [ ] ~~0.6 StorageEngine Protocol 定义~~ （r2 删除，不做此抽象）

**Phase 1 — Company Canonical**
- [ ] 1.1 V002 DDL + Pydantic contracts/company.py（含 snapshot 42 列）
- [ ] 1.2 `company/import_xlsx.py` HEADER_ALIASES 扩到 42 列；新建 `team_parser.py`（"姓名，职务：X，介绍：Y。" 模式）
- [ ] 1.3 xlsx row → company / company_snapshot / company_team_member / company_signal_event(funding) 写入链路
- [ ] 1.4 `apps/admin-console/backend/api/data.py` + `entity.py` + 前端 `DataList.tsx` + `EntityDetail.tsx` 最小版（场景 A 入口打通）
- [ ] 1.5 跑通 docs/专辑项目导出1768807339.xlsx：1025 家公司 + ~2500 team_member + ~500+ funding event

**Phase 2 — Company News & Event**
- [ ] 2a.1 V006 DDL + company_answer_pack 初版（仅 body jsonb）
- [ ] 2a.2 `company/news_refresh.py` 日级调度 top 200 company（tier=official/trusted 来源优先）
- [ ] 2b.1 `event_extractor.py` + dedup_key 公式
- [ ] 2b.2 ADR 落 embedding 模型 + 中文 FTS 方案；V008 DDL 加 fts_text / embedding 字段
- [ ] 2.x W3 Freshness + Pipelines + Anomaly tab

**Phase 3 — Professor Canonical（r2 修订）**
- [ ] 3.1 V003 DDL (professor / affiliation / fact)
- [ ] 3.2 V005 DDL (professor_paper_link)
- [ ] 3.3 `professor/canonical_writer.py` 新写（§9.4 接口）
- [ ] 3.4 `professor/release.py` 改写为双写
- [ ] 3.5 `paper/canonical_writer.py` + paper 表 DDL
- [ ] 3.6 `source_page` + rule-based page_role classifier（URL 正则 + anchor text）
- [ ] 3.7 跑 docs/教授 URL.md 全量，验收达标
- [ ] 3.8 `professor_answer_pack` 初版

**Phase 4 — 跨域 Resolvers**
- [ ] 4.1 V005 DDL 剩余（professor_company_role / professor_patent_link / company_patent_link）
- [ ] 4.2 `company/team_resolver.py` + `resolver/professor_to_company_resolver.py`（迁移 v3 cross_domain_linker）
- [ ] 4.3 `patent/import_xlsx.py` 扩列 + applicant_resolver + inventor_resolver
- [ ] 4.4 跨域 E2E: "深圳 STEM 教授创办的公司" 可答

**Phase 5 — Retrieval + Online Patch + 旧库迁移**
- [ ] 5.1 `retrieval/planner.py` + entity_lookup + graph_traversal
- [ ] 5.2 `retrieval/online_freshness_patch.py` + `offline_enrichment_queue` 建表
- [ ] 5.3 `V007_quality.sql` + `answer_readiness_eval` 建表 + 每日跑回归
- [ ] 5.4 `migrate_sqlite_to_postgres.py` 一次性迁移 + 旧 released_objects 转只读
- [ ] 5.5 双写停止（canonical_writer.legacy_sqlite_store=None）

**Phase 6 — Admin Console v2**
- [ ] 6.1 W1 Home + W2 Data Browser + W3 Monitor + W4 Entity Detail 前后端
- [ ] 6.2 `data_agents/quality/rules/R00X_*.py` 初始 10 条规则
- [ ] 6.3 `admin_audit_log` 接入每个写动作
- [ ] 6.4 Basic auth / SSO 入口（Phase 7 完成）
- [ ] 6.5 旧 Dashboard / DomainList / RecordDetail 页加 LEGACY banner

---

## One-Line Rule

**Schema 是 crawler 和 cleaner 的蓝图；shape 决定行为。企业域以 xlsx 42 列为底座扩展结构化事实与事件；教授域以官方 roster 为锚点、verified relation 为骨架；离线 canonical 不容污染，在线新鲜度不入图谱。**
