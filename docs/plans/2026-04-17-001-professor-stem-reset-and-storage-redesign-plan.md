---
title: Professor STEM Reset And Storage Redesign Plan
date: 2026-04-17
owner: codex
status: active
origin:
  - docs/solutions/workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md
  - docs/solutions/workflow-issues/testset-answer-workbook-coverage-validation-2026-04-16.md
  - docs/plans/2026-04-16-007-plan-portfolio-execution-roadmap.md
---

# Professor STEM Reset And Storage Redesign Plan

## Goal

把当前教授与论文数据链从“旧 shared store 污染 + 错误强关系 + 宽松 ready”重置为一条 **STEM 优先、官方证据优先、论文关系可验证** 的新主链，并最终能自动支撑 [测试集答案.xlsx](../测试集答案.xlsx) 那类问题回答。

这份计划只覆盖：

- 深圳高校的 STEM 教师
- professor / paper / professor-paper relation
- shared relational store 与 vector store 的重设计
- admin console backend 的 serving / relation 适配
- 基于真实 `docs/教授 URL.md` 与 workbook 问题的 E2E 验收

这份计划暂不覆盖：

- HSS / 艺术 / 教育 / 法学等非 STEM 教师的全面闭环
- company / patent 域的结构重做
- admin console 的大规模 UI 重做

## Safety Requirement

这轮是重置式重构，但不能接受“先清空再祈祷重建成功”。

任何 destructive reset 之前必须先完成：

1. shared SQLite snapshot
2. Milvus collection snapshot 或可恢复导出
3. rollback 条件定义
4. serving 切换策略定义

如果这些前置条件未满足，本计划不能进入实现阶段。

## Product Test: Workbook-Answerability

设计的第一性原则不是“schema 是否优雅”，而是：

**最终系统能否自动化地产出与 `测试集答案.xlsx` 同类问题相匹配的高质量回答。**

对当前 professor/paper 重构，重点服务以下问题类型：

1. 指定教授是谁，属于哪个学校/院系/方向
2. 指定教授是否有代表性论文，论文是否真的是他/她的
3. 给定一篇论文，是否能反查到正确教授
4. 能否围绕教授给出结构化、可信、非模板化的介绍
5. 能否把 professor 与 paper 作为后续 professor-company / professor-patent 问答的可靠中间层

因此，新的数据设计必须首先最大化：

- `identity correctness`
- `paper authorship correctness`
- `release-ready correctness`

而不是最大化对象总数。

## Why Now

当前 web 控制台里的 professor 数据质量差，不是单点 bug，而是结构性问题：

1. shared professor 域几乎整域是 `2026-04-05` 旧发布链产物
2. 旧链默认 `ready`，没有经过当前严格质量门
3. paper 域把 `professor_ids` 当成强关系落库，导致错作者关系被前端直接展示
4. professor 端只保留 `top_papers: list[str]`，丢失了证据来源和验证状态
5. paper 标题缺少统一 sanitizer，当前 shared store 里已存在 MathML / HTML entity / 标签残留

结论：继续在当前 shared store 上补丁式修复，不如重置派生层并重建契约。

## Confirmed Baseline

以下事实已由当前 shared store 和代码核实：

- 当前 professor 对象按 `last_updated` 分布：
  - `2026-04-05`: `3273`
  - `2026-04-16`: `1`
- 当前旧 professor 对象默认 `quality_status = ready`
- `唐博` 当前已被写入多篇明显不属于他的 paper 关系
- 当前 paper 标题至少存在：
  - `9` 条 `<mml:...>`
  - `57` 条 HTML entity 残留
  - `130` 条含残留标签/角括号内容

## Phase 6 STEM Slice

Phase 6 真实 E2E 只覆盖当前优先闭环的 STEM 学校：

- `南方科技大学`
- `清华大学深圳国际研究生院`
- `香港中文大学（深圳）`
- `中山大学（深圳）`
- `哈尔滨工业大学（深圳）`
- `深圳技术大学`
- `深圳理工大学`

这组学校在 Phase 0.5 会固化成一份 `stem_phase6_school_list.json`，后续 Phase 5 adapter 范围必须以它为准。

## Quantitative Safety Gates

这轮 reset 的 rollback / go-live 条件必须是硬数字，不允许用“明显低于预期”这类描述代替。

