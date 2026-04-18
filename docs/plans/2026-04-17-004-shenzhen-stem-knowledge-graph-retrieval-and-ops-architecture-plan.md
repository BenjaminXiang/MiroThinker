---
title: Shenzhen STEM Knowledge Graph Retrieval And Ops Architecture Plan
date: 2026-04-17
status: active
owner: codex
origin:
  - docs/plans/2026-04-17-001-professor-stem-reset-and-storage-redesign-plan.md
  - docs/plans/2026-04-17-003-professor-stem-issue-closure-plan.md
  - docs/solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md
  - docs/solutions/workflow-issues/professor-stem-rebuild-current-problems-2026-04-17.md
---

# Shenzhen STEM Knowledge Graph Retrieval And Ops Architecture Plan

## Goal

把当前“released object 大宽表 + 混合搜索 + 对象浏览式后台”重构为一条 **seed-driven、offline-first、question-oriented** 的主线架构，使系统能够：

1. 以深圳高校 STEM 教师为中心稳定发现老师
2. 以导入的企业/专利 `xlsx` 为结构化种子稳定构建公司和专利域
3. 通过 verified relation 把 `teacher / company / paper / patent / news` 组织成可追溯知识图谱
4. 在线回答时优先读取本地库和本地检索投影，而不是反复现场搜索
5. 让运维人员在 web 控制台清楚看到“数据是怎么来的、对不对、卡在哪里、哪里变旧了”
6. 最终更稳定地支撑 [测试集答案.xlsx](../测试集答案.xlsx) 同类问题回答

## Product North Star

这不是一个通用网页搜索系统，而是一个：

**以深圳高校 STEM 老师为中心、离线持续构建、支持投研型企业问题的知识图谱与问答底座。**

因此核心路径固定为：

- 高校官方 `roster seed` 负责发现老师
- 企业 `xlsx` 负责发现公司
- 专利 `xlsx` 负责发现专利
- 公司新闻刷新负责补充最近动态与投研事件
- 所有在线回答优先从本地事实层与投影层完成

## Why This Architecture Is Necessary

当前主线已经暴露出三个结构性问题：

1. [search_service.py](../../apps/miroflow-agent/src/data_agents/service/search_service.py) 仍是“关键词猜 domain + exact/semantic 混搜”，无法稳定支撑复杂问答。
2. [sqlite_store.py](../../apps/miroflow-agent/src/data_agents/storage/sqlite_store.py) 仍是 `released_objects` 单表 payload 存储，事实、关系、检索投影混在一起。
3. [dashboard.py](../../apps/admin-console/backend/api/dashboard.py) 只展示 `count / quality / last_updated`，无法支持运维判断“数据收集得对不对”。

结论：继续在当前 serving/store/search 之上打补丁，无法同时满足准确性、速度、成本控制、可运维性和 workbook-answerability。

## Primary Product Constraints

### 1. Teacher Discovery Constraint

深圳高校教师列表页是老师发现主种子。高校 seed 页的职责是：

- 告诉系统“这个学校/院系有哪些老师”
- 提供官方详情页入口
- 提供后续递归的官方锚点

它不是最终人物画像页，也不是最终论文页。

### 2. Company Seed Constraint

企业域的主 seed 不是网络搜索，而是外部导出的结构化 `xlsx`。

预期输入包括：

- 企业工商/行业/融资/团队等 `xlsx`
- 后续周期刷新得到的公司新闻

这意味着 company domain 的第一职责是“稳健导入和持续刷新”，而不是“开放式发现”。

### 3. Patent Seed Constraint

专利域同样以结构化 `xlsx` 导入为主，不依赖在线搜索作为主发现机制。

### 4. Offline-First Constraint

用户希望尽可能离线收齐数据，避免在线回答时反复做多轮 search。

因此：

- search 不应成为主数据生产方式
- search 只能作为离线 enrichment 或在线 fallback
- fallback 的结果必须回写离线管线，而不是停留在一次性对话结果里

### 5. Workbook-Answerability Constraint

字段设计、关系设计、检索设计、dashboard 设计，都必须首先回答：

