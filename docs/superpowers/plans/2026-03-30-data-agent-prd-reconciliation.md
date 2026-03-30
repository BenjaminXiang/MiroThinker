# Data Agent PRD Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the shared spec, top-level product PRD, and domain PRDs so they all align to the approved multi-DB `PostgreSQL + Milvus` architecture, professor-anchored paper pipeline, workbook-aligned answer behavior, and the new patent-agent scope.

**Architecture:** Apply a contract-first rewrite. Update the shared spec first so it becomes the canonical cross-domain contract source, then align the top-level product PRD to the approved answer and routing behavior, then update each domain PRD to match the shared contract and its approved collection strategy. Finish with a cross-document sweep that removes stale assumptions like single-DB `pgvector`, mandatory `credit_code`, and `企名片 API` as the primary enterprise backbone.

**Tech Stack:** Markdown PRDs, Git, `rg`, `sed`, `apply_patch`

---

## Current State

### Approved Inputs

- The design baseline is [2026-03-30-data-agent-prd-reconciliation-design.md](/home/longxiang/MiroThinker/docs/superpowers/specs/2026-03-30-data-agent-prd-reconciliation-design.md).
- The workbook [测试集答案.xlsx](/home/longxiang/MiroThinker/docs/测试集答案.xlsx) remains the target answer-style and scenario source, while factual knowledge must remain verifiable and current.
- The paper domain is now explicitly professor-anchored: the periodic paper pipeline starts from the Shenzhen professor roster and linked papers help keep professor profiles fresh.

### Current Code Baseline

These PRD rewrites must reflect the current MiroThinker codebase rather than invent a separate agent runtime:

- `apps/miroflow-agent/src/core/pipeline.py` already provides the reusable task-execution entrypoint that wires `ToolManager`, `Orchestrator`, and `OutputFormatter`.
- `apps/miroflow-agent/src/core/orchestrator.py` already provides the multi-turn agent loop, context-compression support, rollback handling, and duplicate-query protection that make the project relevant to data-collection agents.
- `apps/miroflow-agent/src/core/tool_executor.py` already includes practical tool-call fixes, duplicate query tracking, empty-search rollback, and result post-processing behavior.
- `apps/miroflow-agent/src/config/settings.py` already maps Hydra agent configs to MCP servers for `search_and_scrape_webpage`, `jina_scrape_llm_summary`, `tool-python`, and related tools.
- `apps/miroflow-agent/conf/agent/mirothinker_1.7_keep5_max200.yaml` already encodes the high-performing long-horizon single-agent pattern: search + scrape/extract + python with context compression.
- `libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/search_and_scrape_webpage.py` already implements the practical web-search layer with retries, Serper/Sogou support, and banned-source filtering.
- `libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/jina_scrape_llm_summary.py` already implements scrape-then-extract behavior with Jina and Python fallback, which is directly relevant to data cleaning and information extraction tasks.
- `apps/miroflow-agent/benchmarks/common_benchmark.py` and the BrowseComp-ZH scripts already provide a reusable evaluation harness pattern for task execution, logging, and repeated runs.

### Why This Project Context Matters

The reason to place these data-agent PRDs inside MiroThinker is not only documentation convenience.

The project already contains:

- a benchmark-proven search-and-browse agent loop
- reusable tool orchestration for search, scraping, extraction, and Python normalization
- logging and evaluation patterns proven on BrowseComp-ZH-style tasks

Therefore, the rewritten PRDs should describe how professor / company / paper / patent collection agents can be implemented as domain-specific adaptations of the current MiroThinker stack, rather than as a totally separate greenfield system.

### Files To Modify

- Modify: `docs/Data-Agent-Shared-Spec.md`
- Modify: `docs/Agentic-RAG-PRD.md`
- Modify: `docs/Company-Data-Agent-PRD.md`
- Modify: `docs/Professor-Data-Agent-PRD.md`
- Modify: `docs/Paper-Data-Agent-PRD.md`
- Create: `docs/Patent-Data-Agent-PRD.md`

### Cross-Document Rewrite Rules

