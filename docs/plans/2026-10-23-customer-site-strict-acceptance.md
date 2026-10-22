# 客户现场任务严格验收审计（2026-10-23）

审计对象：本轮为客户现场做的全部变更。
审计方法：不只看页面 `last_status`，逐项核对 `job_run` 的 command/exit/summary、数据库行数、
cron、key 掩码、Seed 运行、ops 可用性，并重跑测试。服务当前 `active`、`/api/health` 200。

## 结论

| 项目 | 结论 | 证据 |
|---|---|---|
| 企业新闻采集 | **PASS** | run `b9f6141b…` `succeeded`、exit 0、200/200 家、抓取 84、写入 36；`company_news_item=109` |
| 新闻周任务 | **PASS** | cron 行存在：`0 2 * * 1 … run_scheduled_job.py company-news-ingest`；`next=2026-10-26T02:00+08:00` |
| 7 个日常采集按钮 | **PASS** | 7 个任务最新 `job_run` 均 `succeeded`、exit 0、command 为 venv Python 且带 `--limit`；7 个 `available=true` |
| 教授采集源（Seed） | **PASS** | `professor_seed=185`；seed 95 预览 run `abe9de28…` `succeeded`；抽样任务 run `fcc493e7…` `succeeded`（items=1） |
| DeepSeek 新 key | **PASS** | 受管库/两个 legacy 文件均后缀 `…504b`、0600；chat resolver 后缀 `…504b`；`api.deepseek.com/v1/models` 200；job 环境 key 匹配 |
| Excel 结构识别 + 分域入库 | **PASS** | 四域识别 high；企业/教授/专利/论文各 1–2 行实测入库并查库命中，测试后已清理；`test_excel_structure` + manual recall API 18 passed |
| 管理台登录 | **PASS（账号可用）** | 23:50 出现 `operator=admin`、`trigger_source=manual` 的新闻采集并成功；未重置密码，无法代替用户验证其口令 |
| 管理台手册/图文/PDF | **PASS** | 三个文件存在；PDF 22 页；含任务/Seed/Excel 章节 |
| 回归测试 | **PASS** | 管理台相关 125 passed / 2 skipped；新闻采集 37 passed |
| `/upload` 结构化导入页 | **FAIL（未实现）** | 仍依赖构建期 PG 和缺失的 `run_admin_upload_import.py` |
| 3 个高级操作 | **FAIL（禁用）** | `task_views` 仍 `postgres_unavailable` |
| 上传内容 chat 自动引用 | **FAIL（阻塞）** | manual 点 active=3、lane 已 append（top cosine 0.8754），answer evidence retention 仍丢弃 |

## 审计中发现的缺口并已修复

- `admin-seed-refresh-sample` 原先只有页面内直跑记录，没有 job gate 的 `job_run`。已补跑：
  run `fcc493e7-4438-4f90-9d46-fee773a54023`，`succeeded`、exit 0、`items_processed=1`。

## 未通过项说明

1. **chat 自动引用**：不是配置问题。manual provider 存在、候选已 append、top score 0.8754，
   但最终答案证据集不带 manual 条目；需要改 answer evidence retention 或新增专用证据车道。
2. **`/upload` 页**：需要构建期 PostgreSQL + 导入脚本；当前可用入口是「数据浏览 → 企业 → 上传文档」。
3. **3 个高级操作**：需要构建库 DSN 和索引工具链，当前服务节点不具备。

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
