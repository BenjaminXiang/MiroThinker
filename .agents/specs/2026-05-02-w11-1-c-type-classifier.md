---
title: "W11-1: C 类型（跨域跳转）分类器接入"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review
wave: Wave 11
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
prd_anchor: docs/Agentic-RAG-PRD.md §2.1 type C
---

# W11-1: C 类型（跨域跳转）分类器接入

## 1. Goal

PRD §2.1 定义 7 个 query type：A B C D E F G。当前 `chat.py:_classify_query_with_llm` prompt 中支持 A/B/D/E/F/G 共 6 个，**缺 C**（跨域跳转：跨教授-论文-公司-专利的链式追问）。

C 类型典型 query：
- "他的论文有哪些"（接续 A 教授查询后）
- "他参与了哪些公司"
- "这家公司的专利有哪些"

W11-3 进一步处理 D 类型缩窄；W11-1 先把 C 加入 classifier。

## 2. Non-goals

- **不**实施 C handler 业务逻辑（W11-6 + W11-3 联合处理）
- **不**改 multi-turn pronoun 解析（已就绪）
- **不**做 G 类型澄清流程（W11-2）
- **不**改 fixture (W9-3 100 条 benchmark 中 C 已占 15 条)

## 3. User-visible behavior

| 场景 | 行为 |
|---|---|
| query "他的论文" | classifier 返回 type=C, target_domain="paper" |
| query "他参与了哪些公司" | type=C, target_domain="company" |
| query "这家公司的专利有哪些" | type=C, target_domain="patent" |
| C 类型 query 命中 W9-3 fixture C 子集 | 准确率 ≥ 80%（per-class gate） |

## 4. Affected paths

```
修改：
  apps/admin-console/backend/api/chat.py
    - _CLASSIFIER_SYSTEM prompt 加 C 类型描述 + example
    - QueryType Literal 加 'C'（如已有则 noop）
    - _classify_query_with_llm 返回结构含 target_domain（可选；A/B/D/E/F/G 仍只有 type）

CREATE / MODIFY:
  apps/admin-console/tests/test_chat_classifier_c_type.py
    单测：mock LLM 返回 C → handler 不报错 + 字段齐全
```

## 5. Interface contract

### 5.1 _CLASSIFIER_SYSTEM 新增 C type 描述

```text
- C: 跨域跳转 — 用户在已有上下文（前一轮提到的教授/公司/论文）的基础上追问
     另一个域的关联实体。典型词："他的论文"/"她参与的公司"/"这家公司的专利"。
     输出 target_domain: "paper" | "company" | "patent"。
     示例：
       Q: "丁文伯是谁" → type A
       Q: "他的论文" → type C, target_domain="paper"
```

### 5.2 ClassifyResult 增字段

```python
class ClassifyResult(BaseModel):
    type: Literal["A", "B", "C", "D", "E", "F", "G"]
    target_domain: Literal["professor", "paper", "company", "patent"] | None = None
    rationale: str = ""
```

## 6. Invariants

- A/B/D/E/F/G 已有行为不变
- 现有 chat tests 不退化
- 100 条 W9-3 fixture overall accuracy 仍 ≥ 90%
- C per-class accuracy ≥ 80%（spec §F-R1 现行阈值；fixture C=15 条）

## 7. Edge cases

| 场景 | 处理 |
|---|---|
| C type 但无 prior context（首轮） | classifier 仍可输出 C；handler 退化提示 "请先查询某位教授/公司"（W11-6 实施） |
| target_domain 模糊（"他的成果" 可能 paper or 专利） | classifier 优先 paper；handler 可拓展 |
| LLM 偶尔不输出 target_domain | 后处理 default = "paper" |

## 8. Validation

```bash
cd apps/admin-console

# 新单测
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/test_chat_classifier_c_type.py -n0 --no-cov -v

# 既有 chat 单测不退化
uv run pytest tests/ -k chat -n0 --no-cov

# W9-3 benchmark 复跑（claude 操作；需 LLM 可达）
uv run pytest tests/test_classifier_benchmark.py -m requires_classifier_llm -v
# 期望: overall ≥ 90%, C per-class ≥ 80%
```

## 9. Done criteria

1. ✅ _CLASSIFIER_SYSTEM 含 C 描述
2. ✅ ClassifyResult 含 target_domain 字段
3. ✅ 单测 + 既有 chat tests 全过
4. ✅ benchmark 复跑：C 准确率 ≥ 80%，overall ≥ 90%

## 10. Stop conditions

- benchmark C accuracy < 80% → prompt 调优 1 轮；仍不过 escalate（可能 fixture 问题）
- ClassifyResult schema 改动破坏现有 handler → 加 default None 兼容