Phase 0.5 必须先锁定以下门槛：

- `phase6_discovered_stem_professor_count`：以上述 7 所学校真实全量 harvest 后得到的 STEM 教师基数
- `projected_stem_professor_count >= 0.90 * phase6_discovered_stem_professor_count`
- `ready_stem_professor_count >= 0.60 * phase6_discovered_stem_professor_count`
- `false_positive_verified_paper_link_count = 0`（以人工抽检集和 targeted real E2E 为准）
- `polluted_ready_professor_count = 0`
- `critical_workbook_subset_pass_rate = 1.0`

当前计划里的 critical workbook subset 明确限定为当前 professor/paper 主链必须支撑的题型：

- `q1` 的 professor identity 基础问答：`介绍清华的丁文伯`
- `q6` 的 professor-paper 精确关联：`pFedGPA ...`
- `q9` 的 professor identity / profile 问答：`王学谦`

这三类题型在 Phase 6 必须 `100%` 通过，不能再接受“对象存在但关系错”或“页面可查但答案仍要手工 patch”。

## Scope Boundary

### In Scope

- 清空并重建 shared store 中的 `professor` 与 `paper` 域
- 设计新的 professor / paper / professor-paper relation 契约
- 设计新的 relational schema
- 设计新的 vector schema
- 重做 STEM 专用 ready gate
- 重做 STEM 教师 paper linking 流程
- 基于真实 `docs/教授 URL.md` 与 workbook 风格问题完成 E2E 验收

### Out Of Scope

- HSS 的最终 release-ready 定义
- company / patent schema 变更
- admin console UI 大改
- 把所有学校适配器一次性做完

## Non-Negotiable Product Rules

1. 系统只采“系统里已有教授”的论文，不做开放式论文全网抓取。
2. 论文关系必须先验证再落强关系，不能因为名字命中就写入 `verified`。
3. `ready` 只表示“可以对外使用”，不能表示“字段非空”。
4. 对 STEM 当前采用“宁可少，不可错”的策略。
5. 学校官网 URL 只是 seed，必须递归到教师详情页、个人主页、课题组页、CV、ORCID、Scholar、publication 页面。

## Contract Migration Rules

这轮不是只加新表，不改老 contract。

必须同时改掉当前 shared contract 的默认危险行为：

- `ReleasedObject.quality_status` 默认值从 `ready` 改为 `needs_review`
- `ProfessorRecord.quality_status` 默认值从 `ready` 改为 `needs_review`
- `PaperRecord.quality_status` 默认值从 `ready` 改为 `needs_review`
- 其它共享 record 默认值也统一改成“非 ready 默认”，避免 call site 漏传时静默变成 `ready`

兼容迁移策略固定为：

- canonical fact tables 不再把 `paper.professor_ids` 作为事实源
- `ProfessorRecord.top_papers` 从 shared professor contract 中移除；代表论文只能通过 `verified professor_paper_link -> canonical paper` 在查询层派生
- `PaperRecord.professor_ids` 在过渡阶段保留为 **deprecated compatibility field**，只允许从 `verified professor_paper_links` 反向投影生成
- admin console 和新 serving relation API 不再读取 `paper.core_facts.professor_ids`
- 旧 `released_objects` 中已经序列化的 `top_papers / professor_ids` 只留在旧 projection；切换到新 projection 后不再作为事实依据

## `discipline_bucket` Definition

`discipline_bucket` 是当前 scope filter 的正式枚举，不允许留成自由文本。

允许值：

- `engineering`
- `science`
- `medicine`
- `other`

赋值规则：

- 优先由院系/学院名称规则判定
- 规则无法判定时，由 `slot_cleaner` 返回 `discipline_bucket`
- 在 canonical professor record 写入前可以被修正
- 一旦写入 release projection，只能通过明确 reprocess 更新

## Current Contract Failures

### 1. Old professor release path bypasses current gate

相关路径：

- `apps/miroflow-agent/src/data_agents/professor/release.py`
- `apps/miroflow-agent/src/data_agents/contracts.py`

问题：

- 旧链直接构造 `ProfessorRecord`
- `ProfessorRecord` 默认 `quality_status = ready`
- release summary 会被补长，看起来“像有效文本”

