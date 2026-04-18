# 教授论文数据缺失与 `ready` 误判审查报告

- **日期**: 2026-04-07
- **目标**: 解释为什么当前项目里“已完成验证/已发布”的教授对象大量没有论文数据，并给出一份可执行的修复计划

## 1. 结论摘要

本次审查的结论很明确：

1. 当前文档体系已经把“论文反哺教授画像”定义为**核心能力**，不是可选优化。
2. 当前系统的真实发布结果却是：教授对象可以在**没有 `top_papers`、没有 `paper_count`、没有 `h_index`、没有 `citation_count`** 的情况下被标成 `ready`。
3. 问题不只在论文采集失败，还在于：
   - 采集链路缺少 `name_en` 与多源学术消歧；
   - 质量门对 `ready` 的定义过宽；
   - 发布脚本和共享契约把教授域的质量状态与论文缺口进一步“压扁”了；
   - 已有论文域/多源设计没有真正接到当前教授发布链路上。
4. 如果不先修正“什么叫 ready”，即使后面补了论文采集，也还会继续把不完整对象发布成 `ready`。

## 2. 审查范围

### 2.1 文档

- `docs/Professor-Data-Agent-PRD.md`
- `docs/Paper-Data-Agent-PRD.md`
- `docs/Data-Agent-Shared-Spec.md`
- `docs/index.md`
- `docs/Professor-Pipeline-V2-User-Guide.md`
- `docs/Paper-Collection-Multi-Source-Design.md`
- `docs/plans/2026-04-05-001-feat-professor-enrichment-pipeline-v2-plan.md`
- `docs/plans/2026-04-06-002-professor-pipeline-v3-redesign.md`
- `docs/plans/2026-04-06-003-feat-professor-pipeline-v3-implementation-plan.md`
- `docs/solutions/data-quality/professor-pipeline-v3-data-gap-analysis-2026-04-07.md`

### 2.2 代码与实际产物

- `apps/miroflow-agent/src/data_agents/professor/academic_tools.py`
- `apps/miroflow-agent/src/data_agents/professor/paper_collector.py`
- `apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py`
- `apps/miroflow-agent/src/data_agents/professor/agent_enrichment.py`
- `apps/miroflow-agent/src/data_agents/professor/quality_gate.py`
- `apps/miroflow-agent/src/data_agents/professor/pipeline_v3.py`
- `apps/miroflow-agent/src/data_agents/paper/pipeline.py`
- `apps/miroflow-agent/scripts/run_professor_publish_to_search.py`
- `apps/miroflow-agent/scripts/reassess_quality.py`
- `apps/miroflow-agent/scripts/consolidate_to_shared_store.py`
- `logs/data_agents/professor/enriched.jsonl`
- `logs/data_agents/professor/search_service/professor_released_objects.jsonl`
- `logs/data_agents/released_objects.db`

## 3. 实证结果

### 3.1 文档要求已经把论文反哺定义为主路径

从文档口径看，论文并不是“锦上添花”：

- `docs/Professor-Data-Agent-PRD.md` 明确写了教授域必须支持“基于论文的教授画像更新”，并在第六节强调“论文反哺不是可选优化，而是核心能力”。
- `docs/Paper-Data-Agent-PRD.md` 的主流程明确要求：
  - 从深圳教授 roster 出发；
  - 建立教授-论文关联；
  - 反哺教授 `research_directions` / `top_papers` / `profile_summary`。
- `docs/Paper-Collection-Multi-Source-Design.md` 又进一步把问题收敛为：
  - 当前 `name_en` 缺失导致学术 API 搜索失败；
  - 目标是让 `top_papers` 覆盖率 > 80%，`h_index/citation_count` 填充率 > 70%。

也就是说，按当前文档，**没有论文数据的教授对象不应被视为“完成态”**。

### 3.2 当前全量 enriched 数据里，论文字段实际上是全空

对 `logs/data_agents/professor/enriched.jsonl` 的抽样统计结果：

```json
{
  "count": 3274,
  "name_en_nonempty": 0,
  "top_papers_nonempty": 0,
  "paper_count_nonzero": 0,
  "h_index_nonzero": 0,
  "eval_nonempty": 3274
}
```

结论：

- 当前 3274 条教授 enriched 数据里，`name_en` 完全没填；
- `top_papers`、`paper_count`、`h_index` 全部没有有效数据；
- 说明“教授主数据已经生成”，但“论文采集能力实际上没有接通”。

### 3.3 当前教授发布层把 3274 条对象全部发布成 `ready`

对 `logs/data_agents/professor/search_service/professor_released_objects.jsonl` 的统计结果：

```json
{
  "count": 3274,
  "ready": 3274,
  "needs_review": 0,
  "paper_count_nonzero": 0,
  "h_index_nonzero": 0,
  "citation_count_nonzero": 0,
  "top_papers_nonempty": 0
}
```

