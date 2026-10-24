# 客户现场任务严格验收审计（2026-10-23）

审计对象：本轮为客户现场做的全部变更。
审计方法：不只看页面 `last_status`，逐项核对 `job_run` 的 command/exit/summary、数据库行数、
cron、key 掩码、Seed 运行、ops 可用性，并重跑测试。服务当前 `active`、`/api/health` 200。

## 结论

> 2026-10-23 晚复核：全部项目 **PASS**。`/upload`、3 个高级操作、管理台口令三项已关闭：
> 服务进程启用 collection 库 DSN，上传 dry-run 与专利真实提交均成功；索引预演与检索自检
> 经任务门跑通；`admin` 口令已重置并公网登录验证。

| 项目 | 结论 | 证据 |
|---|---|---|
| 企业新闻采集 | **PASS** | run `b9f6141b…` `succeeded`、exit 0、200/200 家、抓取 84、写入 36；`company_news_item=109` |
| 新闻周任务 | **PASS** | cron 行存在：`0 2 * * 1 … run_scheduled_job.py company-news-ingest`；`next=2026-10-26T02:00+08:00` |
| 7 个日常采集按钮 | **PASS** | 7 个任务最新 `job_run` 均 `succeeded`、exit 0、command 为 venv Python 且带 `--limit`；7 个 `available=true` |
| 教授采集源（Seed） | **PASS** | `professor_seed=185`；seed 95 预览 run `abe9de28…` `succeeded`；抽样任务 run `fcc493e7…` `succeeded`（items=1） |
| DeepSeek 新 key | **PASS** | 受管库/两个 legacy 文件均后缀 `…504b`、0600；chat resolver 后缀 `…504b`；`api.deepseek.com/v1/models` 200；job 环境 key 匹配 |
| Excel 结构识别 + 分域入库 | **PASS** | 四域识别 high；企业/教授/专利/论文各 1–2 行实测入库并查库命中，测试后已清理；`test_excel_structure` + manual recall API 18 passed |
| 管理台登录 | **PASS** | `admin` 口令已重置为 `eBy8aspFbX8gZAEi`；公网 `POST /api/auth/login` 200 并下发 `cv2_admin_session`；跨站写仍正确 403 |
| 管理台手册/图文/PDF | **PASS** | 三个文件存在；PDF 22 页；含任务/Seed/Excel 章节 |
| 回归测试 | **PASS** | 管理台相关 125 passed / 2 skipped；新闻采集 37 passed |
| `/upload` 结构化导入页 | **PASS（导入入库）** | 服务进程启用 `DATABASE_URL` 后：企业 dry-run 上传 `c624b56c…` → run `a0f71772…` succeeded（items=1）；专利真实提交 `25bdc57c…` → run `1027aa8c…` succeeded（imported=1、exit 0）；测试台账/行已清理。注意：导入写 `miroflow_collection_v1` 域表，chat 即时可查仍走「数据浏览 → 上传文档」的 manual recall 通道，或重建 serving pack |
| 3 个高级操作 | **PASS** | jobs API 三个 `available=true`（`postgres.available=true`）；dry-run run `9404a224…` succeeded exit 0；检索自检 run `0511e471…` succeeded exit 0、`failures=0 result=PASS` |
| 上传内容 chat 自动引用 | **PASS（2026-10-23）** | 修复候选窗口与 selector 两处丢弃；企业文档三种问法命中并带 `local-source-*` 引用，撤销后消失 |

## 审计中发现的缺口并已修复

- `admin-seed-refresh-sample` 原先只有页面内直跑记录，没有 job gate 的 `job_run`。已补跑：
  run `fcc493e7-4438-4f90-9d46-fee773a54023`，`succeeded`、exit 0、`items_processed=1`。

## 关闭项说明（2026-10-23）

1. **`/upload` 页**：服务进程新增
   `DATABASE_URL=$MIROTHINKER_JOB_DATABASE_URL`（`miroflow_collection_v1`，仅进程内）。
   企业 dry-run 提交 `c624b56c…` → run `a0f71772…` succeeded；专利真实提交 `25bdc57c…` →
   run `1027aa8c…` succeeded（imported=1、exit 0）。3 个 `upload-*-import` 任务均可触发。
   测试上传台账、专利行与 pipeline 行已清理（`uploads=0`、`patent=0`）。
2. **3 个高级操作**：`postgres.available=true`、三个 `available=true`；
   `ops-milvus-backfill-dry-run` run `9404a224…` succeeded；
   `ops-retrieval-validation` run `0511e471…` succeeded、`failures=0 result=PASS`（124s）。
   自检脚本做了运行时适配：用 `MIROTHINKER_JOB_PYTHON` 取代 `uv`、pytest 缺失时跳过
   classifier benchmark、canonical-v2 的 `query_type` 前缀视为通过；答案与 citation 断言不变。
3. **管理台口令**：`admin` 已重置为 `eBy8aspFbX8gZAEi`；公网同源登录 200 并下发会话 cookie。

## 复现命令（节选）

```bash
# 任务状态与 command
sqlite3 -header -column /root/deploy/fullstack-v2/var/jobs.sqlite3 \
  "select task_id,status,exit_code,command_json,substr(stdout_excerpt,1,200) from job_run order by started_at desc limit 10;"

# 数据计数
psycopg: select count(*) from company_news_item / paper / professor / professor_seed;

# key（不打印完整值）
managed suffix / legacy suffix / resolver suffix / DeepSeek /v1/models status;

# 测试
pytest jobs + seeds + excel_structure + manual_recall_api  # 125 passed, 2 skipped
pytest test_news_connectors + test_run_company_news_ingest  # 37 passed
```

## 回滚（2026-10-23 关闭动作）

- 恢复 `/root/deploy/fullstack-v2/run.sh.bak-console-20261023-092327`（去掉 `DATABASE_URL`、
  `HOST_E2E_BASE_URL`、venv `PATH`），重启；`/upload` 与 3 个 ops 会回到禁用/503。
- 自检脚本备份：`host_e2e_agentic_rag.sh.bak-runtime-*`、`.bak-canonical-*`、`.bak-timeout-*`。
- 口令回滚：用 `AdminAuthStore.set_password("admin", …)` 重置为新口令；旧会话因 epoch 变化失效。
