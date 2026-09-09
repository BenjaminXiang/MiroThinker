---
title: "W11-5: chat_session Postgres 持久化"
date: 2026-05-02
owner: codex
spec: .agents/specs/2026-05-02-w11-5-chat-session-postgres.md
slice: 1 of 1
status: ready
---

# W11-5 handoff（单 slice）

## CRITICAL — codex CLI proxy + sandbox

```bash
export https_proxy=http://100.64.0.14:10003
export HTTPS_PROXY=http://100.64.0.14:10003
```

沙箱：**不要 git commit**；claude 后续 commit。

## Read order

1. 本 handoff
2. `.agents/specs/2026-05-02-w11-5-chat-session-postgres.md` 全文（§5 数据流 / §6 schema/接口 / §7 不变量 / §8 边界）
3. `apps/admin-console/backend/api/chat.py:548-624`（现 _SESSIONS dict + SessionContext 类）
4. `apps/miroflow-agent/alembic/versions/V010_add_professor_profile_fields.py`（仿 V015 写法）
5. `apps/admin-console/backend/deps.py`（admin DB 连接模式）

## Files

NEW:
- `apps/miroflow-agent/alembic/versions/V015_add_chat_session_table.py`（spec §6.1 给完整 DDL）
- `apps/admin-console/backend/storage/chat_session.py` — `SessionStore` 类（spec §6.2 给接口）
- `apps/admin-console/tests/test_chat_session_store.py`
- `apps/admin-console/tests/test_chat_session_persistence.py`

MODIFY:
- `apps/admin-console/backend/api/chat.py`
  - 把 `_SESSIONS: dict` 替换为模块级 `_SESSION_STORE = SessionStore(dsn)` 单例
  - `_get_or_create_session` 调 `_SESSION_STORE.get_or_create()`
  - turn / entity 推送后调 `_SESSION_STORE.persist(ctx)`
  - 保留 `_SESSIONS_LOCK` 仅在 in-memory cache 路径（如有）

## Critical decisions（spec 已锁）

- TTL 24h 不变；entities/turns 各上限 5
- worker race 用 ON CONFLICT (session_id) DO UPDATE
- Postgres 不可达 → 退化 in-memory dict（不挂）
- entities / turns 用 JSONB（不用单独表）
- `user_id` 字段加但 W11-5 不用

## Do-not

- ❌ 不动 multi-turn pronoun 解析逻辑
- ❌ 不改 SessionEntity 模型
- ❌ 不实施 W11-1/2/3/4
- ❌ 不加 Redis
- ❌ 不 commit

## Tests / checks

```bash
cd apps/admin-console

# 新单测
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/test_chat_session_store.py tests/test_chat_session_persistence.py \
    -n0 --no-cov -v

# 既有 chat 单测不退化
uv run pytest tests/ -k chat -n0 --no-cov
```

## Done criteria

1. ✅ V015 + SessionStore 实装 + 4 test 全过
2. ✅ chat.py 替换完成；既有 chat tests 不退化
3. ✅ Postgres 不可达退化路径单测过

## Stop conditions

- chat.py 替换破坏现有 multi-turn tests > 3 个 → stop, escalate
- ON CONFLICT 在测试 mock store 不工作 → 检查 psycopg dialect

## Report

```
Summary:
Changed files:
- apps/miroflow-agent/alembic/versions/V015_add_chat_session_table.py (new)
- apps/admin-console/backend/storage/chat_session.py (new)
- apps/admin-console/backend/api/chat.py (modified)
- apps/admin-console/tests/test_chat_session_store.py (new)
- apps/admin-console/tests/test_chat_session_persistence.py (new)

Verification:
- pytest test_chat_session_store / persistence: N passed
- 既有 chat tests: N passed (无退化)

Risks/notes:
- Postgres 不可达退化路径需要在生产环境验证
```
