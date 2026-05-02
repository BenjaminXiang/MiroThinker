---
title: "W13-5: retrieval._PROFESSOR_OUTPUT_FIELDS 补学术指标（P0-6）"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review
wave: Wave 13
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-04-30-w9-1-prof-academic-metrics.md
prd_anchor: docs/Professor-Data-Agent-PRD.md §4.1（h_index/citation_count/paper_count）
shared_spec_anchor: docs/Data-Agent-Shared-Spec.md §4.3（教授必发布字段）
---

# W13-5: retrieval._PROFESSOR_OUTPUT_FIELDS 补学术指标（P0-6）

## 1. Goal

W9-1 + W12-2 已让 `professor` Milvus collection schema 含 `h_index / citation_count / paper_count`，写入路径在 `apps/miroflow-agent/src/data_agents/professor/vectorizer.py:100-102` 与 `scripts/run_milvus_backfill.py:262-264`。但 `apps/miroflow-agent/src/data_agents/service/retrieval.py:23-29` `_PROFESSOR_OUTPUT_FIELDS` 仅 5 字段（`professor_id / name / institution / department / profile_summary`），ANN 召回 metadata 拿不到这三大指标。

直接结果：D/E 路径走 retrieval 时 evidence 里没指标；前端 chat 卡片不展示指标（admin / chat A 路径走 Postgres SQL 绕开了，但语义路径全丢）。

本 spec 极小：扩 OUTPUT_FIELDS。

## 2. Non-goals

- **不**改 vectorizer / Milvus schema
- **不**改 chat.py 渲染（拿到 metadata 后前端自然能展示；如有渲染调整另起）
- **不**改 paper / company / patent 的 OUTPUT_FIELDS（如需另起小 spec）

## 3. User-visible behavior

| 场景 | 之前 | 之后 |
|---|---|---|
| `RetrievalService.retrieve(domains=("professor",), query="...")` 返回 evidence | metadata 仅 5 字段 | metadata 含 h_index / citation_count / paper_count |
| chat D 类教授 evidence 卡片 | 无指标 | 含指标 |

## 4. Affected paths

```
修改：
  apps/miroflow-agent/src/data_agents/service/retrieval.py
    _PROFESSOR_OUTPUT_FIELDS（约 :23-29）追加：
      "h_index", "citation_count", "paper_count"
    _format_professor_metadata 同步把这三个字段写进 metadata（如该 helper 已自动展开 OUTPUT_FIELDS 则无需改）

  apps/miroflow-agent/tests/data_agents/service/test_retrieval.py
    既有 mock fixture 加这三字段；断言 retrieve 返回的 metadata 含三字段
```

## 5. Interface

无新接口；现有 `RetrievalEvidence.metadata` dict 增 3 个 key：

```python
{
  "professor_id": "PROF-XXX",
  "name": "...",
  "institution": "...",
  "department": "...",
  "profile_summary": "...",
  "h_index": int | None,
  "citation_count": int | None,
  "paper_count": int | None,
}
```

值为 None / 0 时正常返回（缺 ORCID 数据时常见）。

## 6. Invariants

- 字段名与 vectorizer schema 完全一致：`h_index / citation_count / paper_count`
- 顺序无关（dict）
- Milvus 端 `_PROFILES_FIELDS` 与本 spec OUTPUT_FIELDS 必须同步；W9-1 已加，本 spec 校对
- 既有 `retrieval.retrieve` / `get_object` / `get_related_objects` 行为不变（只是 evidence 多 3 个字段）

## 7. Edge cases

| 场景 | 处理 |
|---|---|
| Milvus 老数据未含三字段 | OUTPUT_FIELDS 仍能 SELECT；老行返回值是 None / 默认 0 |
| 教授未跑 ORCID backfill（W9-2 子集） | 三字段 = 0 / None；前端可降级展示 |

## 8. Validation

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/service/test_retrieval.py \
                tests/data_agents/service/test_retrieval_get_object.py \
                tests/data_agents/service/test_retrieval_get_related.py \
                -n0 --no-cov -v

# admin-console chat 不退化
cd ../admin-console
uv run pytest tests/test_chat_retrieval.py tests/test_chat_v1.py -n0 --no-cov
```

## 9. Done criteria

1. ✅ `_PROFESSOR_OUTPUT_FIELDS` 含 3 个新字段
2. ✅ 单测断言 metadata 含 3 个字段
3. ✅ 既有教授 retrieval / chat 测试不退化
4. ✅ ruff 通过

## 10. Open questions

| 问题 | 默认决策 |
|---|---|
| 是否同时改 `_PAPER_OUTPUT_FIELDS` 让 metadata 含 summary_zh？| 否，单独立 spec（涉及 W13-1 暴露契约对齐） |
| 是否同时改 company OUTPUT_FIELDS 含 evaluation_summary？| 否，依赖 W13-D1 决策 |
