---
title: "feat: Paper Collection Multi-Source — Priority Implementation Plan"
type: feat
status: active
date: 2026-04-08
origin: docs/Paper-Collection-Multi-Source-Design.md
---

# feat: Paper Collection Multi-Source — Priority Implementation Plan

## Overview

把修订后的多源论文设计落成可执行实现顺序。计划采用“两阶段推进”：

- **Phase A**：先稳定交付 `paper-backed ready professor`
- **Phase B**：在 Phase A 通过真实 E2E 和人工精度审计后，再补 ORCID、DOI enrichment、DBLP 和 contract 扩展

目标不是一次完成完整多源融合，而是先消除“教授已 ready 但无论文数据”与“多源设计存在但未真正接入主链路”这两个核心问题。

## Problem Frame

当前教授域已经有部分 paper 多源能力，但仍存在四个承重缺口：

- OpenAlex institution 约束仍停留在机构别名打分，没有深圳 9 校的稳定 institution registry
- `name_en` 补全不稳定，导致 author search 对中文教授仍容易退化
- 当前 hybrid 是单源 fallback，不是真正的多源融合
- 设计稿中的 ORCID、DOI enrichment、DBLP 和 contract 扩展还没有进入当前主链路

如果继续按“全量终态”同时推进，执行面会过大；如果只做零散修补，又会继续在真实 E2E 里靠单点手修收口。

## Requirements Trace

- **R1**：补齐深圳 9 校 OpenAlex institution registry，作为 Phase A 的阻塞依赖
- **R2**：在 paper collection 之前稳定提供 `name_en` 或 query-only 英文名候选
- **R3**：让 OpenAlex 成为 institution-constrained 的主路径
- **R4**：保留当前 `Semantic Scholar / Crossref` author-search fallback，但不把它们误写成完整 DOI enrichment
- **R5**：Phase A 不扩共享 Paper contract，也不引入新的共享 `quality_status`
- **R6**：未确认 identity 或未拿到稳定 paper signal 的教授，必须停留在 `needs_enrichment`
- **R7**：Phase A 的完成标准必须基于真实教授 URL E2E 和人工精度抽检
- **R8**：Phase B 只能在 Phase A 验收通过后启动

## Scope Boundaries

**Phase A in scope:**

- institution registry
- `name_en` / query candidate 可靠性增强
- OpenAlex 主路径改造
- current hybrid fallback 对齐
- professor paper 结果语义修正
- 真实 E2E 与人工精度审计

**Phase A out of scope:**

- ORCID client
- Crossref DOI enrichment
- Semantic Scholar DOI / batch enrichment
- DBLP 条件触发补充
- shared Paper contract 扩展
- 论文多源字段级 merge

**Phase B in scope after Phase A:**

- ORCID identity anchor
- DOI 级 metadata enrichment
- DBLP CS supplement
- Paper contract / release schema 扩展
- DOI-anchored merge

## Context & Research

### Relevant Code and Patterns

- `apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py`：当前 `name_en` 提取与回填入口
- `apps/miroflow-agent/src/data_agents/professor/paper_collector.py`：当前 professor 侧 paper orchestration，已优先走 hybrid
- `apps/miroflow-agent/src/data_agents/paper/openalex.py`：当前 OpenAlex author + works client
- `apps/miroflow-agent/src/data_agents/paper/semantic_scholar.py`：当前 S2 author-search fallback
- `apps/miroflow-agent/src/data_agents/paper/crossref.py`：当前 Crossref author-search fallback
- `apps/miroflow-agent/src/data_agents/paper/hybrid.py`：当前 `OpenAlex -> S2 -> Crossref` 降级链
- `apps/miroflow-agent/src/data_agents/professor/quality_gate.py`：当前 `ready / incomplete / shallow_summary / needs_enrichment` 质量状态
- `apps/miroflow-agent/scripts/run_professor_url_md_e2e.py`：当前真实教授 URL E2E 入口

### Institutional Learnings

- `docs/solutions/data-quality/professor-paper-gap-root-cause-and-remediation-plan-2026-04-07.md`
  说明问题不只是“没抓到 paper”，还包括 `ready` 语义与发布层丢信号
- `docs/solutions/workflow-issues/professor-url-md-ready-paper-closure-2026-04-08.md`
  说明真实验收必须逐 URL 看 `released + ready + paper-backed`
- `docs/solutions/workflow-issues/data-agent-real-e2e-gates-2026-04-02.md`
  说明数据代理功能必须用真实源 E2E 关门，不能只看单元测试

## Key Technical Decisions

- **Decision 1: institution registry 单独建模块，不塞进 alias helper。**
  `institution_names.py` 继续负责机构别名与英文名；OpenAlex ID registry 单独维护，避免“别名归一化”和“外部 ID 映射”耦合。