**这套系统是否能自动化回答 `测试集答案.xlsx` 同类问题。**

## Architecture Overview

整体架构采用四层：

1. `Source Layer`
2. `Canonical Graph Layer`
3. `Retrieval Projection Layer`
4. `Serving + Ops Layer`

### Layer 1. Source Layer

负责保留原始输入和来源追踪。

核心对象：

- `seed_registry`
- `import_batch`
- `source_page`
- `page_link_candidate`
- `source_row_lineage`
- `news_refresh_run`

### Layer 2. Canonical Graph Layer

负责保存可追溯的实体、事实、关系，不直接为 UI 让步。

核心对象：

- `person`
- `person_affiliation`
- `person_fact`
- `company`
- `company_snapshot`
- `company_fact`
- `company_news_item`
- `company_signal_event`
- `paper`
- `patent`
- verified relation tables

### Layer 3. Retrieval Projection Layer

负责把 canonical graph 派生成适合检索与问答的文档，不直接承担“真相源”。

核心对象：

- `person_answer_pack`
- `company_answer_pack`
- `paper_answer_pack`
- `patent_answer_pack`
- `query_facet_doc`

### Layer 4. Serving + Ops Layer

- 智能体问答默认读取 `answer_pack`
- web 控制台读取 `answer_pack + telemetry + lineage`
- live search 只做 fallback，不直接变成 canonical facts

## Seed Taxonomy

### A. Teacher Seeds

`seed_type = teacher_roster`

来源：

- 高校官方教师 roster
- 院系师资页
- teacher-search 页

作用：

- 发现老师
- 发现官方详情页
- 形成后续递归的官方链入口

### B. Company Seeds

`seed_type = company_xlsx`

来源：

- 三方软件导出的深圳企业信息 `xlsx`

作用：

- 发现 company 实体
- 提供行业、融资、官网、地区等初始结构化维度
- 作为公司新闻刷新和公司-老师关联的主对象集合

### C. Patent Seeds

`seed_type = patent_xlsx`

来源：

- 专利数据库导出的 `xlsx`

作用：

- 发现 patent 实体
- 提供 applicant / inventor / title / patent_number 等结构化维度
- 作为 person/company-patent 关系的候选来源

### D. News Refresh Seeds

`seed_type = company_news_feed`

来源：

- 公司官网新闻页
- 官方公众号/公告页
- 高可信媒体站点

作用：

- 为 company 域补充投研需要的近期动态
- 构建事件时间线，而不是只堆文章列表

## Canonical Data Model

### 1. Person Hub

底层核心实体必须是 `person`，而不是 `professor`。

原因：

- 一个老师可能同时是教师、创业者、专利发明人、论文作者
- `professor` 只是这个人的一个角色或投影视图

#### `person`

- `person_id`
- `canonical_name`
- `canonical_name_en`
- `aliases`
- `discipline_family`
- `identity_status`
- `primary_official_profile_page_id`

#### `person_affiliation`

- `affiliation_id`
- `person_id`
- `institution`
- `department`
- `title`
- `employment_type`
- `is_primary`
- `is_current`
- `start_year`
- `end_year`
- `source_page_id`

这张表负责解决多校/多岗位任职问题。

#### `person_fact`

- `fact_id`
- `person_id`
- `fact_type`
- `value`
- `normalized_value`
- `source_page_id`
- `evidence_span`
- `confidence`

`fact_type` 至少包括：

- `research_topic`
- `education`
- `work_experience`
- `award`
- `academic_position`
- `homepage`
- `contact`

### 2. Company Core

#### `company`

- `company_id`
- `canonical_name`
- `registered_name`
- `aliases`
- `website`
- `hq_city`
- `is_shenzhen`
- `identity_status`

#### `company_snapshot`

表示某次 `xlsx` 导入或官网抓取后形成的结构化快照。

- `snapshot_id`
- `company_id`
- `import_batch_id`
- `snapshot_source_type`
- `industry`
- `sub_industry`
- `business`
- `registered_capital`
- `established_date`
- `legal_representative`
- `registered_address`
- `contact_phone`
- `contact_email`
- `website`
- `patent_count_reported`
- `team_raw`
- `financing_events_raw`
- `snapshot_created_at`

