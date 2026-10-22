# 客户现场企业新闻周任务 · 执行日志（只追加）

> 计划：[客户现场启用企业新闻周任务](./2026-10-22-customer-site-company-news-job.md)
> 关联 OpenSpec：`enable-customer-site-company-news-job`

## 第 0 轮 · 2026-10-22 · 立项与取证

**做了什么**

- 读取 `job_run`/`job_task_state`：`company-news-ingest` 两次手动运行 3ms 失败，
  `stderr_excerpt = FileNotFoundError: 'uv'`，`consecutive_failures=2`、`breaker_open=1`。
- 检查客户 PG：`miroflow_candidate_v2_20260922_r1` 仅 1 表；`..._20260819_r1` 88 表、7,089 家企业；
  没有 raw `company/company_snapshot/company_news_item`。
- 检查构建机 PG：`miroflow_collection_v1` 有 42 表 raw schema，但数据为空（11MB）。
- 检查 `crontab`/systemd：无调度器；`job_run` 无周期记录。
- 检查任务命令：全部 `uv run python ...`；客户机无 `uv`。

**发现**

- 失败不是网络/配额，是缺 `uv` + 缺 raw 采集库 + 无调度器。
- 客户现场是服务节点；但可以用 canonical 企业数据 + 42 表 schema 建一个独立采集库，
  只启用 `company-news-ingest`（B 方案）。

**怎么验证**

- 上述证据均来自只读 SQL/文件检查；未改生产。

**影响哪些问题**

- 企业新闻采集手动失败、周任务无历史、`next_run_at` 10:00/02:00 不一致。

**下一步**

- 建 OpenSpec/验证契约/人读计划；搬 schema；ETL；小样本直跑；改 runner；装 cron。

## 第 1 轮 · 2026-10-22 · 建库、ETL、小样本直跑

**做了什么**

- 从构建机 `gpu01` 的 `miroflow_collection_v1` 导出 **schema-only**（42 张表，96KB），在客户 PG
  新建 `miroflow_collection_v1` 并恢复；42 表校验通过。
- 用 `miroflow_candidate_v2_20260819_r1.company.current_projection` 做 ETL：
  - `company` 7,089 行；`company_snapshot` 7,089 行；`company_news_item` 0 行；
  - `unified_credit_code` 重复 0；抽样 5 家名称/网站正常。
- 直接用服务 venv Python 跑
  `run_company_news_ingest.py --priority all --limit 2 --connector serper`：
  - `companies_total=2`、`companies_processed=2`、`news_fetched=0`、`news_inserted=0`；
  - 日志：`Serper fetch failed ... 400 Client Error: Bad Request for url: https://google.serper.dev/news`。

**发现**

- Serper key 本身有效但**没有额度**：直测 `/search`、`/news`、`/news_tbs` 均返回
  `400 {"message":"Not enough credits"}`。
- Bocha key 可用（200），但样例企业的结果偏题（西锐/尚学等），不是新闻；
  DeepSeek Search key 可用（200），但样例返回百度百科/企业年报，不是新闻。
- `SerperNewsConnector` 把 400 当“无新闻”返回 `[]`，所以任务会显示成功但 `news_fetched=0`；
  这是质量陷阱，不能把这种“成功”当成验收。
- 数据面已就绪，但**新闻源是外部阻塞**：没有额度/没有新闻专用 token，周任务跑了也写不进新闻。

**怎么验证**

- `company`/`company_snapshot` 计数、重复 credit code 查询、5 行抽样。
- Serper/Bocha/DeepSeek 直测状态码与样例结果（未打印 key）。
- 小样本直跑输出 JSON。

**影响哪些问题**

- `company-news-ingest` 仍然不能产出新闻；在新闻源解决前，不应安装 cron 或宣称 B 完成。
- 新库/ETL 是 additive，不影响 `/chat`/`/main`；服务仍未重启，页面仍会因缺 `uv` 失败。

**下一步（需决策）**

1. 给 Serper 充值（最快；现有 connector 就是新闻专用）。
2. 提供 CNStock/Tushare 等新闻 token（现有 connector 可直接用）。
3. 或新增 Bocha/DeepSeek 新闻 connector（需调 query/过滤，样例质量不足，风险较高）。

## 第 2 轮 · 2026-10-22 · 充值复核

**做了什么**

- 用户选择方案 A（给 Serper 充值）后，重新直测 managed key 与 legacy `.serper_api_key`：
  - `POST https://google.serper.dev/search` → `400 {"message":"Not enough credits"}`
  - `POST https://google.serper.dev/news` → `400 {"message":"Not enough credits"}`
- 两个 key 均无额度，说明充值尚未到账/未充到对应账号。

**结论**

- 新闻源仍不可用；不跑全量、不装 cron、不改 runner/重启服务。
- 数据面（新库 42 表、7,089 企业/快照）保持就绪，等服务端额度恢复后继续小样本验证。

**额度复核（同一轮补充）**