- Replace long-term `PostgreSQL + pgvector` assumptions with `PostgreSQL + Milvus`.
- Replace single-DB assumptions with domain-isolated PostgreSQL databases and Milvus collections coordinated by the service layer.
- Treat normalized company name as the primary dedupe anchor; keep `credit_code` as optional supplemental evidence.
- Treat self-built crawlers and deterministic imports as the default collection path; treat Web Search as auxiliary.
- Treat Shenzhen university official sites as the professor coverage anchor.
- Treat papers linked from the Shenzhen professor roster as both searchable paper objects and professor-profile freshness signals.
- Align PRD language with the existing MiroThinker implementation primitives: Hydra-configured agent runs, `Orchestrator`, `ToolManager`, MCP search/scrape tools, and Python-based cleaning utilities.
- Avoid promising a brand-new bespoke agent runtime unless the current code clearly lacks the needed capability.

## File Map

- `docs/Data-Agent-Shared-Spec.md`: canonical shared contracts, service-layer orchestration, handoff fields, quality rules
- `docs/Agentic-RAG-PRD.md`: product scope, answer behavior, query routing, cross-domain aggregation behavior
- `docs/Company-Data-Agent-PRD.md`: company ingestion, dedupe, structured key personnel, user-facing summaries
- `docs/Professor-Data-Agent-PRD.md`: professor coverage, official-source hierarchy, company linkage, paper-driven profile enrichment
- `docs/Paper-Data-Agent-PRD.md`: professor-anchored paper collection, summary generation, professor linkage and enrichment
- `docs/Patent-Data-Agent-PRD.md`: xlsx-based patent ingestion, summaries, linkage, cadence, acceptance criteria

## Code Reference Map

- `apps/miroflow-agent/src/core/pipeline.py`: existing reusable execution entrypoint for task-style agents
- `apps/miroflow-agent/src/core/orchestrator.py`: existing multi-turn reasoning and tool-use loop
- `apps/miroflow-agent/src/core/tool_executor.py`: existing tool-call execution safeguards and duplicate suppression
- `apps/miroflow-agent/src/config/settings.py`: current tool registry and environment-to-tool wiring
- `apps/miroflow-agent/conf/agent/mirothinker_1.7_keep5_max200.yaml`: current high-signal config pattern for search/scrape/python tasks
- `apps/miroflow-agent/src/utils/prompt_utils.py`: current system-prompt and summarization behavior
- `libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/search_and_scrape_webpage.py`: current search implementation
- `libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/jina_scrape_llm_summary.py`: current scrape-and-extract implementation
- `apps/miroflow-agent/benchmarks/common_benchmark.py`: current execution/evaluation harness pattern

## Out of Scope

- Implementing runtime services or database schemas in code
- Changing the workbook itself
- Building the service adapters or database migrations
- Replacing existing local crawlers or adding production ingestion code

### Task 0: Anchor The Rewrite To The Current MiroThinker Implementation

**Files:**
- Reference: `apps/miroflow-agent/src/core/pipeline.py`
- Reference: `apps/miroflow-agent/src/core/orchestrator.py`
- Reference: `apps/miroflow-agent/src/core/tool_executor.py`
- Reference: `apps/miroflow-agent/src/config/settings.py`
- Reference: `apps/miroflow-agent/conf/agent/mirothinker_1.7_keep5_max200.yaml`
- Reference: `libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/search_and_scrape_webpage.py`
- Reference: `libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/jina_scrape_llm_summary.py`
- Reference: `apps/miroflow-agent/benchmarks/common_benchmark.py`

- [ ] **Step 1: Verify the current reusable agent loop and tool stack**

Run:

```bash
sed -n '1,220p' apps/miroflow-agent/src/core/pipeline.py
sed -n '1,260p' apps/miroflow-agent/src/core/orchestrator.py
sed -n '1,240p' apps/miroflow-agent/src/core/tool_executor.py
sed -n '1,360p' apps/miroflow-agent/src/config/settings.py
sed -n '1,120p' apps/miroflow-agent/conf/agent/mirothinker_1.7_keep5_max200.yaml
```

Expected:

```text
The code shows an existing Hydra-configured agent runtime with multi-turn orchestration, MCP tool wiring, search/scrape/python tools, and context-compression controls.
```

- [ ] **Step 2: Verify the current search and extract implementations**

Run:

