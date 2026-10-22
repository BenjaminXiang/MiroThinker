# 客户现场：教授采集源（Seed）可用 · 执行日志

关联计划：`2026-10-22-customer-site-seed-console.md`

## 第 1 轮 · 2026-10-22 · Seed-only DSN + 重启

**做了什么**

- `backend/console_dsn.py`：新增 `CANONICAL_V2_SEED_DATABASE_URL` 与 `resolve_seed_dsn()`
  （seed DSN > `DATABASE_URL` > `DATABASE_URL_TEST`）。
- `backend/api/canonical_v2_seeds.py`：`require_postgres` 在显式 seed DSN 下放行；
  `_seed_connection` 使用 seed DSN。
- `backend/api/seeds.py`：新增 `get_seed_pg_conn`，6 个 `/api/seeds` 路由改用它；
  `_run_seed_task` 使用 `resolve_seed_dsn()`。
- 客户 `run.sh` 增加：
  `export CANONICAL_V2_SEED_DATABASE_URL="$MIROTHINKER_JOB_DATABASE_URL"`；
  **没有**设置 `DATABASE_URL`，ops/上传面保持原状。
- 备份 `*.bak-seed-*`；同步三个后端文件；重启 `miro-fullstack-v2`。

**验证**

- 单测：`test_canonical_v2_seeds_api.py` 6 passed、2 skipped；`test_seeds_api.py` 集成用例
  在无 PG 环境下 30 skipped。
- 新增回归：`test_seed_dsn_env_bypasses_the_postgres_gate`（显式 seed DSN 放行，gate 仍为 false）。
- 服务重启后：`active`、PID `1589741`、`/api/health` 200；`/main`、`/chat` 200。
- 服务进程有 `CANONICAL_V2_SEED_DATABASE_URL`，**没有** `DATABASE_URL`。
- Seed 连接：`get_seed_pg_conn()` + `list_seeds()` 返回 185 行，首条 id=95 中山大学（深圳）。
- 旧 `/api/seeds` 触发路径：`trigger_seed_run(95, preview)` → 202，run `a616cf22…`，
  seed 95 `last_run_status=success`。
- 旧 `/api/seeds` 抓取路径：`trigger_seed_run(95, sample, limit=5)` → 202，
  run `3cddc244…`，`pipeline_run.status=succeeded`、`items_processed=1`。
- Job 路径：`admin-seed-refresh` run `abe9de28…` `succeeded`，`items_processed=1`，
  `seed_status=success`。
- 隔离：3 个 ops 仍 `postgres_unavailable`；上传页仍无构建 PG。

**发现**

- `seeds.html` 实际调用旧 `/api/seeds`，不是 V2 路由；只改 V2 路由不够，必须同时改旧路由的
  连接依赖。
- 不能在服务环境里直接设 `DATABASE_URL`：会同时把 3 个 ops 和上传页打开，导致“按钮可点但
  必失败”。seed-only 变量是必要的隔离。
