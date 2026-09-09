---
title: "W13-D1: evaluation_summary 字段去留决策（P0-4，需 user 拍板）"
date: 2026-05-02
owner: claude
status: blocked-on-user-decision
audience: user（决策）；claude review
wave: Wave 13
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
prd_anchor:
  - docs/Professor-Data-Agent-PRD.md §4.1（教授可选发布字段）
  - docs/Company-Data-Agent-PRD.md §4.1 + §4.2
shared_spec_anchor: docs/Data-Agent-Shared-Spec.md §4.3（教授 evaluation_summary 100-150 字 / 企业 evaluation_summary）
---

# W13-D1: evaluation_summary 字段去留决策（P0-4）

## 1. 现状（schrödinger）

### 教授

| 位点 | 状态 |
|---|---|
| `apps/miroflow-agent/src/data_agents/professor/summary_generator.py:167-197,250-269` | 仍生成 `evaluation_summary` |
| `apps/miroflow-agent/src/data_agents/professor/vectorizer.py:96-98,164` | 写进 `professor_profiles` Milvus collection |
| `apps/miroflow-agent/src/data_agents/professor/models.py:157` | 注释 "V3: no longer generated" |
| canonical schema（V003 / V010） | **无 `evaluation_summary` 列** |
| `apps/admin-console/backend/api/domains.py` 教授 DTO | **不暴露** |
| `apps/admin-console/backend/api/chat.py` | **不读** |
| `apps/miroflow-agent/src/data_agents/service/retrieval.py:_PROFESSOR_OUTPUT_FIELDS` | **不读** |

### 企业

| 位点 | 状态 |
|---|---|
| `apps/miroflow-agent/src/data_agents/company/release.py + enrichment.py:78` | JSONL release path 生成 |
| canonical schema（V002 / V014） | **无 `evaluation_summary` 列**；V014 仅含 `profile_summary + technology_route_summary` |
| `apps/miroflow-agent/src/data_agents/company/narrative_enrichment.py:260` | LLM 仅生成 2 个摘要（profile + technology_route），**没生成 evaluation**|
| `apps/admin-console/backend/api/domains.py` 企业 DTO | **不暴露** |
| chat / retrieval | **不读** |

PRD 要求：

- `docs/Data-Agent-Shared-Spec.md §4.3`：教授 evaluation_summary 100-150 字（事实性评价摘要）；企业 evaluation_summary（事实性评价摘要）
- `docs/Professor-Data-Agent-PRD.md §4.1`：可选发布字段
- `docs/Company-Data-Agent-PRD.md §4.1`：必发布字段

**结论**：代码状态自相矛盾，必须二选一。

## 2. 选项

### 选项 A：保留 + 补齐（兑现 PRD）

工作量：

1. 教授：
   - V019 `professor.evaluation_summary TEXT NULL`
   - 把 summary_generator 输出落 canonical（目前只进 Milvus）
   - admin DTO + chat profile + retrieval._PROFESSOR_OUTPUT_FIELDS 暴露
   - quality_gate 加长度 100-150 字校验
2. 企业：
   - V020 `company.evaluation_summary TEXT NULL`
   - narrative_enrichment 改 prompt：output 3 段（profile / technology_route / evaluation）
   - run_company_narrative_backfill.py 全量回填（与 W13-V2 合）
   - admin DTO + retrieval._COMPANY_OUTPUT_FIELDS 暴露
3. 测试：
   - 长度门 + 中文 + 事实性（不用主观词）
4. 文档：
   - `docs/index.md` 状态矩阵更新

风险：

- 多两段 LLM 调用（教授 + 企业），token 翻倍
- "事实性评价"prompt 不好写，容易和 profile_summary 重叠
- Milvus 现有 schema 写了字段但 canonical 没 → backfill 需要额外步骤同步

### 选项 B：退役（修 PRD/Spec）

工作量：

1. 教授：
   - 删 summary_generator.py 中 `evaluation_summary` 生成逻辑（约 50 行）
   - models.py:157 注释改为 "removed in V3"
   - 删 vectorizer.py 中 evaluation_summary 字段 + Milvus collection schema 演进（去掉一列）—— 已在线数据不影响（仍可保留旧列）
2. 企业：
   - JSONL release path 删字段
   - 不影响 V014 schema（本来就没列）
3. 文档：
   - `docs/Data-Agent-Shared-Spec.md §4.3` 删 evaluation_summary 行
   - `docs/Professor-Data-Agent-PRD.md §4.1` 删
   - `docs/Company-Data-Agent-PRD.md §4.1 + §4.2` 删
   - `docs/index.md` 术语表删
4. 测试：
   - 删相关单测

风险：

- 永久放弃"事实性评价"产品定位；上线后用户看到的只有"画像"+"技术路线"
- 已有 Milvus 数据列名残留（无害但需注释）

## 3. 推荐

| 维度 | 选项 A | 选项 B |
|---|---|---|
| 工作量（人天） | ~3 天 | ~0.5 天 |
| 用户感知差异 | 多一段 100-150 字事实性总结 | 少一段，但 profile_summary 可吸纳事实信息 |
| Token 成本 | 翻倍 LLM 调用（约 +30% summary_zh 总成本） | 不变 |
| PRD 一致性 | 兑现 | 需改 PRD |
| 测试维护 | 多 4-6 个用例 | 净减 |

**Claude 推荐：选项 B（退役）**。理由：

1. profile_summary（200-300 字 用户向）+ technology_route_summary（企业）已经覆盖了"评价"中可用信息；evaluation_summary 在产品定义上与 profile_summary 重叠度高
2. 当前没有任何接口路径使用，且 schema 也未落地——成本最小的状态就是把代码侧也清掉
3. 如果产品后续需要"事实性评价"，可以用 retrieval + LLM 在线生成，不必预 backfill

如果选项 A，建议把它推迟到 Wave 14 / 15（在 P0/P1 修复 + Phase B 论文之前不优先）。

## 4. 决策表（待 user 填）

| 项 | A（保留补齐）| B（退役）| 决策 |
|---|---|---|---|
| 教授 evaluation_summary | 补 V019 + DTO + retrieval | 删生成代码 + 改 PRD | __ |
| 企业 evaluation_summary | 补 V020 + narrative 3 段 | 删生成代码 + 改 PRD | __ |
| 决策日期 | | | __ |
| 决策 owner | | | user |

## 5. 落地后的 follow-up

- 选项 A：起 W14-x spec（教授 V019）+ W14-y（企业 V020 + narrative 3 段 prompt）
- 选项 B：起 W14-z spec（清理代码 + 改 PRD/Shared-Spec）

## 6. Open questions（user 决策前）

1. 用户对 evaluation_summary 的产品定位是什么？是"教授/公司在专业领域的事实性评价（论文影响、产品规模）"还是"主观打分"？答案不同会影响 prompt 设计。
2. 当前 Milvus 教授 collection 已包含 `evaluation_summary` 字段且写入了若干（但 canonical 没存）；选 B 时这些 Milvus 数据是删还是保留废弃？
3. 是否同时影响 `summary_text`（论文/专利）的"事实性评价"语义？答：不影响（论文/专利的 summary_text 不是 evaluation_summary）。

---

**Action required from user**: 在第 4 节决策表填 A 或 B，并在 chat 里确认。Claude 收到后立刻起 follow-up spec。