### 2. `paper.professor_ids` is too strong

相关路径：

- `apps/miroflow-agent/src/data_agents/paper/release.py`
- `apps/admin-console/backend/api/domains.py`
- `apps/miroflow-agent/src/data_agents/storage/sqlite_store.py`

问题：

- 一旦 `paper.professor_ids` 落库，前端就把它当“该教授论文”
- 当前没有 `candidate / rejected / verified` 的区分

### 3. `professor.top_papers` is too weak

相关路径：

- `apps/miroflow-agent/src/data_agents/contracts.py`
- `apps/miroflow-agent/src/data_agents/professor/publish_helpers.py`

问题：

- 只保存标题字符串
- 丢失 `paper_id / 证据来源 / 验证状态 / 匹配原因`

### 4. Paper title quality is uncontrolled

相关路径：

- `apps/miroflow-agent/src/data_agents/paper/release.py`
- `apps/miroflow-agent/src/data_agents/paper/crossref.py`
- `apps/miroflow-agent/src/data_agents/paper/openalex.py`
- `apps/miroflow-agent/src/data_agents/paper/semantic_scholar.py`

问题：

- 没有统一 `title sanitizer`
- 上游 metadata 的 HTML entity / MathML / tags 会直接进入 shared store

## Target Logical Architecture

1. `seed / discovery layer`
   - 学校 roster、详情页发现、学校 adapter
2. `evidence layer`
   - 官方详情页、个人主页、课题组主页、publication 页面、official-linked ORCID/CV/Scholar
3. `canonical entity layer`
   - clean professor records
   - canonical paper records
4. `relation layer`
   - professor-paper links with verification state
5. `release layer`
   - shared relational store
   - vector collections
   - admin console serving

核心决策：

**paper 是对象，authorship/link 是关系。**

## Relational Redesign

### Current Problem

当前 `SqliteReleasedObjectStore` 只有：

- `released_objects(id, object_type, display_name, payload_json)`

它适合 serving，不适合做 professor-paper 关系事实源。

### Proposed Fact Tables

#### `professor_records`

字段：

- `id`
- `name`
- `name_en`
- `institution`
- `department`
- `title`
- `email`
- `homepage`
- `profile_url`
- `lab_url`
- `research_directions_json`
- `education_json`
- `work_experience_json`
- `projects_json`
- `awards_json`
- `profile_summary`
- `evaluation_summary`
- `quality_status`
- `quality_detail`
- `discipline_bucket`
- `identity_confidence`
- `last_updated`
- `released_at`

约束：

- `quality_status` 默认不能是 `ready`
- `title` 必须是短字段
- polluted title 不能进入 release
- `discipline_bucket` 必须是上面的枚举值之一

#### `paper_records`

字段：

- `id`
- `canonical_title`
- `clean_title`
- `title_zh`
- `year`
- `venue`
- `doi`
- `arxiv_id`
- `abstract`
- `publication_date`
- `authors_json`
- `citation_count`
- `fields_of_study_json`
- `source_priority`
- `title_quality_status`
- `last_updated`
- `released_at`

约束：

- `canonical_title` 是 display-facing title，保留可信来源的 casing，但必须完成 HTML entity decode 与 tag strip
- `clean_title` 是 display-safe title，由 `canonical_title` 进一步去除 MathML / HTML residue 得到
- dedup 不直接使用存储字段本身，而是使用 `dedup_title_key = normalize(clean_title)` 的派生 key
- paper 本体不直接承诺属于某教授

去重层级必须固定为：

1. `doi`
2. `arxiv_id`
3. `normalized clean_title + year + author overlap`

其中 `dedup_title_key` 至少包括：

- lowercase
- HTML entity decode
- MathML / HTML tag strip
- punctuation collapse
- whitespace collapse

其中 `author overlap` 明确定义为：

- 至少一位作者在 person-name normalization 后匹配
- 匹配规则是 `surname exact + given-name initial exact`
- tier 3 dedup 只做 paper object merge，不直接产生 verified professor link

#### `professor_paper_links`

字段：

- `id`
- `professor_id`
- `paper_id`
- `link_status`
  - `verified`
  - `candidate`
  - `rejected`
- `match_reason`
- `verified_by`
  - `rule`
  - `llm`
  - `human`
