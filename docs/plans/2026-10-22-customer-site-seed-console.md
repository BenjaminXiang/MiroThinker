# 客户现场：教授采集源（Seed）可用（2026-10-22）

关联 OpenSpec：`enable-customer-site-seed-console`

## 1. 问题

`/seeds` 页面（教授采集源）显示「控制台没有配置数据库（DATABASE_URL）：seed 管理不可用」，
「检查名册 / 开始抓取」都不能用。采集库已有 `professor_seed` 185 行，种子刷新任务也具备运行条件。

## 2. 方案

- 新增 `CANONICAL_V2_SEED_DATABASE_URL`，只给 Seed 面使用：
  - V2 Seed API：`require_postgres` / `_seed_connection` 用它；
  - 旧 `/api/seeds`（`seeds.html` 实际调用的路由）：连接依赖改为 `get_seed_pg_conn`；
  - 后台 `_run_seed_task` 也用它。
- `run.sh` 导出该变量指向 `miroflow_collection_v1`，**不设置** `DATABASE_URL`。
- 这样 ops/上传页仍保持不可用，不会把构建按钮误开。

## 3. 验收

- `/seeds` 能列出 185 条 Seed。
- 「检查名册」/「开始抓取」触发 `admin-seed-refresh`，运行历史出现记录。
- 3 个 ops 仍 `postgres_unavailable`；上传页仍提示无构建 PG。
- `/api/health`、`/main`、`/chat` 200。

## 4. 回滚

删除 `CANONICAL_V2_SEED_DATABASE_URL`，恢复 `console_dsn.py` / `canonical_v2_seeds.py` /
`seeds.py` 的 `.bak-seed-*`，重启。
