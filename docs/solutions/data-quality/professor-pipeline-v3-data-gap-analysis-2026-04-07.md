# Professor Pipeline V3 数据缺口分析

- **日期**: 2026-04-07
- **范围**: 9 校 E2E（limit=5）共 43 条 enriched profiles
- **目的**: 分析当前教授数据收集的完整性缺口，定位根因，提出修复方案

## 1. 数据完整性总览

基于 43 条 enriched profile 的字段填充率统计：

| 字段 | 填充数 | 填充率 | 评级 |
|------|--------|--------|------|
| name | 43 | 100% | ✓ 完整 |
| institution | 43 | 100% | ✓ 完整 |
| homepage | 42 | 98% | ✓ 完整 |
| profile_summary | 43 | 100% | ✓ 完整 |
| department | 33 | 77% | △ 待改善 |
| research_directions | 30 | 70% | △ 待改善 |
| work_experience | 26 | 60% | △ 待改善 |
| academic_positions | 26 | 60% | △ 待改善 |
| paper_count | 23 | 53% | △ 待改善 |
| title | 21 | 49% | △ 待改善 |
| email | 19 | 44% | △ 待改善 |
| education_structured | 17 | 40% | △ 待改善 |
| awards | 15 | 35% | △ 待改善 |
| **name_en** | **0** | **0%** | **✗ 致命缺失** |
| **top_papers** | **0** | **0%** | **✗ 致命缺失** |
| **h_index** | **2** | **5%** | **✗ 致命缺失** |
| **citation_count** | **2** | **5%** | **✗ 致命缺失** |
| **evaluation_summary** | **0** | **0%** | **✗ 代码bug** |
| **patent_ids** | **0** | **0%** | ✗ 跨域未联动 |
| **projects** | **1** | **2%** | ✗ 来源稀缺 |
| company_roles | 5 | 12% | ✗ 跨域未联动 |
| office | 3 | 7% | ✗ 来源稀缺 |

## 2. 致命问题分析

### 问题 A：论文数据完全为空（top_papers=0%, h_index=5%）

**根因链路**:
1. `paper_collector.py` 调用 `academic_tools.collect_papers()`
2. `collect_papers()` 用 `search_name = name_en or name` 决定搜索名
3. `name_en` 在所有 43 条 profile 中**均为空**
4. 因此实际用**中文名**去搜索 Semantic Scholar / DBLP / arXiv
5. 这三个 API 全部是英文索引，中文名搜索返回 0 结果

**验证**:
```
DBLP "潘毅" → 0 results
DBLP "Yi Pan" → 15,656 results
Semantic Scholar "吴亚北" → 0 results
```

**`name_en` 为空的根因**:
- Pipeline V3 各阶段均**未实现** `name_en` 的提取或生成：
  - `discovery.py` — 不处理 name_en
  - `roster.py` — 不处理 name_en
  - `homepage_crawler.py` — 不处理 name_en
  - `agent_enrichment.py` — 不处理 name_en
  - `web_search_enrichment.py` — 不处理 name_en
- `name_en` 字段在 `models.py:114` 定义为 `str | None = None`，从未被任何阶段赋值

**影响范围**:
- 论文数据（top_papers, h_index, citation_count）完全失效
- 基于论文的研究方向聚类（paper_driven directions）完全失效
- Paper staging records（跨域论文关联）完全失效

### 问题 B：evaluation_summary 被硬编码为空

**根因**: `pipeline_v3.py:404`:
```python
# Stage 7: LLM Summary
summaries = await generate_summaries(profile=profile, ...)
profile = profile.model_copy(update={
    "profile_summary": summaries.profile_summary,
    "evaluation_summary": "",  # ← BUG: 丢弃了已生成的 evaluation_summary
})
```

`generate_summaries()` 实际会返回 `GeneratedSummaries(profile_summary=..., evaluation_summary=...)`，但 pipeline 用空字符串覆盖了 `evaluation_summary`。

**修复**: 改为 `"evaluation_summary": summaries.evaluation_summary`

### 问题 C：SUSTech 异常——Agent 和 Web Search 均未触发

E2E 报告显示 SUSTech 的 agent_triggered=0, web_search_count=0，而其他 8 校均正常触发。

**可能原因**:
- SUSTech 的 homepage crawler 直接抓取到较完整的数据（官网结构良好），completeness assessment 判定无需 agent 补全
- 无 agent enrichment → 数据仍不足但未达触发 web search 的条件
- 需要检查 completeness assessment 的阈值是否合理

## 3. 中等优先级问题

### 3.1 department 填充率 77%

10 条 profile 缺少院系信息，主要来自：
- 官网列表页只有姓名、无院系
- Regex 提取未覆盖某些高校的 HTML 结构

### 3.2 title（职称）填充率 49%

22 条 profile 无职称，原因：
- 部分高校列表页不展示职称
- Homepage crawler 提取的 HTML 中职称字段格式多样

### 3.3 email 填充率 44%

24 条无邮箱，部分高校出于反爬/隐私保护不在公开页面展示邮箱。

### 3.4 education_structured 填充率 40%

教育背景结构化提取需要 agent enrichment 或 homepage 页面包含详细简历，数据来源有限。

