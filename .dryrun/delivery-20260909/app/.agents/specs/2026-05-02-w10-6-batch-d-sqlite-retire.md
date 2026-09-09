---
title: "W10-6 batch D: admin-console SQLite store 退役（6.2 → 6.3 → 6.4 → 6.5 → 6.6）"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex；claude review
wave: Wave 10
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-04-30-admin-console-architecture.md
  - .agents/specs/2026-04-30-w10-6-1-domains-py-postgres.md  # 6.1 已完
prd_anchor: docs/Agentic-RAG-PRD.md §3 admin-console
---

# W10-6 batch D: admin-console SQLite store 退役

## 1. Goal

W10-6.1 (commit `0b72c77`) 已切 domains.py 6 handler 到 Postgres。`SqliteReleasedObjectStore` 仍被 `batch.py` / `export.py` / `upload.py` / `data.py` 使用。本 batch 完成全部退役 + 模块整合。

## 2. Sub-slice

### 2.1 W10-6.2 batch.py 切 Postgres

`backend/api/batch.py` 用 SQLite store 做 batch 导入预览/确认。改为：从 Postgres canonical 表读 → 写 staging 表（已有 import_batch / source_row_lineage）→ user confirm → promote。

### 2.2 W10-6.3 export.py 切 Postgres

`backend/api/export.py` 用 SQLite store dump JSONL。改读 Postgres canonical 4 域；保持输出 JSONL schema 与现 ReleasedObject 兼容（avoid 破坏下游 collect-trace / visualize-trace）。

### 2.3 W10-6.4 upload.py 切 Postgres + semantic 触发

`backend/api/upload.py` POST /api/upload 现写 SQLite。改为：写 Postgres source_page 原文 + 触发 V3 pipeline（异步 asyncio.create_task）→ professor / paper 域。upload semantic 行为按 user 锁定：source_page raw + trigger pipeline。

### 2.5 W10-6.5 SqliteReleasedObjectStore 退役

删 `backend/storage/sqlite_store.py`（如此名）、相关 tests、依赖；schema dump 文件归档到 `docs/source_backfills/legacy_sqlite_store_2026-05-02.sql`。

### 2.6 W10-6.6 data.py 退役 / domains.py 唯一 endpoint

User 锁定方向：data.py 退役。
- React 现在调 `/api/data/professors` 等 → 加 deprecation alias；将路由 redirect 到 `/api/{domain}` (domains.py)
- 保留 `data.py` 中 chat 用的 helper 函数（提取到 `backend/services/data_helpers.py`，由 chat.py + domains.py 共用）
- 删 data.py 路由定义；逐步删 imports

## 3. Non-goals

- **不**改 React 前端代码（仅 backend redirect）
- **不**改 ReleasedObject schema（保 7 字段兼容输出）
- **不**实施新 chat handler / classifier
- **不**触碰 V3 pipeline 内部

## 4. User-visible behavior

| 端点 | 行为 |
|---|---|
| `/api/upload`（POST） | 写 source_page + 异步触发 pipeline；返 task_id |
| `/api/batch`（POST） | 用 Postgres 做 preview/confirm；不再读 SQLite |
| `/api/export/{domain}` | 输出 Postgres canonical → JSONL；schema 不变 |
| `/api/data/professors` (legacy) | 301 redirect → `/api/professor` |
| React DomainList | 不动；URL 自动 follow redirect |
| SQLite store file | 删除 |

## 5. Affected paths