```bash
sed -n '1,260p' libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/search_and_scrape_webpage.py
sed -n '1,260p' libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/jina_scrape_llm_summary.py
```

Expected:

```text
The code shows retrying web search, scraping, extraction, banned-source filtering, and Python fallback logic that can be reused by data agents.
```

- [ ] **Step 3: Verify the benchmark/evaluation context that motivates reuse**

Run:

```bash
sed -n '1,120p' README.md
sed -n '1,220p' apps/miroflow-agent/benchmarks/common_benchmark.py
sed -n '1,120p' apps/miroflow-agent/conf/benchmark/browsecomp_zh.yaml
sed -n '1,200p' apps/miroflow-agent/scripts/run_evaluate_multiple_runs_browsecomp_zh.sh
```

Expected:

```text
The repository documents strong BrowseComp-ZH performance and already contains a reusable benchmark runner pattern that justifies grounding the PRDs in the current MiroThinker stack.
```

- [ ] **Step 4: Carry these implementation constraints into every PRD rewrite**

Use this constraint text while editing the docs:

```md
- 数据采集 Agent 优先复用当前 MiroThinker 的 agent runtime，而不是另起一套 orchestration
- 搜索优先映射到 search_and_scrape_webpage / Sogou / Serper 能力
- 网页/PDF 抽取优先映射到 jina_scrape_llm_summary
- 规则化清洗、标准化、去重辅助处理优先映射到 tool-python 与离线脚本
- 日志、验证、批量执行方式优先复用现有 benchmark / pipeline 模式
```

### Task 1: Rewrite The Shared Spec As The Canonical Contract Source

**Files:**
- Modify: `docs/Data-Agent-Shared-Spec.md`

- [ ] **Step 1: Capture the stale assumptions that must be removed**

Run:

```bash
rg -n "pgvector|单库|企名片 API|credit_code|PostgreSQL \\+ pgvector|SQL 示例" docs/Data-Agent-Shared-Spec.md
```

Expected:

```text
Matches appear in the current file and identify the sections that still encode the old architecture.
```

- [ ] **Step 2: Rewrite the architecture and dependency sections around multi-DB `PostgreSQL + Milvus`**

Insert or rewrite these concepts in `docs/Data-Agent-Shared-Spec.md`:

```md
## 一、整体架构

- 长期架构统一为 PostgreSQL + Milvus
- 教授、企业、论文、专利可各自独立 PostgreSQL 库与 Milvus collection
- 线上服务层负责查询编排、多源召回、结果融合、rerank
- 不要求各域底层物理 schema 完全一致，但必须遵守统一对外契约字段
```

- [ ] **Step 3: Replace the single physical schema framing with logical contract sections**

Add sections that define:

```md
## 三、共享逻辑契约

- 统一 ID 规则：PROF-* / COMP-* / PAPER-* / PAT-*
- 统一对外字段：id、主展示字段、summary 字段、evidence/source、last_updated
- 统一过滤语义：institution、industry、year_range、patent_type、key_person education filters
- 统一服务接口语义：多源召回、结果融合、rerank 输入输出契约
```

- [ ] **Step 4: Remove stale company and paper assumptions from the shared spec**

Ensure the rewritten file says:

```md
- 企业主数据骨架来自企名片导出 xlsx，不再把企名片 API 作为主采集路径
- 公司去重主锚点是标准化公司名称，credit_code 为可选补充字段
- 论文周期性采集范围以深圳教授 roster 为锚点
- 论文既是独立检索对象，也是教授画像更新信号
- 当前实现映射优先复用 MiroThinker 的 `pipeline.py`、`Orchestrator`、`search_and_scrape_webpage`、`jina_scrape_llm_summary`、`tool-python`
```

- [ ] **Step 5: Verify the shared spec no longer claims the old architecture**

Run:

```bash
rg -n "PostgreSQL \\+ pgvector|单库|credit_code\\s+TEXT NOT NULL UNIQUE|企名片 API.*主|一条 SQL 实现多路召回" docs/Data-Agent-Shared-Spec.md
```

Expected:

```text
No matches for the removed long-term assumptions.
```

- [ ] **Step 6: Commit the shared-spec rewrite**

Run:

```bash
git add docs/Data-Agent-Shared-Spec.md
git commit -m "Rewrite shared data-agent contract spec"
```

