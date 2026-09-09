---
title: "W11-3: D 类型 narrowing per-domain last_result_set"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex；claude review
wave: Wave 11
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w11-5-chat-session-postgres.md
prd_anchor: docs/Agentic-RAG-PRD.md §2.1 type D
---

# W11-3: D 类型 narrowing per-domain last_result_set

## 1. Goal

PRD §2.1 D 类型："基于上轮 N 条结果的进一步筛选"（如 A 类型返 50 教授 → "其中做无人机的"）。当前 chat.py 无 last_result_set storage → 第二轮 D 重新执行 A 检索，丢失上轮上下文。

## 2. Non-goals

- **不**做跨域 narrowing（仅同 domain 内）
- **不**改 W11-5 SessionContext 主结构
- **不**改 retrieval 接口

## 3. User-visible behavior

| 场景 | 行为 |
|---|---|
| 第一轮 A "深圳做 AI 的教授"（返 50）| `chat_session.last_result_set["professor"]` 存 50 prof_ids |
| 第二轮 D "其中做大模型的" | 用 prof_ids 缩 retrieval 范围；返 5 |
| 第三轮 D "其中清华的" | 用上轮 5 prof_ids 二次缩 |
| 跨域 query | 重置该 domain 的 last_result_set |

## 4. Affected paths

```
新增：
  apps/miroflow-agent/alembic/versions/V016_add_chat_session_last_result_set.py
  apps/admin-console/tests/test_chat_d_narrowing.py

修改：
  apps/admin-console/backend/storage/chat_session.py
    SessionContext model 加 last_result_set: dict[str, list[str]]
    SessionStore CRUD 同步
  apps/admin-console/backend/api/chat.py
    A/B 类型 handler 写 last_result_set[domain] = 返回的 ids
    D 类型 handler 读 last_result_set[domain]，retrieve 时加 id IN (...) 过滤
```

## 5. Schema

V016：

```python
op.add_column(
    "chat_session",
    sa.Column("last_result_set", postgresql.JSONB, nullable=False, server_default="{}"),
)
```

形如 `{"professor": ["PROF-A","PROF-B",...], "paper": [...], "company": [...], "patent": [...]}`，每域 LRU 100 ids（按 query 出现顺序，超容截断最旧）。

## 6. Interface

`SessionContext.last_result_set: dict[Literal[domain], list[str]] = Field(default_factory=dict)`

Helper：
```python
def push_result_set(self, domain: str, ids: list[str], cap: int = 100) -> None:
    existing = self.last_result_set.get(domain, [])
    deduped = ids + [x for x in existing if x not in set(ids)]
    self.last_result_set[domain] = deduped[:cap]

def clear_other_domains(self, current: str) -> None:
    """Optional: 不清，保留多域 history（用户可能交叉追问）"""
```

## 7. Invariants

- LRU cap 100/domain
- domain 必须 ∈ {professor, paper, company, patent}
- 跨 domain 不影响其他 domain 的 last_result_set（保留）
- ids 顺序：最新优先（push 时新 ids 在前）
- D handler 缺 last_result_set 时 fallback 到 A（不 raise）

## 8. Validation

```bash
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest apps/admin-console/tests/test_chat_d_narrowing.py \
                apps/admin-console/tests/test_chat_session_store.py \
                -v
```

## 9. Done criteria

1. ✅ V016 + last_result_set CRUD
2. ✅ A/B handler push；D handler 读 + 过滤
3. ✅ 单测覆盖单域 narrow / 跨域不污染 / 三轮叠加
4. ✅ 既有 chat tests 不退化

## 10. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| Storage | chat_session.last_result_set JSONB column |
| 容量 | 100 ids/domain |
| 跨域行为 | 保留各域 history；不清空 |