- **Decision 2: Phase A 不做字段级多源 merge。**
  首期只选择一个最佳 source result，并依赖现有 release 层去重，避免在 contract 未扩展前做无处落地的 enrichment。

- **Decision 3: query-only 英文名候选可以比 persisted `name_en` 更激进。**
  为了提高 OpenAlex 命中率，可以在查询时引入 transliteration/URL-derived 候选；但只有被主页或结构化内容证实的英文名才写回 profile。

- **Decision 4: 不新增共享 `quality_status`。**
  identity uncertain 或 paper unresolved 统一通过“不给 paper signal”体现，最终仍归入 `needs_enrichment`。

- **Decision 5: Phase A 验收先于 Phase B 开发。**
  任何 ORCID / DOI enrichment / DBLP 工作，都必须在 Phase A 稳定后开始，防止在不稳的主路径上叠加复杂度。

## Open Questions

### Resolve Before Implementation

- 深圳 9 校 OpenAlex institution ID 的最终映射值是什么
- 查询期 transliteration 候选是否需要单独的 debug 输出，便于人工核查命中来源
- 是否要在 Phase A 就持久化内部 `paper_identity_confidence`，还是只进调试产物

### Deferred to Phase B

- ORCID record 评分细则
- Crossref / S2 enrichment 字段的 shared contract 设计
- DBLP 触发条件的关键词集合与 venue 优先级

## High-Level Technical Design

```text
Professor homepage/profile
  -> name_en resolution + institution registry lookup
  -> OpenAlex author search (institution constrained when registry exists)
  -> OpenAlex works
  -> fallback: Semantic Scholar author search
  -> fallback: Crossref author search
  -> choose best single-source paper result
  -> generate/merge research directions
  -> quality gate: ready only when paper signal exists
  -> professor URL E2E + manual audit gate

Phase B only after the gate:
  -> ORCID anchor
  -> DOI enrichment (Crossref/S2)
  -> DBLP supplement
  -> contract extension
  -> multi-source DOI merge
```

## Priority Order

| Priority | Unit | Why first | Exit criterion |
|----------|------|-----------|----------------|
| P0 | Acceptance gates + institution registry | 没有这两者，后续实现无法判定成功与否 | 9 校 registry 有明确状态；Phase A 验收口径固定 |
| P1 | OpenAlex 主路径改造 | 这是 paper-backed professor 的主产出源 | OpenAlex 命中路径在真实样本上明显改善 |
| P1 | `name_en` / query candidate 强化 | 没有稳定 query name，OpenAlex 主路径无法充分发挥 | query names 对中文-only 页面可用 |
| P1 | paper 结果语义与 quality 对齐 | 防止“看似 paper_enriched，实际无 paper” | unresolved 记录不会伪装成已完成 |
| P2 | Phase A E2E 与人工审计 | 需要真实验证锁定是否值得进入 Phase B | 真实 URL E2E 与抽检达标 |
| P3 | ORCID + DOI enrichment + DBLP + contract | 属于增强层，不应阻塞首期交付 | Phase A gate 已通过 |

## Implementation Units

### P0-1: Phase A 验收口径与基线固化

- [ ] **Unit P0-1: Freeze Phase A acceptance gates**

**Goal:** 把 Phase A 的成功标准写死到计划和脚本语义中，避免“代码做了很多，但没人知道算不算完成”。

**Requirements:** R5, R6, R7

**Dependencies:** None

**Files:**
- Modify: `docs/Paper-Collection-Multi-Source-Design.md`
- Modify: `docs/solutions/workflow-issues/professor-url-md-ready-paper-closure-2026-04-08.md`
- Optional modify: `apps/miroflow-agent/scripts/run_professor_url_md_e2e.py`
- Test: `apps/miroflow-agent/tests/scripts/` 下补充脚本级 summary 测试（如已有相应目录）

**Approach:**
- 固化 Phase A 验收条件：
  - `ready` 教授不能没有 paper signal
  - 真实 URL E2E 必须报告 paper-backed professor 比例
  - 必须保留人工精度抽检步骤
- 若 E2E summary 目前不输出所需统计，则补充最小 summary 字段，不改动业务逻辑

**Patterns to follow:**
- `apps/miroflow-agent/scripts/run_professor_url_md_e2e.py`
- `logs/data_agents/professor_url_md_final_verification_2026-04-07.md`

**Test scenarios:**
- summary 包含 `released / ready / paper-backed` 三类计数
- unresolved URL 能在 summary 中被准确标出
- regression：现有 URL E2E 输出格式不被破坏

**Verification:**
- 运行现有 professor URL E2E 报告生成流程，确认验收字段可见

---

### P0-2: Institution Registry

- [ ] **Unit P0-2: Add OpenAlex institution registry for Shenzhen 9 schools**

