---
title: "W11-2: G 同名歧义 clarification UX"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex；claude review
wave: Wave 11
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
prd_anchor: docs/Agentic-RAG-PRD.md §2.1 type G
---

# W11-2: G 同名歧义 clarification UX

## 1. Goal

PRD §2.1 G 类型："同名教授/公司，需 user 选具体哪一个"。当前 chat.py 在 G 类型时返自然语言列表 + 用户重新输入；UX 重。

**本 spec**：返结构化 `clarification` 字段（≤ 5 候选）让前端渲染内联列表 + "选择" 按钮；user 点击后下一轮带 entity_id 直接继续。

## 2. Non-goals

- **不**改前端 React（本 spec 只 backend；前端独立 W13+）
- **不**做模糊 query 主动澄清（仅同名）

## 3. User-visible behavior

| 场景 | 行为 |
|---|---|
| Q: "丁文伯" → 命中 5 同名 | 返 ChatResponse.clarification = {options: [{id, label, hint}, ...]} 5 项 |
| User 选其一 | 下一轮 query 带 entity_id_hint=PROF-XXX；走正常 A handler |
| Cancel / 用户输入新 query | 默认 top1 by ranking score |
| 候选 > 5 | 取 top 5 (by 论文 / paper_count)；附 "另有 N 位..." |

## 4. Affected paths

```
修改：
  apps/admin-console/backend/api/chat.py
    ChatResponse pydantic 加 clarification: ClarificationPayload | None
    ClarificationPayload = {options: list[CandidateOption], default_id: str, prompt: str}
    G handler 不再生成自然语言列表，改返 clarification 结构
    ChatRequest 加 entity_id_hint: str | None
    A handler 检测 entity_id_hint → bypass disambiguation

CREATE / MODIFY:
  apps/admin-console/tests/test_chat_g_clarification.py
    test_g_returns_structured_clarification
    test_clarification_capped_at_5
    test_entity_id_hint_bypasses_g
    test_cancel_default_top1
```

## 5. Interface contracts

```python
class CandidateOption(BaseModel):
    id: str  # PROF-XXX / COMP-XXX / etc
    domain: Literal["professor", "company", "paper", "patent"]
    label: str  # display name
    hint: str  # disambiguation context (institution / industry / year+venue)

class ClarificationPayload(BaseModel):
    prompt: str  # "找到 5 位..." / "找到 3 家..."
    options: list[CandidateOption]  # ≤ 5
    default_id: str  # top1 ranking
    omitted: int  # 候选超 5 时附

class ChatResponse(BaseModel):
    answer_text: str  # 简短文本（让无前端的 caller 也可用）
    query_type: str
    clarification: ClarificationPayload | None = None
    citation_map: dict[str, list[str]]
    # ... existing fields

class ChatRequest(BaseModel):
    query: str
    entity_id_hint: str | None = None  # 用户从 clarification 选了
    # ... existing
```

## 6. Invariants

- options ≤ 5（多了截断 + omitted 计数）
- default_id 必须 in options
- entity_id_hint 优先级最高：设了就 bypass G
- 现有非 G query 行为不变（clarification = None）
- answer_text 仍是 fallback 自然语言（前端缺失时可显示）

## 7. Edge cases

| 场景 | 处理 |
|---|---|
| 候选 0 | clarification = None，answer_text="未找到..." |
| 候选 1 | 不返 clarification（不需澄清），直接 A handler |
| 候选 2-5 | clarification 完整 |
| 候选 > 5 | top 5 + omitted = N - 5 |
| user 提供 invalid entity_id_hint | 当作 None 处理；走 G |

## 8. Validation

```bash
uv run pytest apps/admin-console/tests/test_chat_g_clarification.py \
              apps/admin-console/tests/test_chat_v1.py \
              -v
```

## 9. Done criteria

1. ✅ ChatResponse.clarification 结构化
2. ✅ entity_id_hint bypass G handler
3. ✅ 单测全过；既有 chat tests 不退化

## 10. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| UX | 内联列表（≤ 5）+ "选择" 按钮 |
| Cancel 行为 | 默认 top1 |
| 列表上限 | 5；超出 omitted 计数 |
| entity_id_hint 字段名 | `entity_id_hint`（避免 reserved word） |