Expected:

```text
A commit is created containing only the shared spec rewrite.
```

### Task 2: Align The Top-Level Product PRD To The Approved Query And Answer Model

**Files:**
- Modify: `docs/Agentic-RAG-PRD.md`

- [ ] **Step 1: Rewrite the product-level architecture language so it matches service-layer orchestration**

Add or revise wording in `docs/Agentic-RAG-PRD.md` so it states:

```md
- 线上服务面向多库多 collection 编排查询
- 查询链路包含多源召回、结果融合、rerank
- 不假设所有数据都在单一关系库中
- 数据采集侧能力建设以复用当前 MiroThinker agent stack 为前提
```

- [ ] **Step 2: Remove stale product assumptions about enterprise data acquisition**

Revise the enterprise module so it no longer depends on:

```md
- 企名片 API 作为企业主数据 backbone
- 用户查看企业详情时默认实时调用企名片 API 获取基础信息
```

Replace with:

```md
- 企业主数据以周期性导入和自建爬虫补全为主
- 实时外部检索只作为补充或事实校验路径
```

- [ ] **Step 3: Align paper-module behavior with the professor-anchored periodic scope**

Ensure the PRD explicitly says:

```md
- 周期性 paper 数据来自深圳教授 roster 关联论文
- 任意显式论文标题查询可走服务层实时外部 fallback
- paper 结果也用于补全教授最近研究方向
```

- [ ] **Step 4: Verify approved answer behavior remains explicit**

Run:

```bash
rg -n "歧义|另一家|来源|时效|fallback|论文标题|黄赌毒" docs/Agentic-RAG-PRD.md
```

Expected:

```text
The file contains explicit wording for ambiguity handling, conditional source disclosure, realtime fallback, and the approved narrow local-safety exception.
```

- [ ] **Step 5: Commit the top-level PRD rewrite**

Run:

```bash
git add docs/Agentic-RAG-PRD.md
git commit -m "Align top-level Agentic RAG PRD"
```

Expected:

```text
A commit is created containing only the top-level PRD rewrite.
```

### Task 3: Rewrite The Company Agent PRD Around Xlsx Backbone And Searchable Summaries

**Files:**
- Modify: `docs/Company-Data-Agent-PRD.md`

- [ ] **Step 1: Rewrite the source-of-truth and dedupe sections**

Make `docs/Company-Data-Agent-PRD.md` say:

```md
- 企业骨架数据主来源是企名片导出 xlsx
- 自建爬虫为主，Web Search 为辅助
- 公司主去重锚点是标准化公司名称
- credit_code 是补充校验字段，不是必填主键
- 采集与清洗优先复用现有 MiroThinker search/scrape/python 工具链
```

- [ ] **Step 2: Expand the data model to require user-facing summary fields and searchable key personnel**

Add or strengthen these requirements:

```md
- 必要摘要字段：profile_summary、evaluation_summary、technology_route_summary
- key_personnel 为可检索结构化字段
- key_personnel 至少包含：name、role、education_structured、work_experience、description
```

- [ ] **Step 3: Replace any `pgvector` or single-store wording with domain-store wording**

Use wording like:

```md
- 企业 Agent 维护企业域 PostgreSQL 库与 Milvus collection
- 向服务层暴露统一对外契约字段，而非要求与其他域共享物理 schema
```

- [ ] **Step 4: Verify the company PRD no longer treats `credit_code` as the primary identity**

Run:

```bash
rg -n "credit_code|pgvector|企名片 API" docs/Company-Data-Agent-PRD.md
```

Expected:

```text
Any remaining mentions frame credit_code as optional and avoid describing 企名片 API as the primary backbone or pgvector as the long-term architecture.
```

- [ ] **Step 5: Commit the company PRD rewrite**

Run:

```bash
git add docs/Company-Data-Agent-PRD.md
git commit -m "Rewrite company data-agent PRD"
```

Expected:

```text
A commit is created containing only the company PRD rewrite.
```

### Task 4: Rewrite The Professor Agent PRD Around Official Sources And Paper-Driven Freshness

**Files:**
- Modify: `docs/Professor-Data-Agent-PRD.md`

- [ ] **Step 1: Strengthen professor coverage and source hierarchy**

