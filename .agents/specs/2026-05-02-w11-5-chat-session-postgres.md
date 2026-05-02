---
title: "W11-5: chat_session Postgres 持久化"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review
wave: Wave 11
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
prd_anchor: docs/Multi-turn-Context-Manager-Design.md
---

# W11-5: chat_session Postgres 持久化

## 1. Goal

当前 `chat.py:548-624` 用 `_SESSIONS: dict[str, SessionContext]` 进程本地内存存会话上下文。重启即丢；多 worker / HA 不可用。

PRD §Multi-turn 持久化要求：会话上下文跨重启可恢复，多 worker 可访问。

**本 spec**：迁移 SessionContext 到 Postgres `chat_session` 表；保留进程内 LRU cache（读热路径）作为优化层。

## 2. Non-goals

- **不**做 Redis 层（Postgres TTL 足够；W12+ 可加 cache）
- **不**改 Multi-turn 解析逻辑（pronoun resolve / topic switch 不动）
- **不**实施 W11-1/2/3/4（其他 chat 改造；本 spec 只动 storage）
- **不**做跨用户隔离（仍按 session_id 维度；user_id 可选字段，留给 Wave 13）

## 3. User-visible behavior

| 场景 | 行为 |
|---|---|
| 重启 admin-console | 旧会话 (24h 内) 仍可恢复 |
| 多 worker / HA | 任一 worker 拿到 session_id cookie 都能 resolve |
| 24h 不活跃 | 自动 GC（cron 或 lazy 清理） |
| pronoun 解析 ("他") | 同前；Postgres 读 entities 列表 |

## 4. Affected paths

```
新增：
  apps/miroflow-agent/alembic/versions/V015_add_chat_session_table.py
  apps/admin-console/backend/storage/chat_session.py（新模块）
  apps/admin-console/tests/test_chat_session_store.py
  apps/admin-console/tests/test_chat_session_persistence.py

修改：
  apps/admin-console/backend/api/chat.py
    - 替换 _SESSIONS dict 为 SessionStore 实例
    - _get_or_create_session 走 store CRUD
    - SessionContext 改 Pydantic（便于 JSONB 序列化）
```

## 5. Data flow

```
HTTP request with session_id cookie
  ↓
SessionStore.get_or_create(session_id)
  ↓ SELECT * FROM chat_session WHERE session_id = %s AND last_seen_at > now() - interval '24h'
  ↓
return SessionContext(entities=jsonb, turns=jsonb, last_seen_at)
  ↓
[handler logic — push_entity / push_turn]
  ↓
SessionStore.persist(session)
  ↓ UPSERT INTO chat_session SET entities=%s, turns=%s, last_seen_at=now()
```

## 6. Schema

### 6.1 V015 alembic

```python
def upgrade():
    op.create_table(
        "chat_session",
        sa.Column("session_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=True),  # reserved for Wave 13
        sa.Column("entities", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("turns", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_session_last_seen_at", "chat_session", ["last_seen_at"])

def downgrade():
    op.drop_index("ix_chat_session_last_seen_at", "chat_session")
    op.drop_table("chat_session")
```

### 6.2 SessionStore 接口

```python
class SessionStore:
    def __init__(self, dsn: str) -> None: ...
    
    def get_or_create(self, session_id: str | None) -> SessionContext:
        """读取 / 创建；自动过滤 24h 过期"""
    
    def persist(self, ctx: SessionContext) -> None:
        """UPSERT 写入 entities/turns/last_seen_at"""
    
    def gc_expired(self, *, ttl_seconds: int = 86400) -> int:
        """DELETE WHERE last_seen_at < now() - ttl；返回清理行数"""
```

## 7. Invariants

- 24h TTL 不变（_SESSION_TTL_SECONDS）
- entities 上限 5（_SESSION_MAX_ENTITIES）— 在 SessionContext 应用层过滤
- turns 上限 5（_SESSION_MAX_TURNS）
- session_id 仍 32 hex（uuid.hex）
- pronoun resolution 不动（操作 SessionContext.entities）
- worker race：UPSERT (ON CONFLICT) 处理；最后写者胜（acceptable for last_seen_at）
- entities/turns serialize via Pydantic model_dump (JSONB-compatible)

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| Postgres 不可达 | log warning + 退化到 in-memory dict（避免 chat 整体挂） |
| session_id 不存在 | get_or_create 创建新行 |
| session 24h+ 不活跃 | get_or_create 不返回（视为不存在；新建） |
| entities JSONB 损坏（手工编辑） | Pydantic validator catch + log；返回空 entities |
| 多个 worker 同时 UPSERT | ON CONFLICT (session_id) DO UPDATE，无竞态 |
| GC 误删活跃 session | 由 last_seen_at 保护；TTL 24h 充足 |

## 9. Validation

```bash
cd apps/admin-console

# 单测
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/test_chat_session_store.py tests/test_chat_session_persistence.py \
    -n0 --no-cov -v

# 既有 chat 单测不退化
uv run pytest tests/ -k chat -n0 --no-cov

# 端到端：发送 query → 重启 worker → 同 session_id 仍记得 entity
# (claude 后续操作)
```

## 10. Done criteria

1. ✅ V015 migration + 单测过
2. ✅ SessionStore CRUD 单测全过
3. ✅ chat.py 替换 _SESSIONS dict；既有 chat tests 不退化
4. ✅ Postgres 不可达时退化路径不挂
5. ✅ 重启 admin-console 恢复测试 PASS

## 11. Stop conditions

- Pydantic JSONB 序列化和现有 SessionContext 不兼容 → 重新 design Pydantic 模型，保留 to_dict / from_dict
- 多 worker 测试看到竞态 → ON CONFLICT 写法错；double check

## 12. Open questions（spec 已锁）

| 问题 | 决策 |
|---|---|
| Redis 层？ | 不加（W12+） |
| user_id 字段？ | 加但 Wave 11 不用 |
| GC 时机？ | lazy（每次 get_or_create 顺手清理 + 后台 cron W12+） |
| TTL 多长？ | 24h（同前） |