- `match_confidence`
- `created_at`
- `updated_at`

关系约束：

- `UNIQUE(professor_id, paper_id)`
- 关系状态必须做 UPSERT，不允许同一 pair 出现多条冲突记录
- 状态强度默认：`verified > candidate > rejected`

状态机：

- `candidate -> verified`
- `candidate -> rejected`
- `rejected -> candidate` 仅允许人工 override
- `verified -> rejected` 仅允许人工撤销，并必须记录 reason

release 规则：

- admin console 只展示 `verified`
- `candidate` 仅内部可见
- `rejected` 用于防止反复误链

#### `professor_paper_evidence`

因为同一 professor-paper 关系可能被多种证据共同支撑，所以 link 本体不能只保留一个单值 `evidence_source`。

字段：

- `id`
- `link_id`
- `evidence_source`
- `evidence_url`
- `evidence_snippet`
- `evidence_rank`
- `created_at`

规则：

- 一个 `professor_paper_link` 可对应多条 `professor_paper_evidence`
- `professor_paper_links.match_confidence` 由 strongest evidence 聚合生成
- 不再让后续 pipeline run 覆盖掉 earlier evidence
- `evidence_rank` 是 ordinal integer，`1 = strongest`
- `evidence_rank` 在插入时按 source priority 固定：
  - `official_publication_page = 1`
  - `official_linked_orcid = 2`
  - `official_linked_cv = 3`
  - `school_matched_openalex = 4`
  - `other_candidate_source = 5`

### Serving Projection

`released_objects` 保留，但改成 projection/cache，不再是事实源。

迁移期间策略固定为：

- 旧 `released_objects.db` 继续 serving
- 新 canonical tables 构建在独立 SQLite 文件 `professor_paper_canonical_v2.db`
- 新 projection 构建在独立 SQLite 文件 `released_objects_v2.db`
- `released_objects_v2.db` 除 `released_objects` 外，新增 `released_relationships`
- 只有在 Phase 6 真实 E2E 通过后才允许原子切换 serving projection

禁止：

- 先清空 professor/paper 再等待多天重建
- 在 admin console 上直接暴露半成品 projection

### Serving Projection Design

#### Professor projection payload

来源：

- `professor_records`
- `professor_paper_links(link_status = verified)`
- `paper_records`

对外字段：

- 身份字段来自 `professor_records`
- `paper_count` = verified link count
- `top_papers` = top 5 verified paper titles 的 derived projection
- `quality_status` 只取明确 gate 结果

#### Paper projection payload

来源：

- `paper_records`
- `professor_paper_links(link_status = verified)` 的反向投影

对外字段：

- `canonical_title / clean_title / doi / arxiv_id / authors / venue / year`
- 兼容期内可保留 `professor_ids`，但只能由 verified links 投影生成
- admin console 不再把 `professor_ids` 当事实源，而是走 `released_relationships`

#### Relation projection

`released_relationships` 至少包含：

- `source_object_id`
- `source_object_type`
- `target_object_id`
- `target_object_type`
- `relation_type`
- `relation_status`
- `rank`

#### Cutover mechanism

- SQLite cutover：通过切换 backend `RELEASED_OBJECTS_DB` 到 `released_objects_v2.db` 并重启 admin console 完成
- Milvus cutover：通过 collection alias 切换到新的 vector collections
- rollback：切回旧 DB path 与旧 Milvus alias；不恢复整个 shared DB 文件

## Vector Redesign

### Current Problem

当前向量层有两套不足：

- `apps/miroflow-agent/src/data_agents/storage/milvus_store.py`
  - 通用 hash embedding，语义质量弱
- `apps/miroflow-agent/src/data_agents/professor/vectorizer.py`
  - 建立在错误 professor contract 上

### Proposed Collections

#### `professor_identity_vectors`

用途：按人找对老师。

输入文本：

- `name`
- `name_en`
- `institution`
- `department`
- `title`
- `profile_summary`

元字段：

- `professor_id`
- `quality_status`
- `discipline_bucket`
- `institution`

#### `professor_research_vectors`

用途：按研究方向和代表论文找老师。

输入文本：

- `research_directions`
- `verified paper titles`
- `profile_summary`

元字段：

- `professor_id`
- `quality_status`
- `institution`
- `discipline_bucket`