Make the PRD state:

```md
- 教授覆盖目标是深圳高校教授
- 主来源是深圳各高校官网、教师目录、教师主页
- Scholar、个人主页、Web Search 都是辅助补充与验证源
- 当前实现优先复用 MiroThinker 单智能体 search + scrape/extract + python 清洗链路
```

- [ ] **Step 2: Remove old company-linkage dependence on `企名片 API`**

Rewrite the linkage section so it says:

```md
- 教授 company_roles 主要来自企业库匹配与公开网页证据
- 必要时可用 Web Search 做辅助确认
- 不再要求 Phase 1 依赖企名片 API 作为主关联路径
```

- [ ] **Step 3: Make paper-derived signals a required freshness input**

Add explicit wording:

```md
- 论文从深圳教授 roster 出发采集并与教授建立关联
- 论文用于精细化 research_directions
- 论文用于更新 profile_summary 与 recent research understanding
- 当官网简介滞后时，以已验证 paper 信号补强教授画像
```

- [ ] **Step 4: Align the professor storage and outward contract wording**

Use wording like:

```md
- 教授域可独立维护 PostgreSQL 库与 Milvus collection
- 通过统一对外契约字段与服务层衔接
```

- [ ] **Step 5: Verify the professor PRD reflects the approved source order and paper-enrichment role**

Run:

```bash
rg -n "企名片 API|深圳高校|官网|research_directions|profile_summary|论文" docs/Professor-Data-Agent-PRD.md
```

Expected:

```text
The file clearly shows official Shenzhen university sources as the primary anchor, removes 企名片 API as the primary company-linkage path, and makes paper enrichment explicit.
```

- [ ] **Step 6: Commit the professor PRD rewrite**

Run:

```bash
git add docs/Professor-Data-Agent-PRD.md
git commit -m "Rewrite professor data-agent PRD"
```

Expected:

```text
A commit is created containing only the professor PRD rewrite.
```

### Task 5: Rewrite The Paper Agent PRD As A Professor-Anchored Pipeline

**Files:**
- Modify: `docs/Paper-Data-Agent-PRD.md`

- [ ] **Step 1: Rewrite the collection scope**

Make the PRD say:

```md
- 周期性论文采集从深圳教授 roster 出发
- 只采集可归属到深圳教授的论文
- 不是开放式全网论文抓取器
- 论文检索与抽取优先复用现有 search_and_scrape_webpage 与 jina_scrape_llm_summary
```

- [ ] **Step 2: Make professor linkage and enrichment a first-class responsibility**

Add or strengthen wording:

```md
- 每篇 paper 在归属置信度足够时必须关联 professor_ids
- 论文关键词、摘要、时间分布用于补全教授研究方向与最近研究重点
- paper 既是可检索对象，也是教授画像更新信号
```

- [ ] **Step 3: Keep the local summary layer and add realtime fallback wording**

Ensure the PRD says:

```md
- 保留 summary_zh 与 summary_text 作为本地回答层
- 显式论文标题但本地库缺失时，可由服务层走实时外部 fallback
```

- [ ] **Step 4: Verify the paper PRD no longer reads like an unconstrained universal crawler**

Run:

```bash
rg -n "深圳教授|professor_ids|summary_zh|summary_text|fallback|全网" docs/Paper-Data-Agent-PRD.md
```

Expected:

```text
The file shows a professor-anchored pipeline, explicit professor linkage, retained local summaries, and controlled realtime fallback.
```

- [ ] **Step 5: Commit the paper PRD rewrite**

Run:

```bash
git add docs/Paper-Data-Agent-PRD.md
git commit -m "Rewrite paper data-agent PRD"
```

Expected:

```text
A commit is created containing only the paper PRD rewrite.
```

### Task 6: Create The Patent Agent PRD

**Files:**
- Create: `docs/Patent-Data-Agent-PRD.md`

- [ ] **Step 1: Create the patent PRD skeleton with the same granularity as the other domain PRDs**

Create sections like:

```md
# 专利数据采集智能体 — 产品需求文档
## 一、定位与目标
## 二、数据来源
## 三、数据模型
## 四、采集与清洗流程
## 五、关联与摘要生成
## 六、更新策略
## 七、验收标准
```

