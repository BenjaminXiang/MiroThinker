---
title: "W13-9: MILVUS_USE_REAL_CLIENT 显式化（避免生产 silent 0 hits）"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（小修）；claude review
wave: Wave 13 follow-up
related_findings: docs/solutions/integration-issues/v2-stage3-company-top5-eval-2026-05-02.md §7
---

# W13-9: MILVUS_USE_REAL_CLIENT 显式化

## 1. Goal

`apps/miroflow-agent/src/data_agents/storage/milvus_collections.py:148-159` 全局 monkey-patch：默认 `.db` URI 走 in-memory mock client，必须 `MILVUS_USE_REAL_CLIENT=1` 才用真 Milvus。

- 单测时正确（避免污染真 Milvus）
- 但 admin-console 生产部署默认 silent 走 mock → 所有 chat / retrieval query 0 hits 而不报错
- 当前生产正确仅因 systemd 启动脚本恰好设了 env（不在仓库代码 / 文档里）

V2 Stage 3 实测时**已差点犯错**：50/50 query 0 hits 直到加 env 才正常。任何新部署 / 本地 dev / docker compose 都会踩。

## 2. Affected paths

```
修改：
  apps/admin-console/backend/main.py
    顶部加：os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")
    （在 import pymilvus / from backend.deps import ... 之前）

  CLAUDE.md §5 Common commands 加一行注：
    "ops: MILVUS_USE_REAL_CLIENT=1 必须设；admin-console main.py 已 setdefault"

  apps/admin-console/README.md（如不存在则创建）
    Quickstart + env 说明：MILVUS_USE_REAL_CLIENT=1 / DATABASE_URL / SERPER_API_KEY

新增测试：
  apps/admin-console/tests/test_main_milvus_env.py
    - import backend.main 后 os.environ['MILVUS_USE_REAL_CLIENT'] == '1'
    - 已经显式设 '0' 时不被覆盖（setdefault 正确）
```

## 3. 备选方案（更激进）

修改 `milvus_collections.py:148-159`：默认走真 client，仅当 `MILVUS_FORCE_MEMORY=1` 或 pytest fixture 显式 patch 时走 mock。

但这会让所有现有单测改 fixture（影响大）。本 spec 选**最小改动**：admin-console 启动时 setdefault，不动 monkey-patch 默认行为。

## 4. Validation

```bash
cd apps/admin-console
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/test_main_milvus_env.py -v
```

## 5. Done criteria

1. ✅ admin-console main.py 启动时 setdefault MILVUS_USE_REAL_CLIENT=1
2. ✅ test_main_milvus_env.py pass
3. ✅ CLAUDE.md / admin-console README 显式说明
4. ✅ 既有 chat regression 不退化
5. ✅ 重启 admin-console 后 curl `/api/chat` 仍能命中（host 实测）

## 6. 可见性 follow-up

- 加 healthz endpoint 检查 Milvus 是否真的有 ready data（4 collection row count > 0）
- admin-console 启动 log 第一行打印 "Milvus URI=..., MILVUS_USE_REAL_CLIENT=..., collections=[...]"