#### `paper_semantic_vectors`

用途：按标题/摘要找 canonical paper。

输入文本：

- `clean_title`
- `abstract`
- `venue`
- `fields_of_study`

元字段：

- `paper_id`
- `title_quality_status`
- `year`

### Build Timing

- `professor_identity_vectors` 可以在 Phase 1 后开始构建
- `professor_research_vectors` 必须等 Phase 3 verified link pipeline 产出后再构建
- `paper_semantic_vectors` 在 Phase 2 canonical paper release 完成后构建
- 旧 vector collections 在 Phase 6 通过前不能删除
- Phase 6 cutover 后至少保留一轮 soak period，再删除旧 collections

### Query Routing

因为 workbook 风格问题经常同时包含身份线索和研究线索，所以 professor 向量检索不能只打一侧 collection。

默认路由：

1. exact / filter / relational constraints 先跑
2. `professor_identity_vectors` 与 `professor_research_vectors` 双查
3. 结果在应用层做 merge + rerank
4. mixed query rerank 时，identity match 权重大于 research semantic similarity

纯论文问题：

- 先查 `paper_semantic_vectors`
- 再回 relational 层反查 `verified professor_paper_links`

## New Ready Gate For STEM

STEM `ready` 必须同时满足：

1. `identity_clean_passed`
2. `content_clean_passed`
3. `verified_scholarly_output_passed`

### Identity Clean

- 人名正确
- 学校正确
- title 没有错槽
- department 没有错槽
- 至少一个官方锚点

### Content Clean

- `profile_summary` 非模板
- `evaluation_summary` 非模板
- 关键字段带 provenance

### Verified Scholarly Output

至少一个：

- `>=1` 条 `verified professor_paper_link`
- 或官方 publication list 抽出的成果，经验证可归属于该教授

这里的第二条必须明确成操作规则：

- 不是“页面上出现论文二字就算”
- 必须是 official publication block / personal homepage / lab page / official-linked CV 中抽到的标题级成果
- 且经规则或 LLM 验证为该教授成果

这是明确的产品 tradeoff：

- 新入职或转产业的 STEM 教师可能暂时没有外部索引论文
- 当前阶段宁可把这类对象留在 `needs_review / needs_enrichment`
- 也不接受把弱证据论文强行写成 `ready`

### Quality Gate Interface

新的 STEM gate 不直接从 DB 查 link，而是消费 pipeline 传入的 verified relation summary。

最小输入：

- `verified_link_count`
- `verified_publication_titles`
- `verified_evidence_sources`

最小规则：

- `verified_link_count >= 1` 才能让 STEM 通过 `verified_scholarly_output_passed`
- `top_papers` 只能作为 derived display field，不再作为 gate 的事实源

## LLM Role Redesign

### Current weakness

LLM 主要用于：

- homepage 结构化抽取
- summary 生成

### New LLM components

#### `slot_cleaner`

判断：

- `name`
- `title`
- `department`
- `field validity`
- `suspicious_fields`

输出 contract：

- `clean_name`
- `clean_title`
- `clean_department`
- `discipline_bucket`
- `invalid_fields`
- `confidence`
- `reasoning`

#### `paper_link_verifier`

判断候选论文是：

- `verified`
- `candidate`
- `rejected`

并给出：

- `why`
- `evidence_span`

输出 contract：

- `verdict`
- `confidence`
- `evidence_url`
- `evidence_span`
- `matched_author_name`
- `reasoning`

动作映射：

- `confidence >= 0.85` 且 evidence 来自真实已访问页面 -> `verified`
- `0.60 <= confidence < 0.85` -> `candidate`
- `< 0.60` -> `rejected`

防 hallucination 规则：

- `evidence_url` 必须属于当前 pipeline 已访问 URL 集合
- LLM 生成了未访问 URL 时，结果自动降级为 `candidate`

#### `release_judge`

输入 clean professor + verified link summary，输出：

- `quality_status`
- `blocking_reasons`

输出 contract：

- `quality_status`
- `blocking_reasons`
- `warnings`
- `confidence`

最低要求：

- `release_judge` 不能单独把对象抬成 `ready`
- 它只能在规则 gate 通过后做二次清洗和 blocking reason 归因

## School Adapter Strategy

继续采用：