```
新增：
  apps/admin-console/backend/services/data_helpers.py  # chat.py 用的 SQL 查询 helper（从 data.py 提取）
  apps/admin-console/tests/test_batch_postgres.py
  apps/admin-console/tests/test_export_postgres.py
  apps/admin-console/tests/test_upload_pipeline_trigger.py
  docs/source_backfills/legacy_sqlite_store_2026-05-02.sql  # schema dump 归档

修改：
  apps/admin-console/backend/api/batch.py     # SQLite → Postgres
  apps/admin-console/backend/api/export.py    # SQLite → Postgres
  apps/admin-console/backend/api/upload.py    # SQLite → Postgres + asyncio.create_task pipeline
  apps/admin-console/backend/api/data.py      # 删路由，保 helper（迁到 data_helpers）
  apps/admin-console/backend/api/chat.py      # imports from data_helpers (因为 data.py 退役)
  apps/admin-console/backend/main.py / __init__.py  # 注册 redirect rule

删除：
  apps/admin-console/backend/storage/sqlite_store.py（或同名文件）
  apps/admin-console/backend/storage/{released_object_store, sqlite_*}.py
  apps/admin-console/tests/test_sqlite_store.py（如有）
  apps/admin-console/backend/deps.py: get_sqlite_store dependency

修改 deps.py:
  apps/admin-console/backend/deps.py
    删 get_sqlite_store
    保留 get_pg_conn / get_store / get_retrieval_service
```

## 6. Critical decisions（user 已锁）

- 顺序：6.2 → 6.3 → 6.4 → 6.5 → 6.6（一次性）
- 6.6 方向：data.py 退役，domains.py 为唯一 endpoint
- 6.4 upload semantic：source_page raw + asyncio.create_task pipeline
- 6.5 时机：6.2-6.4 完成后立即；不留长期双轨
- 删 sqlite_store 时 schema 归档，方便回滚

## 7. Invariants

- /api/data/{old} 返 301 redirect（不直接 404；迁移期 30 天）
- 既有 chat tests 不退化（chat.py imports 调整 OK）
- ReleasedObject 输出 schema 不变（W10-6.3 export 保兼容）
- Postgres canonical 4 域 schema 不动（仅 read）
- W10-6.4 upload 失败时不阻塞 HTTP 响应（async 异常 log）

## 8. Validation

```bash
cd apps/admin-console

# 单测
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/test_batch_postgres.py \
                tests/test_export_postgres.py \
                tests/test_upload_pipeline_trigger.py \
                -v

# 既有不退化
uv run pytest tests/ -k "chat or domains or data" -v

# 一致性回归（与 W10-6.1 一致）
TOTAL_DOMAINS=$(curl -s "http://localhost:8088/api/professor?filters=%7B%22institution%22%3A%22%E6%B8%85%E5%8D%8E%E5%A4%A7%E5%AD%A6%E6%B7%B1%E5%9C%B3%E5%9B%BD%E9%99%85%E7%A0%94%E7%A9%B6%E7%94%9F%E9%99%A2%22%7D" | jq -r .total)
TOTAL_DATA_REDIRECT=$(curl -sL "http://localhost:8088/api/data/professors?institution=清华大学深圳国际研究生院" | jq -r .total)
[ "$TOTAL_DOMAINS" = "$TOTAL_DATA_REDIRECT" ] && echo "PASS: $TOTAL_DOMAINS" || echo "FAIL"
```

## 9. Done criteria

1. ✅ batch.py / export.py / upload.py 全 Postgres
2. ✅ SqliteReleasedObjectStore 类删除；schema 归档
3. ✅ data.py 路由 redirect；helper 迁 data_helpers.py
4. ✅ chat.py imports 调整；既有 chat tests 不退化
5. ✅ 5+ 新单测过；既有 admin-console 不退化
6. ✅ 一致性回归 PASS

## 10. Stop conditions

- chat.py 与 data.py helper 紧耦合，提取困难 → escalate；可分 commit 提取
- batch.py 用 SQLite 特有 feature（如 PRAGMA） → 改 Postgres 等价
- 一致性回归 fail（数字不同）→ 检 redirect 路径

## 11. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| 顺序 | 单 batch 6.2 → 6.3 → 6.4 → 6.5 → 6.6 |
| 6.6 方向 | data.py 退役 → domains.py |
| 6.4 upload | source_page raw + asyncio task |
| 6.5 时机 | 6.2-6.4 完成后立即 |
| schema 归档 | docs/source_backfills/legacy_sqlite_store_2026-05-02.sql |