这说明教授搜索发布层当前出现了最核心的语义错误：

- **3274/3274 都是 `ready`**
- 但 **0/3274** 有 `top_papers`
- 也 **0/3274** 有有效 `paper_count` / `h_index` / `citation_count`

因此，当前发布层里的 `ready` 并不代表“满足教授域文档要求”，只代表“这条记录被发布了”。

### 3.3.1 不只是论文缺失，教授深字段整体也远未达到文档要求

对同一份 `logs/data_agents/professor/enriched.jsonl` 的字段覆盖率继续统计：

```json
{
  "count": 3274,
  "department": 1969,
  "title": 329,
  "email": 2058,
  "homepage": 3274,
  "research_directions": 639,
  "education_structured": 0,
  "work_experience": 0,
  "awards": 0,
  "academic_positions": 0,
  "projects": 0,
  "company_roles": 0,
  "patent_ids": 0,
  "paper_count": 0,
  "top_papers": 0
}
```

这说明当前教授数据并不是“只差论文”：

- `education_structured` / `work_experience` / `awards` / `academic_positions` / `projects` 仍然是 **0**
- `research_directions` 只有 **639/3274**
- `title` 只有 **329/3274**

也就是说，当前教授对象距离 `docs/Professor-Data-Agent-PRD.md` 和 `docs/Data-Agent-Shared-Spec.md` 里的目标状态仍有明显距离，论文缺口只是其中最醒目的一层。

### 3.4 共享库里的实际样本也存在 `ready` 但无论文数据

共享库 `logs/data_agents/released_objects.db` 中，示例对象 `PROF-CE2F7935B890`（吴亚北）当前状态是：

```json
{
  "id": "PROF-CE2F7935B890",
  "display_name": "吴亚北",
  "quality_status": "ready",
  "top_papers": [],
  "paper_count": null,
  "h_index": null,
  "citation_count": null
}
```

这与用户反馈完全一致：**已发布/已验证对象里，确实存在 `ready` 但没有任何论文数据的教授。**

### 3.5 共享库里的 `ready` 也大面积失真

对 `logs/data_agents/released_objects.db` 中教授对象的统计：

```json
{
  "total_professors": 42,
  "ready_total": 25,
  "ready_no_top_papers": 25,
  "ready_no_paper_count": 11,
  "ready_no_h_index": 24
}
```

结论：

- 共享库当前 25 条 `ready` 教授中，**25 条都没有 `top_papers`**；
- 其中多数还没有有效 `h_index`；
- 这说明问题不是个别数据点，而是**整个 ready 判定口径出了问题**。

## 4. 为什么吴亚北会被标成 `ready`

以吴亚北这类记录为例，链路大致如下：

1. `EnrichedProfessorProfile.name_en` 在当前实现中定义了，但没有任何阶段真正赋值。
2. `apps/miroflow-agent/src/data_agents/professor/academic_tools.py` 里，论文检索直接使用：

```python
search_name = name_en or name
```

3. 因为 `name_en` 为空，检索退化成中文名；当前接的源仍是 `Semantic Scholar` / `DBLP` / `arXiv`，对中文名极不稳定。
4. 论文阶段拿不到稳定结果后，后面的 agent 仍可补出较长的 `profile_summary` 与 `research_directions`。
5. `apps/miroflow-agent/src/data_agents/professor/quality_gate.py` 并不要求“有论文”才算 `ready`。
6. 最终对象进入发布层时，又被进一步固定成通用的 `ready` 语义。

因此，吴亚北被标成 `ready` 并不是因为“论文采到了但没展示”，而是因为：

- **论文没采到**
- **质量门没拦**
- **发布层继续把状态洗成了 ready**

## 5. 根因拆解

### 5.1 根因 A：论文采集前置条件缺失，`name_en` 没有打通

当前代码中：

- `apps/miroflow-agent/src/data_agents/professor/models.py` 定义了 `name_en`
- 但 `homepage_crawler.py`、`agent_enrichment.py`、`pipeline_v3.py` 当前都没有真正把它提取/生成出来

这导致 `academic_tools.collect_papers()` 的学术检索从一开始就使用了错误输入。

这也是 `docs/Paper-Collection-Multi-Source-Design.md` 已经明确指出的主根因。

### 5.2 根因 B：教授 V3 仍在走旧论文采集器，未接入新的多源方案/论文域主流程

当前 V3 教授管线仍调用：

- `apps/miroflow-agent/src/data_agents/professor/paper_collector.py`
- `apps/miroflow-agent/src/data_agents/professor/academic_tools.py`

而不是走文档里已经规划好的：

- OpenAlex 为主的多源 author resolution
- ORCID / Crossref / DBLP 辅助
- 论文域 `src/data_agents/paper/pipeline.py`
- 再由 paper feedback 反哺 professor