**Goal:** 为 OpenAlex author search 提供稳定 institution ID，移除“只靠机构别名打分”的脆弱路径。

**Requirements:** R1, R3

**Dependencies:** Unit P0-1

**Files:**
- Create: `apps/miroflow-agent/src/data_agents/professor/institution_registry.py`
- Modify: `apps/miroflow-agent/src/data_agents/professor/institution_names.py`
- Test: `apps/miroflow-agent/tests/data_agents/professor/test_institution_registry.py`

**Approach:**
- 单独创建 registry 模块，提供：
  - `resolve_openalex_institution_id(institution_name: str) -> str | None`
  - `get_institution_registry_entry(...)`
- registry entry 至少包含：
  - 中文名
  - 主英文名
  - OpenAlex ID
  - 是否与母校共用 ID 的备注
- `institution_names.py` 保持 alias/英文名功能，不混入 OpenAlex ID 常量

**Patterns to follow:**
- `apps/miroflow-agent/src/data_agents/professor/institution_names.py`

**Test scenarios:**
- 中文校名返回稳定 OpenAlex ID
- 英文别名和缩写返回同一个 ID
- 未知学校返回 `None`
- 共用母校 ID 的学校有显式备注，不会静默吞掉差异

**Verification:**
- registry 9 行全部填满
- 核对每行能通过最小 smoke query 对到正确 OpenAlex institution

---

### P1-1: OpenAlex 主路径改造

- [ ] **Unit P1-1: Make OpenAlex the institution-constrained primary path**

**Goal:** 让 OpenAlex author search 在有 registry 时走精确 institution filter，在无 registry 时才回退到 alias scoring。

**Requirements:** R1, R3, R4

**Dependencies:** Unit P0-2

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/paper/openalex.py`
- Modify: `apps/miroflow-agent/src/data_agents/professor/paper_collector.py`
- Test: `apps/miroflow-agent/tests/data_agents/paper/test_openalex.py`
- Test: `apps/miroflow-agent/tests/data_agents/professor/test_paper_collector.py`

**Approach:**
- 扩展 OpenAlex client 签名，允许传入 `institution_id`
- `paper_collector` 在构造 query 时先取 registry；有 ID 时走 `filter=last_known_institutions.id:<id>`
- registry 缺失时保留当前 institution alias scoring
- 保持 `works_count / cited_by_count / h_index` 的现有映射

**Patterns to follow:**
- `apps/miroflow-agent/src/data_agents/paper/openalex.py`
- `apps/miroflow-agent/tests/data_agents/paper/test_openalex.py`

**Test scenarios:**
- 有 `institution_id` 时请求参数包含精确 filter
- 无 `institution_id` 时仍能走现有 author selection 逻辑
- 两个同名作者存在时，优先选择 institution matched author
- OpenAlex 无 author 时，调用方能正常降级到 hybrid fallback

**Verification:**
- 真实样本对比：几位已知教授在 OpenAlex 主路径上能稳定命中正确 author

---

### P1-2: `name_en` 与 Query Candidate 强化

- [ ] **Unit P1-2: Separate persisted `name_en` from query-only English candidates**

**Goal:** 提高中文-only 页面在 OpenAlex 路径下的可搜索性，但不把低置信英文名直接写回 profile。

**Requirements:** R2, R3

**Dependencies:** Unit P0-2

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py`
- Modify: `apps/miroflow-agent/src/data_agents/professor/name_utils.py`
- Modify: `apps/miroflow-agent/src/data_agents/professor/paper_collector.py`
- Test: `apps/miroflow-agent/tests/data_agents/professor/test_homepage_crawler.py`
- Test: `apps/miroflow-agent/tests/data_agents/professor/test_paper_collector.py`

**Approach:**
- persisted `name_en` 只接受主页或结构化内容明确给出的英文名
- query path 允许附加：
  - URL-derived 英文名
  - 可解释的 transliteration 候选
- transliteration 候选只参与 search，不直接写回 profile
- `paper_collector._build_query_names()` 明确 query source 优先级，防止杂乱候选互相污染

**Patterns to follow:**
- `apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py`
- `apps/miroflow-agent/src/data_agents/professor/name_utils.py`

**Test scenarios:**
- 页面明确有英文名时，persisted `name_en` 正确写回
- 页面无英文名但 URL 可推导时，query names 包含 URL-derived 候选
- 页面与 URL 都无英文名时，query names 允许加入 transliteration 候选
- transliteration 候选不会覆盖已有 persisted `name_en`

**Verification:**
- 针对中文-only 教授样本，query names 列表可解释且顺序稳定

---

### P1-3: Paper Result 语义与质量门对齐

- [ ] **Unit P1-3: Prevent false “paper_enriched” semantics on unresolved results**

**Goal:** 避免记录在没有论文成果时仍被标成已完成 paper enrichment。

