# 客户现场：其余采集更新按钮启用 · 执行日志

关联计划：`2026-10-22-customer-site-collection-task-buttons.md`

## 第 1 轮 · 2026-10-22 · 数据回填 + 限流 + 重启

**做了什么**

- 企业产品输入：从 `company` 生成 `code/docs/专辑项目导出1768807339.xlsx`，200 家企业（有官网），
  sheet 名 `sheet1`。
- 论文/教授回填（采集库 `miroflow_collection_v1`）：
  - `paper` 500 行：200 缺 `abstract`（`needs_enrichment`）、200 缺 `summary_zh`（`ready`）、
    100 个 DOI 待校验（`identity_status='unverified'`）；
  - `professor` 200 行（`identity_status='resolved'`、`profile_raw_text=NULL`）；
  - `source_page` 200 行（`official_profile`）；
  - `professor_seed` 185 行（唯一主页 URL）。
- 安装 `paper-search-mcp==0.1.4`（附带 `pypdf`、`feedparser`、`feedparser-sgmllib`）。
- 6 个非新闻采集任务加 `--limit`：企业产品 50、论文检索 20、摘要 50、DOI 100、
  教授重爬 20、教授论文 10。
- 同步 `jobs.py` 到客户机并重启 `miro-fullstack-v2`（备份 `jobs.py.bak-limit-*`）。

**验证**

- 企业产品 `--limit 1 --dry-run`：exit 0，`companies_considered=1`。
- 论文检索 `--limit 1 --dry-run`：`papers_processed=1`、`abstracts_found=1`、
  `summaries_written=1`、`persist_errors=0`。
- 论文摘要 `--limit 1 --dry-run`：`papers_processed=1`、`summaries_written=1`，
  DeepSeek `POST /chat/completions` 200。
- DOI 校验 `--limit 1 --dry-run`：`papers_total=1`、`papers_processed=1`、
  `papers_unverified=1`。
- 教授重爬 `--limit 5 --apply --confirm-real-db`：`examined=5`、`fetched OK=5`、
  `bio extracted=1`、`bios stored=1`。
- 教授论文 `--dry-run --limit 1`：`profs_processed=1`、`papers_linked_total=4`。
- jobs 测试：101 passed（工作树 `canonical-v2-s11-consolidation`）。

**发现**

- `paper-search-mcp` 缺包会让论文检索在“有数据”时直接 crash；补装后正常。
- `paper-search-backfill --help` 因 help 字符串里的 `% N` 触发 argparse 格式化错误，
  但不影响实际任务运行；属于小 bug，后续可修。
- 教授主页抓取有站点差异：5 条里只有 1 条能抽出有效 bio；任务会继续处理下一条，不会失败。
- `paper-doi-verify` 只选 `identity_status='unverified'`，回填时已按这个条件准备 100 条。
- 企业产品首次真实运行暴露一个 schema 兼容 bug：`company.aliases` 是 `jsonb`，脚本却用
  `%s = ANY(aliases)`，PostgreSQL 报 `WrongObjectType: op ANY/ALL (array) requires array`。
  已改为 `aliases @> to_jsonb(%s::text)`，备份 `run_company_official_product_capture.py.bak-aliases-*`。
  该 bug 只在“名称/注册名都匹配不到、需要查别名”时触发，`--limit 1` 的样例没覆盖到。

**部署与页面级验证**

- 同步 `jobs.py` 后 17:00:57 重启 `miro-fullstack-v2`；启动 11m33s，PID `3269640`；
  `/api/health`、`/main`、`/chat` 均 200。
- 重启后 `task_views()`：7 个采集任务 `available=true`；3 个 ops 仍
  `postgres_unavailable`；导入/Seed 仍为跳转链接。
- 用页面同款 `JobRuntime.trigger(trigger_source='manual')` 触发 `professor-homepage-rescrape`：
  run `6f046e6d-04c9-433e-81af-952c0ad6f320`、`succeeded`、exit 0，20 个候选、19 个抓取成功、
  8 条 bio 入库。
- `jobs.py` mtime 17:00:51，进程启动 17:00:56，确认服务加载的是带 `--limit` 的新任务定义。
- 企业产品真实运行：首次 `ac36338d…` 因 `aliases` jsonb 兼容 bug 失败；修复后
  `22692758…` `succeeded`、exit 0，50 家、111 个页面、40 个产品、`company_product` 28 行。
- 教授论文增量 `16cbf070…`：`succeeded`、10/10 教授、关联 55 篇论文。
- DOI 校验 `fae18beb…`：`succeeded`、exit 0，100 条候选、92 条 pipeline issue。
- 论文摘要 `c45782b4…`：`succeeded`、50/50 条、写入 50 条中文摘要。
- 论文检索 `0659393a…`：`succeeded`、20/20 条、补到 19 条摘要。

**未完成**

- 3 个 ops、3 个导入、2 个 Seed 仍需构建期 PostgreSQL / 上传台账 / Seed 控制台 DB，
  本次未启用；页面继续显示禁用或跳转链接。