这张表不应该被覆盖，只能追加，供运维回看历史变化。

#### `company_fact`

- `fact_id`
- `company_id`
- `fact_type`
- `value`
- `normalized_value`
- `source_kind`
- `source_ref`
- `confidence`

建议重点支持：

- `industry_tag`
- `product_tag`
- `technology_route`
- `founder_background`
- `customer_type`
- `data_route_type`
- `real_data_method`
- `synthetic_data_method`
- `movement_data_need`
- `operation_data_need`

这些字段直接服务投研问题和 workbook 里的 taxonomy 问题。

### 3. Paper Core

#### `paper`

- `paper_id`
- `title_clean`
- `title_raw`
- `doi`
- `arxiv_id`
- `openalex_id`
- `year`
- `venue`
- `abstract_clean`
- `authors_display`
- `citation_count`
- `canonical_source`

关键规则：

- 主显示字段只能用 `title_clean`
- `title_raw` 只保留审计和回溯
- 乱码、MathML、HTML 残片不允许进入主展示与检索字段

### 4. Patent Core

#### `patent`

- `patent_id`
- `patent_number`
- `title_clean`
- `title_raw`
- `applicants`
- `inventors`
- `filing_date`
- `publication_date`
- `patent_type`
- `status`
- `abstract_clean`

### 5. Company News and Events

#### `company_news_item`

- `news_id`
- `company_id`
- `source_domain`
- `source_url`
- `published_at`
- `title`
- `summary_clean`
- `content_clean`
- `is_official`
- `source_confidence`
- `refresh_run_id`

#### `company_signal_event`

- `event_id`
- `company_id`
- `news_id`
- `event_type`
- `event_date`
- `event_summary`
- `structured_payload`
- `confidence`

`event_type` 至少包括：

- `funding`
- `product_launch`
- `partnership`
- `policy`
- `hiring`
- `order`
- `patent`
- `award`
- `expansion`

投研用户真正需要的是 `event timeline`，不是简单新闻列表。

去重规则：

- 如果新闻事件对应已知 `patent` 或已知公司奖项 fact，`company_signal_event` 必须保留回链到 authoritative entity/fact
- timeline 视图按 `company_id + event_type + normalized subject + event_date window` 去重
- `patent/award` 类事件不得与 canonical patent/fact 双重计数

## Verified Relation Model

### 1. `person_paper_link`

- `link_id`
- `person_id`
- `paper_id`
- `link_status`
- `evidence_source_type`
- `evidence_page_id`
- `evidence_url`
- `match_reason`
- `author_name_match_score`
- `topic_consistency_score`
- `institution_consistency_score`
- `is_officially_listed`
- `verified_by`

状态至少分：

- `verified`
- `candidate`
- `rejected`

强规则：

- 老师的论文只能通过这张表读取
- 不再允许 `paper.professor_ids` 直接作为事实来源

### 2. `person_company_role`

- `role_id`
- `person_id`
- `company_id`
- `role_type`
- `link_status`
- `evidence_source_type`
- `evidence_url`
- `match_reason`
- `verified_by`

`role_type` 至少包括：

- `founder`
- `cofounder`
- `advisor`
- `chief_scientist`
- `board_member`
- `executive`

### 3. `person_patent_link`

- `link_id`
- `person_id`
- `patent_id`
- `role_type`
- `link_status`
- `evidence_source_type`
- `evidence_url`
- `match_reason`

### 4. `company_patent_link`

- `link_id`
- `company_id`
- `patent_id`
- `link_status`
- `evidence_source_type`
- `match_reason`

## Identity Resolution Policy

Identity resolution 是这条主线的硬约束，不允许把 `person_id / company_id` 当成“先生成再说”的技术细节。

### Person Identity Resolution

优先级从高到低：

1. 官方教师详情页 URL
2. 官方详情页明确挂出的个人主页 / 官方 external profile
3. 官方详情页中的姓名 + 当前 affiliation
4. ORCID / DBLP / Scholar 等外部 academic profile（仅在官方链锚定时）
5. 弱名字匹配

规则：