这意味着现在存在明显的“设计已写好，但主链路没接上”的架构漂移。

### 5.3 根因 C：教授质量门把“无论文”当成可发布状态

当前 `apps/miroflow-agent/src/data_agents/professor/quality_gate.py` 的逻辑是：

- 只有 `enrichment_source == "regex_only"` 且没有 `top_papers` 时，才标 `needs_enrichment`
- 只要不是 `regex_only`，即使 `top_papers=[]`，也可能是 `ready`

更关键的是，测试已经把这种口径固化了：

- `apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py`
- `test_quality_status_ready_when_all_good()`
- 明确断言：`enrichment_source="paper_enriched"` 且 `top_papers=[]` 时，`quality_status == "ready"`

这说明“`ready` 不要求论文数据”不是偶发 bug，而是**当前实现的显式设计**。

### 5.4 根因 D：共享契约和管理后台只有通用三态，无法表达教授域的真实缺口

当前共享契约与后台仍使用：

- `ready`
- `needs_review`
- `low_confidence`

见：

- `docs/index.md`
- `docs/Data-Agent-Shared-Spec.md`
- `apps/miroflow-agent/src/data_agents/contracts.py`
- `apps/admin-console/backend/api/batch.py`

但教授管线内部的质量门实际使用的是：

- `ready`
- `incomplete`
- `shallow_summary`
- `needs_enrichment`

这导致教授域的真实质量语义在进入共享层时被压缩掉了。

### 5.5 根因 E：发布脚本主动丢弃教授域字段，并强制写 `ready`

`apps/miroflow-agent/scripts/run_professor_publish_to_search.py` 当前存在三个关键问题：

1. `quality_status="ready"` 被硬编码写入
2. `top_papers=[]` 被硬编码写入
3. `education_structured` / `work_experience` / `company_roles` / `patent_ids` 也被直接写空

核心片段如下：

```python
education_structured=[],
work_experience=[],
company_roles=[],
top_papers=[],
patent_ids=[],
quality_status="ready",
```

这意味着即使未来 enriched 数据补全了这些字段，只要仍走这条发布链路，发布层仍然会把教授对象“洗平”成低保真版本。

### 5.6 根因 F：质量重评脚本也不看论文字段

`apps/miroflow-agent/scripts/reassess_quality.py` 对 professor 的规则是：

- 有 institution + email + department + research_directions 就可判 `ready`

它同样不要求论文字段，因此即使做后置重评，也仍会继续把“无论文教授”判成 `ready`。

## 6. 文档与现实的主要断层

| 维度 | 文档要求 | 当前现实 |
|------|----------|----------|
| 论文反哺地位 | 核心能力，不是可选项 | 当前发布层不依赖论文即可 `ready` |
| `top_papers` 覆盖 | 设计目标 >80% | 当前搜索发布层 0/3274 |
| `h_index/citation_count` | 设计目标 >70% 填充 | 当前搜索发布层 0/3274 |
| 教授状态语义 | 应体现质量差异 | 共享层只有三态，且经常被强制 `ready` |
| 教授-论文联动 | paper domain 反哺 professor | 当前 professor 主链路仍主要自采、自发、自发版发布 |
| 多源论文方案 | OpenAlex 主源 + ORCID/Crossref/DBLP 辅助 | 当前主链路仍停留在旧 academic_tools |

## 7. 修复计划

### P0：先停止“假 ready”继续扩散

目标：先修质量口径，再做大规模补采。

建议改动：

- `apps/miroflow-agent/src/data_agents/professor/quality_gate.py`
  - 把“无论文仍可 ready”的规则改掉
  - 建议新增教授 ready 最低标准：
    - 至少满足 `top_papers` 非空
    - 或 `paper_count` / `h_index` / `citation_count` 至少有一项有效，且状态不是 `regex_only`
- `apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py`
  - 删除/改写当前允许 `top_papers=[]` 仍 `ready` 的测试
- `apps/miroflow-agent/scripts/reassess_quality.py`
  - 把教授重评规则改成包含论文字段
- `apps/miroflow-agent/scripts/run_professor_publish_to_search.py`
  - 严禁硬编码 `quality_status="ready"`
  - 严禁硬编码 `top_papers=[]`

### P1：打通 `name_en` 与多源学术身份解析

目标：让论文采集先能跑通，再谈覆盖率。

建议改动：

- 新增 `apps/miroflow-agent/src/data_agents/professor/name_resolution.py`
  - 从 homepage 提取英文名
  - 提供拼音 fallback
  - 提供机构/邮件/主页辅助验证
- `apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py`
  - 增加英文名抽取
- `apps/miroflow-agent/src/data_agents/professor/pipeline_v3.py`
  - 在 Stage 2b 前保证 `name_en` 已解析

### P2：用多源论文方案替换旧 academic_tools 主链路