- [ ] **Step 2: Encode the approved patent decisions**

Make the file say:

```md
- 主来源是平台导出的专利 xlsx
- 第一阶段规则是全量导入导出数据，不在入库前过窄筛选
- 需要生成用户可读摘要字段，并支持 company/professor linkage
- 专利域可独立维护 PostgreSQL 库与 Milvus collection
- 通过统一对外契约字段对接服务层
- Web Search 与网页抽取仅作为 xlsx 之外的辅助补全路径，并优先复用现有 MiroThinker 工具链
```

- [ ] **Step 3: Verify the patent PRD covers source, fields, linkage, cadence, and acceptance criteria**

Run:

```bash
rg -n "xlsx|摘要|linkage|更新|验收|PostgreSQL|Milvus" docs/Patent-Data-Agent-PRD.md
```

Expected:

```text
The file includes source assumptions, required summaries, linkage requirements, update cadence, and architecture wording.
```

- [ ] **Step 4: Commit the new patent PRD**

Run:

```bash
git add docs/Patent-Data-Agent-PRD.md
git commit -m "Add patent data-agent PRD"
```

Expected:

```text
A commit is created containing only the new patent PRD.
```

### Task 7: Run A Cross-Document Consistency Sweep

**Files:**
- Modify if needed: `docs/Data-Agent-Shared-Spec.md`
- Modify if needed: `docs/Agentic-RAG-PRD.md`
- Modify if needed: `docs/Company-Data-Agent-PRD.md`
- Modify if needed: `docs/Professor-Data-Agent-PRD.md`
- Modify if needed: `docs/Paper-Data-Agent-PRD.md`
- Modify if needed: `docs/Patent-Data-Agent-PRD.md`

- [ ] **Step 1: Scan all rewritten docs for removed assumptions**

Run:

```bash
rg -n "PostgreSQL \\+ pgvector|单库|credit_code\\s+TEXT NOT NULL UNIQUE|企名片 API.*主|依赖企名片 API|全网论文抓取" \
  docs/Data-Agent-Shared-Spec.md \
  docs/Agentic-RAG-PRD.md \
  docs/Company-Data-Agent-PRD.md \
  docs/Professor-Data-Agent-PRD.md \
  docs/Paper-Data-Agent-PRD.md \
  docs/Patent-Data-Agent-PRD.md
```

Expected:

```text
No matches for removed long-term assumptions, or only matches that explicitly describe deprecated history.
```

- [ ] **Step 2: Scan all rewritten docs for required architecture and contract terms**

Run:

```bash
rg -n "PostgreSQL \\+ Milvus|统一对外契约|结果融合|rerank|深圳教授|profile_summary|evaluation_summary|technology_route_summary|summary_zh|summary_text" \
  docs/Data-Agent-Shared-Spec.md \
  docs/Agentic-RAG-PRD.md \
  docs/Company-Data-Agent-PRD.md \
  docs/Professor-Data-Agent-PRD.md \
  docs/Paper-Data-Agent-PRD.md \
  docs/Patent-Data-Agent-PRD.md
```

Expected:

```text
Matches appear across the expected files, showing the rewritten corpus encodes the approved architecture and field requirements.
```

- [ ] **Step 3: Review the final diff before reporting completion**

Run:

```bash
git diff -- docs/Data-Agent-Shared-Spec.md docs/Agentic-RAG-PRD.md docs/Company-Data-Agent-PRD.md docs/Professor-Data-Agent-PRD.md docs/Paper-Data-Agent-PRD.md docs/Patent-Data-Agent-PRD.md
```

Expected:

```text
The diff shows a consistent contract-first rewrite with no reintroduction of old architectural assumptions.
```

- [ ] **Step 4: Commit the final reconciliation sweep**

Run:

```bash
git add docs/Data-Agent-Shared-Spec.md docs/Agentic-RAG-PRD.md docs/Company-Data-Agent-PRD.md docs/Professor-Data-Agent-PRD.md docs/Paper-Data-Agent-PRD.md docs/Patent-Data-Agent-PRD.md
git commit -m "Finalize PRD reconciliation across data agents"
```

Expected:

```text
A final consistency commit is created if any cleanup changes were needed after the sweep.
```