- 如果官方详情页 URL 不同，但姓名和 affiliation 相同，不自动合并，进入 `needs_review`
- 如果同一人存在多个学校任职，应复用同一个 `person`，新增多条 `person_affiliation`
- 如果外部 profile 与官方 affiliation/topic 明显冲突，不允许自动并入已有 `person`

### Company Identity Resolution

优先级从高到低：

1. 统一社会信用代码或等价工商唯一标识（如果 xlsx 提供）
2. 官网域名
3. 注册名称
4. 标准化公司名
5. 别名/简称

规则：

- xlsx 导入和新闻抓取不允许仅靠简称自动合并 company
- 如果注册名称和官网域名冲突，先保留多候选状态，不自动 merge
- 如果两行 xlsx 指向同一 canonical company，必须记录 merge evidence

### Merge and Split Evidence

建议新增：

- `entity_merge_decision`
  - `merge_id`
  - `entity_type`
  - `winner_entity_id`
  - `loser_entity_id`
  - `decision_reason`
  - `decision_source`
  - `evidence_refs`
  - `decided_at`

所有自动 merge、人工 merge、split rollback 都必须落这张表，并回链到 `source_row_lineage` 或 `source_page`。

## Relation Verification Policy

`candidate -> verified` 的 promotion 规则必须显式定义，否则 verified relation 会重新退化成弱匹配。

### person_paper_link

自动 `verified` 的最低条件：

- 来自官方 publication page / 官方个人主页 / CV / 官方锚定 academic profile
- `author_name_match_score` 达到阈值
- `topic_consistency_score` 不低于最低线
- 没有明显 institution/topic conflict

其余情况一律先落 `candidate`。

### person_company_role

自动 `verified` 的最低条件：

- 公司官网、工商、可信媒体或官方教师页存在明确角色证据
- `role_type` 明确，不是模糊“有关联”
- 公司 identity 已稳定归一

否则先落 `candidate`。

### person_patent_link / company_patent_link

自动 `verified` 的最低条件：

- 发明人/申请人和 canonical identity 对齐
- patent_number 有效
- applicant/inventor 解析无歧义

### Human-in-the-Loop Policy

- 低风险高置信关系可以自动 verified
- 其余 candidate 必须进入 dashboard 待审队列
- rejected relation 必须保留 rejection reason，避免重复回流

## Source and Lineage Model

### 1. `seed_registry`

- `seed_id`
- `seed_type`
- `institution`
- `department`
- `source_uri`
- `priority`
- `refresh_policy`
- `status`
- `last_processed_at`

### 2. `import_batch`

- `batch_id`
- `batch_type`
- `source_file_or_feed`
- `started_at`
- `finished_at`
- `rows_read`
- `records_parsed`
- `records_merged`
- `records_failed`
- `run_status`

### 3. `source_row_lineage`

- `lineage_id`
- `batch_id`
- `source_row_number`
- `target_entity_type`
- `target_entity_id`
- `merge_decision`
- `merge_reason`

### 4. `source_page`

- `source_page_id`
- `url`
- `page_role`
- `owner_scope`
- `is_official`
- `fetched_at`
- `http_status`
- `title`
- `clean_text`
- `content_hash`

`page_role` 必须强区分：

- `roster_seed`
- `department_hub`
- `official_profile`
- `personal_homepage`
- `lab_homepage`
- `official_publication_page`
- `cv_pdf`
- `official_external_profile`
- `news_article`
- `web_search_result`

### 5. `page_link_candidate`

- `candidate_id`
- `from_page_id`
- `target_url`
- `candidate_role`
- `priority`
- `decision_source`
- `follow_status`
- `decision_reason`

这张表是“先抓官方详情页，再由 LLM 尽早分类外链”的落点。

## Retrieval Architecture

检索不应再是单一“对象表 + 向量搜”，而应拆成五类能力。

### A. Entity Lookup

适用于：

- 人名
- 公司名
- 别名
- 官网域名
- DOI
- 专利号

必须优先 exact / normalized / alias match。

### B. Graph Retrieval

适用于：

- 某老师有哪些 verified 论文/企业/专利
- 某公司关联哪些老师/专利/事件
- 某专利关联哪些公司/老师