- `统一主链 + 学校级 adapter`

优先学校：

- `*.sustech.edu.cn`
- `*.sigs.tsinghua.edu.cn`
- `*.cuhk.edu.cn`
- `*.sysu.edu.cn`
- `*.sztu.edu.cn`
- `*.suat-sz.edu.cn`
- `*.hitsz.edu.cn`

adapter 职责：

- roster page extraction
- detail page extraction
- direct homepage discovery
- publication block discovery
- official-linked ORCID/CV/Scholar extraction

## Reset Strategy

### Keep

- `docs/教授 URL.md`
- 原始 HTML / markdown / crawl logs
- E2E reports
- school adapters and discovery rules

### Reset

- shared `professor` domain
- shared `paper` domain
- old `paper.professor_ids` strong relations
- old professor vector collections
- old paper vector collections if they depend on dirty titles

### Backup And Rollback

执行 reset 前必须产出：

- `logs/data_agents/reset_snapshots/<date>/released_objects.db`
- `logs/data_agents/reset_snapshots/<date>/milvus_snapshot_manifest.json`
- `logs/data_agents/reset_snapshots/<date>/git_sha.txt`
- `logs/data_agents/reset_snapshots/<date>/stem_phase6_school_list.json`
- `logs/data_agents/reset_snapshots/<date>/rollback_thresholds.json`

rollback 条件：

- `projected_stem_professor_count < 0.90 * phase6_discovered_stem_professor_count`
- `ready_stem_professor_count < 0.60 * phase6_discovered_stem_professor_count`
- `critical_workbook_subset_pass_rate < 1.0`
- `false_positive_verified_paper_link_count > 0`
- admin console 无法稳定返回 professor/paper relation 结果

rollback 动作：

- 切回旧 `released_objects.db`
- 切回旧 Milvus collection alias
- 新 canonical/projection DB 停止 serving，但保留以便诊断

Milvus 备份机制固定为：

- 优先使用已部署的 Milvus backup tooling
- 若环境没有该工具，Unit A 必须先交付 `export_milvus_collection.py`
- destructive reset 前，必须完成 vector + metadata JSONL export

## Implementation Units

### Unit A. Canonical schema and storage layer

Files:

- `apps/miroflow-agent/src/data_agents/contracts.py`
- `apps/miroflow-agent/src/data_agents/storage/sqlite_store.py`
- `apps/miroflow-agent/src/data_agents/storage/milvus_store.py`
- `apps/miroflow-agent/scripts/export_milvus_collection.py`
- `docs/Data-Agent-Shared-Spec.md`

Tests:

- `apps/miroflow-agent/tests/data_agents/storage/test_sqlite_store.py`
- `apps/miroflow-agent/tests/data_agents/storage/test_milvus_store.py`
- `apps/miroflow-agent/tests/data_agents/test_contracts.py`

### Unit B. STEM professor release contract

Files:

- `apps/miroflow-agent/src/data_agents/professor/publish_helpers.py`
- `apps/miroflow-agent/src/data_agents/professor/quality_gate.py`
- `apps/miroflow-agent/src/data_agents/professor/pipeline_v3.py`
- `apps/miroflow-agent/scripts/run_professor_publish_to_search.py`

Tests:

- `apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_publish_helpers.py`
- `apps/miroflow-agent/tests/scripts/test_run_professor_publish_to_search.py`

### Unit C. Paper canonicalization and sanitizer

Files:

- `apps/miroflow-agent/src/data_agents/paper/release.py`
- `apps/miroflow-agent/src/data_agents/paper/crossref.py`
- `apps/miroflow-agent/src/data_agents/paper/openalex.py`
- `apps/miroflow-agent/src/data_agents/paper/semantic_scholar.py`
- `apps/miroflow-agent/src/data_agents/paper/doi_enrichment.py`

Tests:

- `apps/miroflow-agent/tests/data_agents/paper/test_release.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_crossref.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_title_sanitizer.py`

### Unit D. Verified professor-paper linking

Files:

- `apps/miroflow-agent/src/data_agents/professor/paper_collector.py`
- `apps/miroflow-agent/src/data_agents/paper/models.py`
- `apps/miroflow-agent/src/data_agents/paper/hybrid.py`
- `apps/miroflow-agent/src/data_agents/paper/orcid.py`
- `apps/miroflow-agent/src/data_agents/paper/cv_pdf.py`
- `apps/miroflow-agent/src/data_agents/paper/google_scholar_profile.py`