- `GET https://google.serper.dev/account`（带 managed key）返回：
  `{"balance": -11, "rateLimit": 50}`。
- key 有效（账号接口 200），但余额为 **-11**，所以 `/search`、`/news` 全部
  `400 Not enough credits`。充值需要先把负数补平；补到正数后再复测。

## 第 3 轮 · 2026-10-22 · 新 DeepSeek key + C 方案新闻 connector

**做了什么**

- 新 DeepSeek key 直测：`/v1/models`、`/v1/tools/search`、`/v1/chat/completions` 均 200。
- 通过 `ManagedSecretsStore.patch` 写入受管密钥库 `llm.api_key`（原子写、0600、审计）；
  备份 `secrets.json`；页面掩码预期变为 `sk-…504b`。
- 扫客户现场可能绕过受管库的位置：
  - `code/.deepseek_api_key`、`bootstrap/keys/.deepseek_api_key` 均为旧 key；已备份并更新为新 key（0600）。
  - `code/apps/miroflow-agent/.env` 无 `DEEPSEEK_API_KEY`；服务进程环境无 `DEEPSEEK_API_KEY`。
- 新增 `DeepSeekNewsConnector`（`news_connectors/deepseek.py`），接入
  `run_company_news_ingest.py` 的 `deepseek` connector，并加入 `all`：
  - 查询 `公司名 最新新闻 动态 -招聘 -招标`，`ori_question` 带原问题；
  - 过滤百科/天眼查/企查查/研报/股价/招聘等噪声；
  - 要求公司名或核心名命中；无日期时要求 news-like URL；authority ≥2；日期在 since 内。
- 直跑验证：
  - 比亚迪股份有限公司：`news_fetched=5`、`news_inserted=5`；
  - 深圳市尚锐科技有限公司：`news_fetched=0`（无近期新闻，过滤掉旧文/百科/年报），符合预期。
- `company_news_item` 当前 5 行（比亚迪样例）。

**发现**

- C 方案可行：DeepSeek Search + 过滤能产出真实新闻，不依赖海外支付。
- Serper 不再作为依赖；其 400 无额度只会在 `all` 下产生 warning，不影响 DeepSeek 结果。
- 服务仍需重启才能让 chat/LLM 与服务进程采用新 key；runner/DSN/cron 尚未部署。

**下一步**

- 改 `jobs.py`（uv→venv Python、job DSN、时区）、`run.sh` env、scheduler wrapper；
- 备份并重启一次（同时应用新 key）；
- 页面手动跑 `company-news-ingest`，再装周一 02:00 cron。

## 第 4 轮 · 2026-10-22 · runner/DSN/时区/cron 落地，首次全量运行成功

**做了什么**

- 客户部署打补丁（均有 `.bak-20261022-*`）：
  - `.../canonical_v2/jobs.py`：新增 `MIROTHINKER_JOB_PYTHON`、`MIROTHINKER_JOB_DATABASE_URL`、`MIROTHINKER_JOB_TIMEZONE`；`uv run python` 在触发前替换为服务 venv Python；`next_run_at` 按配置时区计算。
  - `.../api/canonical_v2_jobs.py`：`build_job_runtime()` 把 job DSN 作为 `console_dsn` 传入（只影响任务子进程）。
  - `/root/deploy/fullstack-v2/run.sh`：导出上述三个变量（job 库 `miroflow_collection_v1`、时区 `Asia/Shanghai`、解释器 `.venv/bin/python`）。
  - 新增 `apps/admin-console/scripts/run_scheduled_job.py`，用于 cron 触发 `trigger_source=schedule`。
- 新 DeepSeek key 写入受管密钥库 `llm.api_key`（掩码 `sk-…504b`）；`code/.deepseek_api_key`、`bootstrap/keys/.deepseek_api_key` 同步更新；调度 wrapper 环境已确认 `DEEPSEEK_API_KEY` 存在且后缀 `…504b`。本地开发仓库的 `.deepseek_api_key` 与 `apps/miroflow-agent/.env` 也已替换为新 key（保留 0600 备份）。
- 15:20:45 重启 `miro-fullstack-v2`；启动约 10 分 36 秒，15:31 左右 `/api/health` 200；外部 `/main`、`/chat` 均 200。
- 复位 `company-news-ingest` 熔断（`consecutive_failures=0`、`breaker_open=0`）。
- 15:33:15 触发首次全量手动运行（run `b25e184e-9bfc-49d7-b5df-8559c45e73e5`）：
  - `status=succeeded`、`exit_code=0`、`duration_ms=566370`（约 9 分 26 秒）；
  - `command_json=["/root/deploy/fullstack-v2/.venv/bin/python","scripts/run_company_news_ingest.py"]`（不再调用 `uv`）；
  - `companies_total=200`、`companies_processed=200`、`news_fetched=68`、`news_inserted=68`、`companies_with_errors=0`；
  - `company_news_item` 5 → 73 行；Top 公司：`company-c-05f933…` 7 条、`company-c-060678…` 6 条。
