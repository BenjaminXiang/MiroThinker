---
title: "W13-4: C 类型 endpoint handler（P0-5）"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review
wave: Wave 13
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w11-1-c-type-classifier.md
  - .agents/specs/2026-05-02-w13-2-cross-domain-relation-writers.md
  - .agents/specs/2026-05-02-w13-3-patent-postgres-writer.md
prd_anchor: docs/Agentic-RAG-PRD.md §2.1 type C
multi_turn_anchor: docs/Multi-turn-Context-Manager-Design.md §3 跨域跳转
---

# W13-4: C 类型 endpoint handler（P0-5）

## 1. Goal

W11-1 已让 classifier 识别 C 一级类型并返回 `target_domain`；`apps/miroflow-agent/src/data_agents/service/retrieval.py:227-417` 已实装 8 条 SQL 的 `get_related_objects`。但 `apps/admin-console/backend/api/chat.py` 的 endpoint dispatch 没有 `if ctype=="C"` 分支：当前 C query 经过 `_rewrite_query_with_context`（chat.py:812）正则代词替换后，被退化成 A/B 路径，丢失"按上轮实体跨域跳转"语义。

本 spec 补 C handler：从 `chat_session.entity_stack.latest_for(source_domain)` 取上轮 entity → 调 `RetrievalService.get_related_objects(source_domain, source_id, target_domain)` → 组卡片返回。

## 2. Non-goals

- **不**改 classifier prompt（W11-1 已就绪）
- **不**改 EntityStack 结构（仍是 W11-6 的 5 槽 LRU 共享；改成每类 3 槽是另一 spec）
- **不**改 retrieval `get_related_objects` 的 SQL（已实装）
- **不**做 D 类型 narrowing（W11-3 已就绪）
- **不**触 patent 关系（patent 表非空依赖 W13-3；patent C handler 在 W13-3 之后才能产出非空结果）

## 3. User-visible behavior

| 场景 | 预期 |
|---|---|
| 上轮：A "丁文伯是谁"（push PROF-X 到 stack）；本轮 C "他的论文" | classifier ctype=C, target_domain=paper；C handler 取 PROF-X，调 `get_related_objects("professor", "PROF-X", "paper")`；返 verified link 论文卡片 ≤ 5 |
| 上轮：A "广和通"（push COMP-Y）；本轮 C "他们的专利" | ctype=C, target_domain=patent；调 `get_related_objects("company", "COMP-Y", "patent")`；W13-3 上线前命中 0 → 显式提示"暂无专利数据" |
| 上轮：A "做大模型的教授"（B 类，多结果，不 push 单实体）；本轮 C "他们的公司" | stack 无 source 实体 → 退化提示"请先确认某位教授" |
| 上轮：A "丁文伯"；本轮 C "他参与的公司"（target=company）| 调 get_related_objects("professor", "PROF-X", "company")；W13-2 上线后命中真数据 |

## 4. Affected paths

```
修改：
  apps/admin-console/backend/api/chat.py
    在 classifier dispatch 区域（约 chat.py:2029-2291）新增 elif ctype == "C":
    handler 函数 _handle_c_type(session, query, target_domain) -> ChatResponse
    - 从 session.entity_stack.latest_entity_for_other_domains(target_domain) 取 source_id 与 source_domain
    - source_id is None → 返回 friendly clarification 提示
    - 调 RetrievalService.get_related_objects(source_domain, source_id, target_domain)
    - 组卡片：professor → professor_card；company/paper/patent → 各自 card
    - push 新 target 实体到 stack（多结果时仅顶 1 进栈）

新增测试：
  apps/admin-console/tests/test_chat_c_handler.py
    - 上轮 prof + 本轮 C paper → 命中
    - 上轮 prof + 本轮 C company → 命中（W13-2 上线后 fixture 真）
    - 上轮 company + 本轮 C patent → 命中（W13-3 上线后 fixture 真；之前先 mock）
    - stack 空 → clarification
    - target_domain 不合法 → 回退 A/B 路径（不 raise）
```

## 5. Interface

`_handle_c_type` 调用 RetrievalService 已实装 API：

```python
results = await retrieval.get_related_objects(
    source_domain="professor",
    source_id="PROF-A1B2",
    target_domain="paper",
    limit=5,
)
# results: list[RetrievalEvidence]，每条含 object_id / metadata / source_evidence
```

返回结构沿用现 `ChatResponse`：

```python
{
  "answer": "丁文伯教授近期论文：...",
  "evidence": [...],
  "query_type": "C",
  "target_domain": "paper",
  "session_id": "...",
}
```

## 6. Invariants

- `source_domain` 必须 ≠ `target_domain`
- `target_domain` ∈ {professor, paper, company, patent}
- 来源实体取 EntityStack 最新（latest_for 排除 target_domain）；为空时 clarification 而非 raise
- 已有 A/B/D/E/F/G dispatch 不变；C 在分类树尾部新增分支
- C handler 失败时退化为 A 路径（不 leak 异常给前端）

## 7. Edge cases

| 场景 | 处理 |
|---|---|
| stack 中只有 paper 实体，target=paper | clarification "请明确要查的论文实体" |
| target_domain 是 'patent' 但 patent 表空（W13-3 未上线）| 命中 0 → 友好提示"暂未收录该公司的专利数据" |
| latest_for 返回了过期实体（TTL 24h 内但已 stale）| 不做过期判断（TTL 即过期边界）|
| classifier 返 C 但无 target_domain | 默认 target_domain="paper"（与 W11-1 §7 一致）|
| `get_related_objects` raise（DB 故障）| catch + 退化 A/B + log warning |

## 8. Validation

```bash
cd apps/admin-console
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/test_chat_c_handler.py \
                tests/test_chat_classifier_c_type.py \
                tests/test_chat_v1.py \
                tests/test_chat_retrieval.py \
                -n0 --no-cov -v

# benchmark 复跑（线下/可达 LLM）
uv run pytest tests/test_classifier_benchmark.py -m requires_classifier_llm -v
# 期望 overall ≥ 90%, C per-class ≥ 80%
```

## 9. Done criteria

1. ✅ chat.py 新增 `if ctype=="C"` 分支 + `_handle_c_type`
2. ✅ 单测覆盖 prof→paper / prof→company / company→patent / stack-empty / fallback 场景
3. ✅ 既有 chat tests 全过
4. ✅ 100 条 benchmark C per-class ≥ 80%（已知 fixture C=15）
5. ✅ ruff 通过

## 10. 顺序依赖

- W13-4 不阻塞 W13-2 / W13-3，可并行；但**真实命中**需要 W13-2（professor↔company）+ W13-3（patent + company↔patent）落地
- 单测里如对 `get_related_objects` 用 fixture mock，写 fail 路径 + happy path 即可

## 11. Open questions

| 问题 | 默认决策 |
|---|---|
| C handler 是否同时把 target 实体 push 进 stack？| 是；命中条数==1 时 push；多于 1 时 push top 1 |
| C 失败时退化路径 | A（最稳定路径，已有 fallback） |
| 是否在 ChatResponse 增 `c_routing_meta`（source_domain/source_id）| 否；只在 evidence 里留 source link 即可 |