目标：不再依赖“中文名直搜 Semantic Scholar/DBLP/arXiv”这种脆弱路径。

建议改动：

- 以 `docs/Paper-Collection-Multi-Source-Design.md` 为准
- 优先引入：
  - OpenAlex author search + institution filter
  - ORCID 锚定
  - Crossref DOI 补全
  - DBLP 作为 CS 补源
- 让 `apps/miroflow-agent/src/data_agents/professor/paper_collector.py`
  - 不再直接依赖旧 `academic_tools`
  - 或直接改成复用 `apps/miroflow-agent/src/data_agents/paper/pipeline.py`

### P3：把 professor 发布链改成“保真发布”，不要再洗字段

目标：采到什么就发布什么，状态也保真透传。

建议改动：

- `apps/miroflow-agent/scripts/run_professor_publish_to_search.py`
  - 透传 `education_structured`
  - 透传 `work_experience`
  - 透传 `company_roles`
  - 透传 `top_papers`
  - 透传 `patent_ids`
  - 透传真实 `quality_status`
- `apps/miroflow-agent/src/data_agents/contracts.py`
  - 要么扩展教授域 `quality_status` 可枚举值
  - 要么新增教授专属 `paper_status` / `enrichment_status`
- `apps/admin-console/backend/api/batch.py`
  - 同步支持新的质量状态语义

### P4：完成一次全量回填与重新发布

目标：把历史坏状态清掉，不让旧库继续污染产品判断。

建议步骤：

1. 先修 P0、P1、P2、P3
2. 对 `logs/data_agents/professor/enriched.jsonl` 对应全量教授重新跑论文采集
3. 重新生成 professor search service 发布产物
4. 重新跑 `consolidate_to_shared_store.py`
5. 再执行一次共享库质量审计

### P5：同步修文档，消除口径漂移

建议更新：

- `docs/index.md`
- `docs/Data-Agent-Shared-Spec.md`
- `docs/Professor-Pipeline-V2-User-Guide.md`
- `docs/Paper-Collection-Multi-Source-Design.md`

需要统一的内容：

- 教授 ready 的最低标准
- 共享层是否允许教授域保留更细质量状态
- 发布链路是否允许空 `evaluation_summary`
- 论文域与教授域的实际串联方式

## 8. 建议优先修改的文件清单

| 优先级 | 文件 | 目的 |
|--------|------|------|
| P0 | `apps/miroflow-agent/src/data_agents/professor/quality_gate.py` | 收紧 ready 标准 |
| P0 | `apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py` | 把错误口径从测试里移除 |
| P0 | `apps/miroflow-agent/scripts/run_professor_publish_to_search.py` | 停止硬编码 ready 与空 `top_papers` |
| P0 | `apps/miroflow-agent/scripts/reassess_quality.py` | 让后置重评纳入论文字段 |
| P1 | `apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py` | 提取 `name_en` |
| P1 | `apps/miroflow-agent/src/data_agents/professor/pipeline_v3.py` | 在 Stage 2b 前完成 name resolution |
| P2 | `apps/miroflow-agent/src/data_agents/professor/paper_collector.py` | 切到多源学术采集 |
| P2 | `apps/miroflow-agent/src/data_agents/professor/academic_tools.py` | 逐步退场或仅保留兼容层 |
| P2 | `apps/miroflow-agent/src/data_agents/paper/pipeline.py` | 接入教授-论文反哺主链路 |
| P3 | `apps/miroflow-agent/src/data_agents/contracts.py` | 修正共享质量状态表达能力 |
| P3 | `apps/admin-console/backend/api/batch.py` | 后台支持真实质量状态 |

## 9. 验收标准

修复完成后，至少应满足以下检查：

1. `logs/data_agents/professor/search_service/professor_released_objects.jsonl` 中：
   - `ready` 教授里 `top_papers=[]` 的数量为 0
   - `ready` 教授里 `paper_count/h_index/citation_count` 全空的数量为 0
2. `name_en` 填充率 > 80%
3. `top_papers` 覆盖率 > 80%
4. `h_index/citation_count` 填充率 > 70%
5. 抽检 50 名教授时，教授-论文归属准确率 ≥ 90%
6. 共享库与搜索发布层的 `quality_status` 语义一致，不再出现“内部 needs_enrichment，外部 ready”的情况

## 10. 不建议的伪修复

以下做法不建议单独上线：

- 只把 UI 里的 `ready` 改成 `needs_review`，但不修论文采集
- 只加中文名拼音翻译，但不做机构/主页/研究方向消歧
- 只改文档，不改质量门和发布脚本
- 继续沿用旧 `academic_tools`，同时在文档里宣称已经支持 OpenAlex 多源方案

这些做法只能改变表象，不能解决“教授对象不满足要求却被发布成完成态”的根本问题。