**Requirements:** R4, R5, R6

**Dependencies:** Unit P1-1, Unit P1-2

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/professor/paper_collector.py`
- Modify: `apps/miroflow-agent/src/data_agents/professor/pipeline_v3.py`
- Modify: `apps/miroflow-agent/src/data_agents/professor/quality_gate.py`
- Test: `apps/miroflow-agent/tests/data_agents/professor/test_paper_collector.py`
- Test: `apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py`

**Approach:**
- `paper_collector` 明确区分：
  - `paper_resolved`
  - `paper_unresolved`
  - `official_only`
- `pipeline_v3` 不再对无 paper 的结果统一写 `enrichment_source="paper_enriched"`
- quality gate 继续用 paper signal 判断 `ready`，不新增共享状态
- 如需内部 `paper_identity_confidence`，先留在 debug artifact 或内部模型，不进入 shared contract

**Patterns to follow:**
- `apps/miroflow-agent/src/data_agents/professor/quality_gate.py`

**Test scenarios:**
- 无论文时 `top_papers=[]` 且不伪装成 `paper_enriched`
- 有论文但 research directions 沿用官网时仍可视为 paper resolved
- unresolved 记录不会被判成 `ready`
- regression：已有 `ready` with paper 的样本不受影响

**Verification:**
- 真实 URL E2E 抽样中，`ready` 记录与 paper signal 一致

---

### P2-1: Phase A Real Verification

- [ ] **Unit P2-1: Run Phase A E2E and manual identity audit**

**Goal:** 用真实 URL E2E 和人工抽检决定是否允许进入 Phase B。

**Requirements:** R7, R8

**Dependencies:** Unit P1-1, Unit P1-2, Unit P1-3

**Files:**
- Use: `apps/miroflow-agent/scripts/run_professor_url_md_e2e.py`
- Create: `logs/data_agents/paper_phase_a_manual_audit_2026-04-08.md`
- Optional create: `apps/miroflow-agent/scripts/run_paper_phase_a_audit.py`

**Approach:**
- 运行真实教授 URL E2E，观察：
  - paper-backed professor 比例
  - unresolved 分布
  - per-school hit rate
- 进行 50-100 名教授人工抽检：
  - 验证 author 是否是同一人
  - 验证 top papers 与研究方向/机构是否明显冲突
- 只有通过这一步，才允许进入 Phase B

**Test scenarios:**
- 不适用典型单元测试；以脚本产物和人工审计报告为验收

**Verification:**
- 形成正式 audit report
- 明确给出 “Go / No-Go for Phase B”

---

### P3: Deferred Phase B Units

- [ ] **Unit P3-1: ORCID client + identity verifier**
- [ ] **Unit P3-2: Crossref DOI enrichment**
- [ ] **Unit P3-3: Semantic Scholar DOI/batch enrichment**
- [ ] **Unit P3-4: Paper contract / release schema extension**
- [ ] **Unit P3-5: DBLP conditional supplement**
- [ ] **Unit P3-6: DOI-anchored multi-source merge**

这些单元暂不展开到实现细节，直到 Phase A 通过验收。

## Dependencies and Sequencing

1. `P0-1` 必须先完成，否则没有稳定验收定义。
2. `P0-2` 是 `P1-1` 的直接前置依赖。
3. `P1-2` 可以与 `P1-1` 并行准备，但合并前要统一 query candidate 语义。
4. `P1-3` 必须在 `P1-1/P1-2` 之后完成，否则结果语义不稳定。
5. `P2-1` 是进入所有 P3 单元的硬门槛。

## Risks

- institution registry 查询结果若不稳定，会拖慢整个 Phase A
- transliteration 候选若过激，可能提升命中率同时引入误采
- OpenAlex institution ID 对深圳校区的粒度可能与预期不一致
- 若不先修正 `paper_enriched` 语义，真实 E2E 结果仍会出现“看似完成”的假象

## Verification Summary

Phase A 完成前，至少需要这些验证：

- `tests/data_agents/paper/test_openalex.py`
- `tests/data_agents/professor/test_paper_collector.py`
- `tests/data_agents/professor/test_homepage_crawler.py`
- `tests/data_agents/professor/test_quality_gate.py`
- `scripts/run_professor_url_md_e2e.py` 的真实源 E2E
- 50-100 名教授人工 identity audit

## Exit Criteria

只有同时满足以下条件，才允许关闭这个计划的 Phase A：

- 深圳 9 校 institution registry 已填满并经 smoke 验证
- OpenAlex institution-constrained 主路径已接入 V3
- `ready` 教授不存在空 paper signal
- 真实教授 URL E2E 证明主路径不是靠个别手工修补才能成立
- 人工抽检精度达到 ≥95%，且明显误采数为 0

满足以上条件后，再创建或扩展 Phase B 计划。
