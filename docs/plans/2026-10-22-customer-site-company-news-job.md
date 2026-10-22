# 客户现场启用企业新闻周任务（B 方案）

> 关联 OpenSpec change：`enable-customer-site-company-news-job`
> 状态：执行中（2026-10-22）· 新闻源已改为 **C：DeepSeek Search connector**（不依赖 Serper/海外支付）；DB/ETL + connector 已验证，runner/cron 待部署
> 关联日志：[执行日志](./2026-10-22-customer-site-company-news-job-log.md)

## 1. 问题

客户现场 `/jobs` 的「企业新闻采集」显示每周一 02:00，但历史为空；点击「立即运行」两次均失败。

服务器证据：

- 任务命令 `["uv","run","python","scripts/run_company_news_ingest.py"]`，服务器没有 `uv`；
  `stderr_excerpt = FileNotFoundError: 'uv'`，3ms 失败。
- 客户候选库 `miroflow_candidate_v2_20260922_r1` 只有 `canonical_v2_alembic_version`；没有
  `company_news_item`，脚本也没有 `DATABASE_URL`。
- 没有 W6 调度器；`crontab` 只有 keepwarm；`job_run` 只有手动失败记录。
- 页面「下次 10:00」与「每周一 02:00」不一致，是 UTC/本地时区显示问题。

## 2. 目标

只让 **企业新闻采集** 在客户现场可运行：

- `/jobs` 手动运行成功，历史有 `succeeded` 和条数；
- 每周一 02:00（服务器本地时间）自动触发，历史显示「周期」；
- 其它采集/导入/Seed/ops 任务保持平台侧执行；
- `/chat`、`/main`、`/browse` 不受影响。

## 3. 方案

### 3.1 数据

- 从构建机 `gpu01` 的 `miroflow_collection_v1` 搬 **42 表 schema-only** 到客户 PG，新建
  `miroflow_collection_v1`；不动服务候选库。
- 用客户 PG 已有的 `miroflow_candidate_v2_20260819_r1.company.current_projection`（7,089 家）
  做 ETL，填 raw `company`/`company_snapshot`；合成一条 `seed_registry` + `import_batch`
  满足外键。
- 新闻源用 **C：DeepSeek Search connector**（国内 key，不依赖 Serper/海外支付）；先用
  `--connector deepseek --company-id <比亚迪>` 验证（实测 5 条），再跑页面任务（默认 top200）。

### 3.2 代码

- `jobs.py`：`uv run python` → 服务 venv Python（`MIROTHINKER_JOB_PYTHON`）；job-only
  `MIROTHINKER_JOB_DATABASE_URL` 传给 child；`next_run_at` 用本地时区。
- `build_job_runtime()` 传入 job DSN；console `DATABASE_URL` 保持不变。
- `run.sh` 增加三个 env；重启服务。

### 3.3 调度

- 新增 `run_scheduled_job.py`：加载 managed secrets、构建 runtime、以
  `trigger_source=schedule` 触发并等待完成。
- cron：每周一 02:00（CST）跑 `company-news-ingest`，日志 `var/jobs-cron.log`。

## 4. 验收

- 新库 42 表；`company=7089`、`company_snapshot=7089`；无重复 credit code。
- 小样本直跑写入 `company_news_item`；页面手动运行 `succeeded`。
- wrapper 写入 `trigger_source='schedule'` 的成功记录；cron 已安装。
- `next_run_at` 显示周一 02:00。
- `/api/health`、`/main`、`/chat` 正常；文档/PDF 更新。

## 5. 回滚

删 cron → 回滚 `jobs.py`/`canonical_v2_jobs.py`/`run.sh` → 重启 → `drop database
miroflow_collection_v1`。服务候选库、serving pack、索引不动。

## 6. 明确不做

其它 6 个采集任务、上传导入、Seed、ops 索引任务；不改 RAG/检索/回答。