这是问答的主 retrieval，不是附加能力。

### C. Lexical Retrieval

基于 `answer_pack` 做 FTS，用于：

- 条件筛选
- 面向描述的检索
- “深圳做机器人数据采集的公司”这类问题

### D. Semantic Retrieval

只搜索 `answer_pack/search_doc`，不搜索 raw object。

作用：

- 召回语义相近的候选
- 支持“研究方向相近”“技术路线接近”类问题

语义召回不能单独确权事实。

### E. Event Retrieval

专门服务投研和时间性问题。

适用于：

- 最近 30 天发生了什么
- 某公司近期是否有融资/合作/产品发布
- 某老师相关企业近期有没有重要动态

## Query Flow

在线查询路径应固定为：

1. `Query Understanding`
2. `Retrieval Planner`
3. `Retriever`
4. `Answer Assembler`
5. `Citation Builder`
6. `Live Fallback`（可选）

### 1. Query Understanding

判断 query 属于：

- 实体查找
- 关系查找
- 条件筛选
- 事件追踪
- 综合问答

### 2. Retrieval Planner

根据问题类型选择：

- `entity lookup`
- `graph retrieval`
- `lexical retrieval`
- `semantic retrieval`
- `event retrieval`

### 3. Retriever

读取 canonical graph 和 answer packs，拿候选集合。

### 4. Answer Assembler

只允许从：

- canonical facts
- verified relations
- news events
- answer packs

中组装答案。

### 5. Citation Builder

输出：

- 官方来源
- xlsx 来源
- 新闻来源
- freshness 信息
- 关键 relation 的证据说明

### 6. Live Fallback

只有当本地库缺失足够答案时，才允许触发：

- 窄范围 web search
- 窄范围 page fetch

并且 fallback 结果应进入下一轮离线 enrichment，不应该只停留在单次对话结果里。

### Fallback Write-Back Protocol

`live fallback` 的回写目标必须是候选层，不允许直接写 canonical facts 或 verified relations。

固定协议：

1. live search / live fetch 命中的页面先写入 `source_page`
   - `page_role = web_search_result`
   - `owner_scope` 按实体候选范围写入
2. 从 live page 抽出的链接写入 `page_link_candidate`
   - `follow_status = discovered`
   - `decision_source = runtime_fallback`
3. 从 live page 抽出的事实或关系只允许写入 candidate 层
   - `person_paper_link.link_status = candidate`
   - `person_company_role.link_status = candidate`
   - `person_patent_link.link_status = candidate`
4. candidate 进入下一轮离线 verification pipeline
5. 只有离线 verification 通过，才允许 promotion 到 `verified`

硬规则：

- live fallback 不得直接生成 `ready` 对象
- live fallback 不得直接覆盖 canonical fields
- 所有 runtime write-back 必须带 `refresh_run_id` 或等价运行标识

## Retrieval Storage Recommendation

目标建议：

- `Postgres`：canonical graph + lineage + telemetry + FTS
- `pgvector`：向量检索
- 文件系统/对象存储：raw pages / raw xlsx / markdown / exported artifacts

不建议继续以：

- `sqlite released_objects` 作为核心 truth store
- `Milvus + sqlite payload` 分裂承担真相和 serving

原因：

- 当前规模下，关系、过滤、回溯、运维比纯向量规模更重要
- `person/company/patent/news` 的联合过滤更适合 Postgres
- dashboard 直接查 SQL view 和 materialized view 更自然

## Retrieval Projections

### `person_answer_pack`

至少包含：

- 当前任职
- 官方研究方向
- verified papers
- verified company roles
- verified patents
- evidence summary
- freshness summary

### `company_answer_pack`

至少包含：

- 基础工商/行业画像
- 产品与技术路线
- 融资和快照摘要
- 关联老师
- 关联专利
- 最近新闻事件时间线
- 投研需要的 taxonomy 字段

### `paper_answer_pack`

- title
- venue/year
- authors
- linked persons
- evidence summary

### `patent_answer_pack`

- patent_number
- applicants
- inventors
- linked company/person
- technology effect summary