## 4. 跨域联动问题

### 4.1 patent_ids = 0%

专利关联需要 patent 域数据先导入，且需姓名+机构匹配。当前 E2E 仅跑了 professor 域，未联动 patent 数据。属于流程问题，非 bug。

### 4.2 company_roles = 12%

仅 5 条有企业关联，主要来自 agent enrichment 提取。company linking 阶段需要 company 域数据配合。

## 5. 修复方案优先级

### P0（必须修复，影响核心数据质量）

| 编号 | 问题 | 修复方案 | 复杂度 |
|------|------|----------|--------|
| A-1 | `name_en` 从未被提取 | 在 homepage_crawler 或 agent_enrichment 阶段增加英文名提取；或在 Stage 2b 之前增加翻译阶段 | 中 |
| A-2 | 学术 API 仅支持英文名 | 提取 `name_en` 后，`collect_papers()` 自然修复 | 依赖 A-1 |
| B-1 | `evaluation_summary` 被硬编码为空 | 修改 `pipeline_v3.py:404`，使用 `summaries.evaluation_summary` | 低 |

### P1（应修复，影响数据完整度）

| 编号 | 问题 | 修复方案 |
|------|------|----------|
| C-1 | SUSTech agent 未触发 | 检查 completeness assessment 阈值 |
| D-1 | department/title 填充率不足 | 在 agent enrichment prompt 中强调提取 |
| D-2 | email 填充率不足 | Homepage 页面专项提取 + web search 补全 |

### P2（可优化，非阻塞）

| 编号 | 问题 | 修复方案 |
|------|------|----------|
| E-1 | education_structured 填充率低 | Agent enrichment prompt 优化 |
| E-2 | 跨域联动（patent/company） | 需先完成各域 E2E，再跑跨域 linking |

## 6. `name_en` 提取方案选型

### 方案 1: Homepage 页面提取（推荐）

许多中国高校教授主页同时标注中英文姓名。在 `homepage_crawler.py` 的 HTML 解析中，通过 regex 或 LLM 提取英文名。

**优势**: 准确、有证据可溯源
**劣势**: 并非所有主页有英文名

### 方案 2: Agent Enrichment 提取

在 `agent_enrichment.py` 的 prompt 中，增加 `name_en` 为必提取字段。Agent 可以从页面上下文推断英文名。

**优势**: 可同时补全其他字段
**劣势**: 取决于 agent 质量

### 方案 3: LLM 翻译

在 Stage 2b 之前，用 LLM 将中文名翻译为拼音英文名（如 "吴亚北" → "Yabei Wu"）。

**优势**: 实现简单，覆盖率 100%
**劣势**: 拼音翻译可能与学术发表名不一致（有些学者用非标准拼写、缩写等）

### 推荐方案: 方案 1+3 组合

1. 优先从 homepage 提取真实英文名（方案 1）
2. 如果提取不到，fallback 到 LLM 拼音翻译（方案 3）
3. 翻译后在 Semantic Scholar 中搜索验证名字是否匹配

## 7. Semantic Scholar Rate Limiting

E2E 期间 Semantic Scholar API 返回 429（Rate Limited）。当前实现：
- 无 API Key（匿名调用，限制更严格）
- 请求间隔 `crawl_delay=2.0s`（可能不够）
- 无重试机制

**建议**:
- 注册 Semantic Scholar API Key（免费，提高配额）
- 增加 exponential backoff 重试
- 考虑 OpenAlex 作为替代/补充源（免费、无 rate limit）

## 8. 各阶段效果评估

| 阶段 | 功能 | 当前状态 |
|------|------|----------|
| Stage 1: Discovery | 从高校官网发现教师列表 | ✓ 正常 |
| Stage 2: Regex Extract | 从列表页提取基本信息 | △ 可改善 |
| Stage 2.1: Direction Cleaning | 研究方向清洗 | ✓ 正常 |
| Stage 3: Homepage Crawl | 抓取教师主页详细信息 | △ 未提取 name_en |
| Stage 2b: Paper Collection | 从学术 API 收集论文 | **✗ 完全失效** |
| Stage 2c: Agent Enrichment | LLM Agent 补全缺失字段 | △ 未要求 name_en |
| Stage 5: Web Search | 网络搜索补全 + 身份验证 | ✓ 正常（SUSTech 除外）|
| Stage 6: Company Linking | 企业关联验证 | △ 依赖 company 域数据 |
| Stage 7: Summary | LLM 生成摘要 | **△ evaluation_summary 被丢弃** |
| Stage 8: Quality Gate | 质量评估 + Release | ✓ 正常 |

## 9. 下一步行动项

1. **[立即]** 修复 `evaluation_summary` bug（pipeline_v3.py:404）
2. **[短期]** 实现 `name_en` 提取（homepage + LLM 翻译 fallback）
3. **[短期]** 修复后重跑 E2E，验证论文数据可正常收集
4. **[中期]** 注册 Semantic Scholar API Key
5. **[中期]** 评估 OpenAlex 作为补充学术数据源
6. **[中期]** 调查 SUSTech agent/web_search 未触发原因
7. **[长期]** 跨域联动（patent + company linking）