Tests:

- `apps/miroflow-agent/tests/data_agents/professor/test_paper_collector.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_openalex.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_semantic_scholar.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_orcid.py`

### Unit E. School adapter expansion for STEM

Files:

- `apps/miroflow-agent/src/data_agents/professor/school_adapters.py`
- `apps/miroflow-agent/src/data_agents/professor/discovery.py`
- `apps/miroflow-agent/src/data_agents/professor/roster.py`
- `apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py`

Tests:

- `apps/miroflow-agent/tests/data_agents/professor/test_school_adapters.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_roster_validation.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_homepage_crawler.py`

### Unit F. Admin console backend serving migration

Files:

- `apps/admin-console/backend/api/domains.py`
- `apps/admin-console/backend/api/dashboard.py`
- `apps/admin-console/backend/deps.py`

Tests:

- `apps/admin-console/backend/tests/test_domains.py`
- `apps/admin-console/backend/tests/test_dashboard.py`

### Unit G. Synthetic integration harness

Files:

- `apps/miroflow-agent/tests/integration/test_professor_paper_reset_pipeline.py`
- `apps/miroflow-agent/tests/fixtures/professor_reset_pipeline/`

Tests:

- 全链 synthetic fixture：`discovery -> enrichment -> paper canonicalization -> verified linking -> gate -> projection`

## Sequencing

### Phase 0. Design lock

- finalize this plan
- run local Claude cross-review
- incorporate grounded findings

### Phase 0.5. Backup and serving migration prep

- snapshot current shared SQLite
- snapshot/export Milvus collections
- define projection switch path
- define rollback thresholds
- freeze Phase 6 STEM school list

### Phase 1. Reset and storage foundation

- canonical schema
- relation model
- build new tables in parallel with old serving projection

### Phase 2. Paper canonicalization

- title sanitizer
- canonical paper release

### Phase 3. Verified link pipeline

- official publication
- official-linked ORCID/CV/Scholar
- school-matched OpenAlex

### Phase 4. STEM ready gate

- slot validity
- summary validity
- verified scholarly output requirement

### Phase 5. School adapter expansion

- cover only the Shenzhen STEM priority schools in `stem_phase6_school_list.json`

### Phase 5.5. Synthetic integration gate

- full synthetic professor-paper pipeline pass
- relation projection pass
- admin console backend relation API pass

### Phase 6. Real E2E acceptance

- rebuild shared store
- run real `docs/教授 URL.md` STEM slice
- validate in admin console and workbook-style queries

Phase dependency：

- Phase 6 MUST NOT start until Phase 5 and Phase 5.5 complete for every school in the Phase 6 STEM slice

## Real E2E Acceptance Standard

Completion is defined by real data only.

Required evidence:

1. real `docs/教授 URL.md` STEM slice E2E report
2. shared store professor refresh report
3. shared store paper refresh report
4. admin console spot-check payload checks
5. workbook-style query validation on professor/paper questions
6. synthetic integration report for the new canonical + projection pipeline

Minimum pass conditions:

- bad cases like `NAKAMURA, Satoshi`, `Ercan Engin Kuruoğlu`, `唐博` no longer appear as false `ready`
- polluted `title` and template summaries are blocked
- wrong-author papers no longer appear under professor detail
- official-homepage publication-rich STEM teachers surface verified papers
- paper title sanitizer removes current known corruption classes
- workbook-style professor/paper questions can be answered from final results without hand patching

Suggested quantitative gate:

- targeted workbook critical subset (`q1 professor identity`, `q6 paper relation`, `q9 professor profile`): `100%` pass
- sampled STEM professor detail pages with verified paper relations: `0` known false-positive relation
- no polluted title / template summary sample may remain `ready`
- projected STEM professor count: `>= 90%` of Phase 0.5 discovered base
- ready STEM professor count: `>= 60%` of Phase 0.5 discovered base

## Review Target

This plan should be reviewed by local Claude with focus on:

- schema soundness
- reset safety
- relation design correctness
- vector scope correctness
- whether the workbook-answerability target is reflected strongly enough