## Projection Build Model

`answer_pack` 是默认 serving surface，因此 projection build 不能留成隐含行为。

### Projection Triggers

- canonical entity 变化
- verified relation 变化
- company news event 变化
- import batch 完成
- scheduled rebuild

### Build Strategy

建议采用：

- canonical write 成功后，异步触发对应 `answer_pack` 增量重建
- 夜间或低峰期执行全量 reconciliation rebuild
- build 必须幂等，允许重复运行

### Required Telemetry

新增：

- `projection_build_run`
  - `build_id`
  - `projection_type`
  - `trigger_type`
  - `entity_scope`
  - `started_at`
  - `finished_at`
  - `status`
  - `rows_built`
  - `rows_failed`
  - `lag_seconds`

### Serving Consistency Contract

- query 默认读最新 successful projection
- 如果 projection 落后 canonical graph 超过 SLA，dashboard 必须报警
- in-flight rebuild 不应阻塞 query；读路径总是读取上一个 successful projection snapshot

### Suggested Freshness SLA

- `person_answer_pack`: `<= 1h` after canonical change
- `company_answer_pack`: `<= 2h` after canonical/news change
- `paper_answer_pack`: `<= 2h`
- `patent_answer_pack`: `<= 4h`

## Dashboard as Data Quality Control Console

Dashboard 的第一职责不是“看有多少条”，而是“看数据收集得对不对”。

### View 1. Seed Ingestion Board

关注导入和抓取是否正确进入系统。

老师：

- 高校 seed 总数
- roster 解析成功率
- 详情页发现率
- 递归页发现率

公司：

- company `xlsx` batch 列表
- 每批总行数
- 解析成功数
- 去重后公司数
- 缺关键字段行数
- merge conflict 数

专利：

- patent `xlsx` batch 列表
- 专利号缺失数
- applicant / inventor 解析失败数
- person/company 匹配率

### View 2. Canonical QA Board

关注实体是否已经成型。

老师：

- identity passed / failed
- affiliation 完整度
- official profile coverage

公司：

- company identity status
- 官网命中率
- 行业结构化完成度
- 近期新闻覆盖率

专利：

- patent_number 标准化完成度
- applicant -> company 连接率
- inventor -> person 连接率

### View 3. Relation QA Board

关注关系是否可信。

- `person_paper_link`
- `person_company_role`
- `person_patent_link`
- `company_patent_link`

必须支持污染告警：

- 同名论文污染
- 公司误合并
- applicant 误归属
- 错公司新闻

### View 4. Freshness Board

关注“数据是不是旧了”。

重点字段：

- `teacher_profile_last_refreshed_at`
- `company_snapshot_last_refreshed_at`
- `company_news_last_refreshed_at`
- `stale_company_count`
- `high_priority_company_stale_count`

建议最小 SLA：

- teacher official profile: refresh every `30d`, stale after `45d`
- company snapshot from xlsx: refresh whenever new batch arrives, stale after `90d` without batch
- company official/news refresh: refresh every `7d` for high-priority companies, stale after `14d`
- patent import: refresh on new batch, stale after `90d`

### View 5. Entity Lineage Board

关注“这条数据从哪来的”。

每个实体都要能 drill-down 到：

- seed 来源
- xlsx batch / row
- 官方详情页
- 递归页
- relation 验证证据
- 为什么是 `ready`
- 为什么不是 `ready`

### View 6. Answer Readiness Board

从问答能力反推数据准备度。

至少展示：

- 老师身份问答 readiness
- 老师论文问答 readiness
- 老师创业关联问答 readiness
- 公司画像问答 readiness
- 公司近期动态问答 readiness
- workbook 题型当前覆盖度

## Quality Control Schema

建议新增专门质量控制表，而不是只靠对象字段：

### `verification_issue`

- `issue_id`
- `entity_type`
- `entity_id`
- `stage`
- `issue_type`
- `severity`
- `evidence`
- `status`

### `entity_quality_snapshot`

- `snapshot_id`
- `entity_type`
- `entity_id`
- `quality_status`
- `blocking_reasons`
- `captured_at`

### `relation_quality_snapshot`