- 安装 cron（保留 keepwarm）：
  `0 2 * * 1 cd /root/deploy/fullstack-v2 && .venv/bin/python code/apps/admin-console/scripts/run_scheduled_job.py company-news-ingest >> var/jobs-cron.log 2>&1`
- `next_run_at` 实测 `2026-10-26T02:00:00+08:00`，`schedule_display=每周一 02:00`。

**发现**

- Serper 仍返回 `400 Not enough credits`，但 `all` 下只记 warning；DeepSeek 独立产出 68 条，任务整体成功。
- 任务允许窗口为 UTC 17–22（北京时间 01:00–06:00）。周一 02:00（UTC 周日 18:00）在窗口内。
- 15:44 用调度 wrapper 做链路验证（run `7b908575-cfef-4c33-adc4-9c1d0e18655c`），因当前是 UTC 07:44、在窗口外，记录为 `trigger_source=schedule`、`status=skipped`、`skip_reason=outside_window`。这是窗口保护生效，不是故障；周一 02:00 不会跳过。
- 调度 wrapper 的环境确认注入了新 key；实际任务子进程未持久化任何环境值。

**怎么验证**

- `job_run` 两条记录（manual succeeded / schedule skipped）见上；`command_json` 为 venv Python。
- `company_news_item` 行数 73；按 `company_id` 分组 Top 5 已核对。
- `task_views()` 输出 `next_run_at=2026-10-26T02:00:00+08:00`、`available=True`。
- 外部 `https://gxzx-coze-api.idea.edu.cn/main`、`/chat`、`/api/health` 均 200。
- 仓库测试：新闻 connector/脚本 37 passed；jobs runner 29 passed；jobs API/registry/store 共 97 passed（工作树 `canonical-v2-s11-consolidation`）。

**影响哪些问题**

- 企业新闻采集从“点了必失败”变为“每周一 02:00 自动跑 + 可手动补跑”；其它任务仍不在本机跑。
- 管理台手册和图文版已改为“企业新闻可立即运行、其它任务不要点”，PDF 已重生成（22 页）。
- 遗留：调度 wrapper 在真实周一 02:00 的首次自动运行仍待自然到达后复核；本次已用固定时钟单测覆盖窗口判定。

## 第 5 轮 · 2026-10-22 · 任务按钮可用性系统测试

**做了什么**

- 读 `/jobs` 前端 `actionsCell()`：7 个日常采集显示可点的「立即运行」；3 个高级操作 `available=false` 显示禁用按钮；3 个导入 + 2 个 Seed 有 `token_params`，只显示「去上传导入页 / 去 Seed 管理页」链接。
- 用真实服务环境调 `task_views()`：7 个采集 `available=true`；3 个 ops `postgres_unavailable`；导入/Seed `available=true` 但页面不给运行按钮。
- 沙箱（临时 jobs.sqlite3 + fake spawn，不写生产历史）逐个跑 `trigger` gate：
  - 7 个采集任务全部 accepted，命令已解析为 venv Python；
  - 3 个 ops 全部 `JobPostgresUnavailableError`；
  - 3 个导入在页面只显示跳转链接；上传台账 `var/uploads.sqlite3` 为空，上传页因无 PG 隐藏提交入口；
  - 2 个 Seed 在 gate 层 accepted（`seed_id` 只校验数字），但 Seed 页依赖 `DATABASE_URL`，当前不可用。
- 限 1 条 + dry-run 实测：
  - `company-official-product-capture --limit 1 --dry-run` → `exit 1`，默认输入 `docs/专辑项目导出1768807339.xlsx` 不存在；
  - `paper-search-backfill`、`paper-summary-zh-backfill`、`paper-doi-verify` → `exit 0`、0 条（采集库无论文）；
  - `professor-homepage-rescrape --limit 1`（未加 `--apply`）、`professor-homepage-paper-ingest --dry-run --limit 1` → `exit 0`、0 条（采集库无教授）。
  - `paper-search-backfill` 另有 warning：`paper_search_mcp` 未安装。

**发现**

- 按钮“能点”不等于“能跑成”：只有企业新闻采集端到端可用。
- 企业官网产品任务缺默认 XLSX，点了会立即失败。
- 论文/教授任务会成功但 0 条，因为采集库只回填了企业数据；论文检索回填还缺 `paper_search_mcp`。
- ops「更新检索索引」仍被禁用：本机没有构建期 PG DSN；导入/Seed 页也因无 PG 不可用。

**怎么验证**

- `task_views()` 输出、gate 沙箱结果、5 个 dry-run 的 `exit code` 与 JSON 汇总均已记录。
- 未实际触发企业产品、论文、教授、ops、导入、Seed 的真实写库运行；避免在客户生产库产生非预期写入。

**影响哪些问题**

- `docs/管理台运维手册.md` §7.3 的“本机可运行”列改为实测结果，并新增测试结论块。
- 对客口径不变：只建议点「企业新闻采集」的「立即运行」；其它按钮不要点。