- `relation_type`
- `relation_id`
- `quality_status`
- `blocking_reasons`
- `captured_at`

### `answer_readiness_eval`

- `eval_id`
- `question_family`
- `entity_scope`
- `is_answerable`
- `blocking_gap`
- `evaluated_at`

这组表直接服务 dashboard，不应由前端临时拼逻辑。

### `pipeline_run` and `seed_refresh_run`

还必须新增运行级 telemetry：

- `pipeline_run`
  - `run_id`
  - `pipeline_type`
  - `seed_scope`
  - `started_at`
  - `finished_at`
  - `status`
  - `items_processed`
  - `items_failed`
- `seed_refresh_run`
  - `refresh_id`
  - `seed_id`
  - `started_at`
  - `finished_at`
  - `status`
  - `new_items_found`
  - `errors_count`

没有这层 telemetry，dashboard 无法支撑 ingestion success rate、projection lag 和 stale alarm。

## What Must Be Deprecated

以下旧字段或旧思路不应再作为主线事实源：

- `ProfessorRecord.top_papers`
- `PaperRecord.professor_ids`
- `evaluation_summary` 作为事实字段
- `released_objects` 作为唯一 truth store
- “query 关键词猜 domain” 作为主入口

这些能力如果保留，只能以 projection 或兼容层身份存在。

## LLM Responsibilities in the New Mainline

LLM 应该承担：

- 官方详情页外链分类与优先级排序
- 页面结构化抽取
- taxonomy 归类
- relation verification 辅助判断
- 事件抽取与归类

LLM 不应承担：

- 无证据造事实
- 用 summary 覆盖 canonical facts
- 在缺官方锚点的情况下直接确权 person-paper/person-company 关系

## Storage Migration Strategy

`Postgres + pgvector` 是目标架构，但不能作为无过渡的直接切换。

### Phase 0 Recommendation

在 Phase 1-2 允许：

- 继续保留当前 SQLite/Milvus 作为旧 serving 兼容层
- 新 canonical graph 进入 Postgres shadow stack

### Cutover Model

建议顺序：

1. importer dual-write
   - 旧 released-object 路径继续工作
   - 新 canonical graph 同步落 Postgres
2. projection shadow read
   - 构建 `answer_pack`，但不对线上读开放
3. side-by-side validation
   - 对同一 query 比较旧 serving 与新 answer pack
4. cutover
   - 智能体默认读新 projection
5. rollback window
   - 保留旧 serving 可回退窗口直到新路径通过 E2E 和 workbook gate

### Rollback Requirement

- 任一阶段必须能回退到旧读路径
- rollback 不能要求重建 raw source 数据
- dual-write divergence 必须进入 dashboard/ops alarm

## Migration Roadmap

### Phase 1. Schema and Storage Foundation

- 落 canonical graph schema
- 落 lineage / telemetry schema
- 保留现有 importer，但把输出改接新 schema

Exit Criteria:

- canonical graph 最小表集可写入
- lineage 与 import batch 可追溯
- 至少一条 teacher/company/patent 样本可完整落库

### Phase 2. Teacher Mainline Migration

- roster seed -> person hub
- official profile recursion -> page_link_candidate
- verified paper relation -> canonical graph

Exit Criteria:

- 真实 `docs/教授 URL.md` targeted E2E 在新 teacher mainline 上通过
- seed 页不再被误当 detail page
- person/person_affiliation/person_fact 可稳定生成

### Phase 3. Company and Patent Seed Migration

- company xlsx -> company/company_snapshot
- patent xlsx -> patent/company_patent_link/person_patent_link candidate

Exit Criteria:

- 至少一批真实 company xlsx 和 patent xlsx 导入成功
- company/patent lineage 可回溯到 batch 和 row
- candidate relation 可见且可审

### Phase 4. Company News Enrichment

- 建 news refresh scheduler
- 生成 `company_news_item + company_signal_event`

Exit Criteria:

- 高优先级 company 集合可以周期刷新
- 至少一类 event timeline 可稳定生成
- stale company 规则在 dashboard 可见

### Phase 5. Retrieval Projection Build

- 构建 `answer_pack`
- 构建 FTS / vector indexes

Exit Criteria:

- `person/company/paper/patent_answer_pack` 可生成
- projection lag 有 telemetry
- 查询能从 projection 返回可解释答案片段

### Phase 6. Admin Console Migration

- dashboard 从 count/quality 升级为 data quality control console
- entity detail 页接 lineage / readiness / relation quality

Exit Criteria:

- 运维能从后台判断“数据对不对”而不是只看数量
- 至少支持 ingestion/quality/freshness/lineage 四类核心视图

### Phase 7. Agent Answer Serving Cutover

- 智能体默认读 `answer_pack + canonical graph`
- live search 降为 fallback

Exit Criteria:

- 代表性 workbook 问题族在新路径可答
- live search 调用显著下降
- fallback write-back 不污染 canonical facts

## Real-Data E2E Acceptance

只有下面这些条件满足，才算 architecture 迁移有效：

1. 高校 roster 主线在真实 `docs/教授 URL.md` 上持续通过 targeted/broad E2E
2. company xlsx 导入后，company canonicalization 与官网/news enrichment 能形成稳定 answer pack
3. patent xlsx 导入后，person/company-patent relation 的 verified/candidate 状态可追踪
4. 针对 `测试集答案.xlsx` 的代表性问题家族，answer readiness 明显提升并可复跑
5. admin console 能让运维人员准确回答：
   - 数据从哪来
   - 哪一步失败
   - 哪些关系还不可信
   - 哪些公司新闻过期

## Workbook Traceability Appendix

为了避免 `workbook-answerability` 留在口号层，这里固定一组代表性问题族映射。

### Question Family A: 老师是谁、在哪、做什么

- canonical tables: `person`, `person_affiliation`, `person_fact`
- projection: `person_answer_pack`
- retrieval mode: `entity lookup + graph retrieval`

### Question Family B: 某老师有哪些可信论文

- canonical tables: `person_paper_link`, `paper`
- projection: `person_answer_pack`, `paper_answer_pack`
- retrieval mode: `entity lookup + graph retrieval`

### Question Family C: 某篇论文对应哪个老师

- canonical tables: `paper`, `person_paper_link`, `person`
- projection: `paper_answer_pack`
- retrieval mode: `entity lookup + graph retrieval`

### Question Family D: 某老师是否参与某公司

- canonical tables: `person_company_role`, `person`, `company`
- projection: `person_answer_pack`, `company_answer_pack`
- retrieval mode: `entity lookup + graph retrieval`

### Question Family E: 某公司做什么、最近有什么动态

- canonical tables: `company`, `company_snapshot`, `company_fact`, `company_signal_event`, `company_news_item`
- projection: `company_answer_pack`
- retrieval mode: `entity lookup + lexical retrieval + event retrieval`

### Question Family F: 某公司或老师有哪些专利

- canonical tables: `patent`, `person_patent_link`, `company_patent_link`
- projection: `patent_answer_pack`, `person_answer_pack`, `company_answer_pack`
- retrieval mode: `entity lookup + graph retrieval`

### Question Family G: 技术路线/数据路线/投研 taxonomy 问题

- canonical tables: `company_fact`, `company_signal_event`, optional linked `person/company/patent` graph
- projection: `company_answer_pack`, `query_facet_doc`
- retrieval mode: `lexical retrieval + semantic retrieval + event retrieval`

## Immediate Design Decisions

这份文档固定以下结论，后续实现不应反复摇摆：

1. 高校官方 roster 是老师主 seed。
2. 企业和专利 `xlsx` 是 company/patent 主 seed。
3. company 新闻刷新是 company 域的持续增强层。
4. truth store 要和 serving projection 分离。
5. retrieval 必须围绕 canonical graph 和 answer pack 设计。
6. dashboard 的核心职责是判断“数据收集得对不对”，不是只看数量。
7. 在线回答默认读取离线库；live search 只做 fallback。

## One-Line Rule

**新的主线不是“对象表上加更多字段”，而是：以 roster/xlsx 为种子、以 canonical graph 为真相、以 answer pack 为检索面、以 dashboard 为质量控制台的离线知识生产系统。**
