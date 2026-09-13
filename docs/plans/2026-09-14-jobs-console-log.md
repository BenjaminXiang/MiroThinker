# 任务运行面（W2）执行日志

> 只追加（append-only）。每轮一条：**做了什么 → 发现 → 怎么验证 → 影响哪些问题**。
> 上游规划 [`2026-09-07-system-wrapup-config-center-and-periodic-refresh.md`](./2026-09-07-system-wrapup-config-center-and-periodic-refresh.md)
> §3.2(d) 任务运行面 / §4 C3 / §5.2 调度方案 / §5.5 成本护栏 / §6 W2 验收线 / §2 原则 4 降级；
> change-id `add-admin-jobs-console`；证据目录 `.agents/runs/admin-jobs-console-w2/`；
> 分支 `feat/admin-jobs-console`（worktree `.worktrees/admin-jobs-console`，基线 = W5 分支尖 `08b8e4d9`）。

---

## 2026-09-14 · 第 1 轮：白名单任务表、同一道闸门、运行记录与 /jobs 页（W2）

### 做了什么

1. **独立 worktree**：`.worktrees/admin-jobs-console`（分支 `feat/admin-jobs-console`，从 W5 的
   `feat/admin-audit-logs` 尖 `08b8e4d9` 拉出）。全程未重启 18188、未碰 live 资产与数据卷、未碰
   `canonical-v2-s11-consolidation` / `data-rebuild` / `admin-config-center` / `admin-audit-logs` 四个 worktree。
2. **声明式任务表**（`apps/miroflow-agent/src/data_agents/canonical_v2/jobs.py`，与 W1 的
   `managed_config.py` 同目录同模式，便于将来 cron 入口复用同一道闸门）：任务 id → **固定 argv 元组**、
   工作目录、超时、展示用节奏（cron 表达式 + 中文文案）、开关来源、配额类别、是否需要 PG、是否受夜间窗口约束。
   9 条任务：§5.3 的 7 条采集任务 + §4 C3 的两条任务运维动作（Milvus 回填、检索验证，各带一个干跑变体）。
   **唯一的运行期参数**是 `ops-milvus-backfill*` 的 `domain`（闭集四值），且只在整 token 占位符上做替换，
   调用方文本永不拼接进命令行、全程 `shell=False`。
3. **同一道闸门**（`JobRuntime.trigger`，手动与将来 cron 共用同一个函数，顺序即语义）：
   解析任务 → 参数闭集校验 → **PG 探测**（需 PG 的任务）→ **熔断**（连续 2 轮失败）→ **受管配置开关**
   （关则空跑并如实记录）→ **配额上限**（为 0 则拒绝并记录）→ **flock 防重入锁**（跨进程，非阻塞）→
   写 `running` 行 → 后台线程执行。手动触发**不跳过任何一道**。
4. **运行记录落 serving 侧 SQLite**（`CANONICAL_V2_JOBS_DB`，未配置时回落到 `CANONICAL_V2_ACCESS_LOG_DB`
   同目录的 `jobs.sqlite3`，与 `corrections.sqlite3` / `access-logs.sqlite3` 同目录同模式）：`job_run`
   （任务、触发来源、操作人、开始/结束、状态、退出码、耗时、条数、失败摘要与 stdout/stderr 尾部片段）+
   `job_task_state`（连续失败数、熔断开关、最近成功/失败）。**子进程环境永不入库**，片段按
   `key=value`（键名含 api_key/token/secret/password 等）与 `Bearer <token>` 两条规则脱敏。
5. **HTTP 与页面**：`GET/POST /api/canonical-v2/admin/jobs*`（清单 / 触发 / 历史 / 运行详情 / 熔断复位），
   新静态页 `/jobs`（与 `/browse`、`/logs`、`admin.html` 同体系、同一条共享导航），展示任务清单、节奏与
   下次运行时间、闸门徽标、最近运行与**失败红点**、"立即采集"按钮、运行历史与失败样例入口。
6. **降级**（§2 原则 4）：PG 探测为**懒式 + 30 秒 TTL + fail-soft**，无 PG 时需 PG 的任务
   `available=false`（页面隐藏触发按钮）且触发返回 503 `job_postgres_unavailable`；**进程启动不受影响**，
   PG 恢复后无需重启；运行记录库不可解析时整个 jobs 面返回 503 `jobs_storage_unavailable`，
   其余 admin 面不受影响。
7. **测试**：4 个新测试文件共 **78 个用例**（白名单闭集 35 / 运行记录 11 / 闸门与执行 20 / HTTP 与降级 12）；
   scratch 端口 **18291**（非 18188）桩任务真实 HTTP 冒烟，七条断言全过；`apps/admin-console` 全量套件
   改前/改后各一次并做失败集差异。

### 发现

1. **`pipeline_run` 在服务机不存在（与 §5.2 描述不符，重要）**：规划 §5.2 写"运行记录落 `pipeline_run` 表（已有）"，
   但该表是构建期 Postgres 表：18188 服务进程由 `serve_s12e_port.py → complete_candidate_runner.py` 以
   `--database-url` **命令行参数**启动，**不导出** `DATABASE_URL` / `CANONICAL_V2_DATABASE_URL` 环境变量；
   W1 的 `canonical_v2_admin_status.py:508-517` 也已把 `collection_history` 标为
   `unavailable("…pipeline_run history lives in the build/release database, not on the serving host")`。
   因此本片把运行记录落在 serving 侧 SQLite（与 corrections/access-logs 同目录同模式的既有约定），
   **不把 `pipeline_run` 当服务机数据源**；将来若服务机可达构建库，再评估镜像同步（本片不做）。
2. **"下次运行时间"目前没有自动来源**：`deploy/cron/` 不存在，crontab 只有 03:17 备份与 03:41 日志清理，
   没有任何采集条目；§5.2 的声明式 cron 表是 W6 的工作。本片让任务表**声明**节奏（cron 表达式），
   由页面按本地时区算出"下次运行"，并明确"改节奏走 cron 安装流程、不进 UI"。
3. **§5.3 与脚本实际默认行为有两处偏差**：① `run_profile_bio_rescrape.py` **默认就是干跑**，写库要显式
   `--apply --confirm-real-db`，所以白名单条目把写意图**显式写出来**（页面任务名标注"写入域库"），
   不让"每月重爬"变成事实上的空跑；② §5.3 的论文行把摘要中文回填与 DOI 校验两条脚本并在一个节奏下，
   本片拆成两条任务，失败可以归因到具体脚本。
4. **§5.5 的"每脚本每轮 max calls"目前只存在于规划**：脚本里没有计数/自停实现。本片落地的是**闸门侧**——
   配额上限取 W1 的受管配置（`collection.max_web_searches_per_run` / `max_llm_calls_per_run`），为 0 直接拒绝
   并且**如实记录为一次 skipped**；同时把生效上限通过 `MIROTHINKER_MAX_*_PER_RUN` 传给子进程、写进运行行，
   让"这一轮被允许花多少"可审计。**脚本内部的逐次计数属于 W6 接线**，本片不冒充已实现。
5. **窗口语义需要拍板（已在设计文档显式记录）**：§5.5 说"全部任务限夜间窗口"，而 D1 又要求"立即采集"可用。
   本片的处理是：夜间窗口（W1 的 `collection.window_*_hour_utc`）对**周期触发（schedule）生效**，
   对**手动触发只记录不拦截**（`window_bound` / `inside_window` 落在运行行上，页面可见）；
   手动触发仍然完整通过开关、配额、熔断、防重入四道闸门——这正是 §3.2(d) 逐条列举的约束集合。
   若甲方要求手动触发也必须在窗口内，改一行参数即可（已是同一个函数）。
6. **旧 SPA 的两条任务运维动作在 V2 壳上是 404**：`backend/api/pipeline.py` 的
   `POST /api/pipeline/runs/{run_id}/milvus-backfill` 与 `…/retrieval-validation` 从未挂到 V2 壳，
   且都要求父 `pipeline_run` 行（构建期 PG）。本片以**固定命令**形式重挂为 `ops-milvus-backfill*` /
   `ops-retrieval-validation`（父级 bookkeeping 去掉，因为服务机上没有那个表），两者仍标 `requires_postgres=True`，
   在无 PG 现场**优雅降级**而不是报 500。
7. **一处需要留意的既有事实**：§3.2(a) 的"各域数据新鲜度 = pipeline_run 最近成功"在服务机同样没有数据源；
   本片的运行记录（`job_task_state.last_success_at`）天然是服务机上一手的新鲜度来源，但**本片不改 W1 的
   系统状态面板**（跨片改动，留给需要它的切片接线），此处如实记录为已知缺口。

### 怎么验证

- **RED**：4 个测试文件先写后实现，改前代码上是 4 个收集错误
  `ModuleNotFoundError: No module named 'src.data_agents.canonical_v2.jobs'`（`red-run-before-change.txt`）。
- **GREEN**：78 个新用例全绿（白名单闭集 / 参数注入拒绝 / 同进程与**跨进程**防重入 / 开关空跑 /
  配额为 0 / 熔断与复位 / 成功清零 / 运行记录持久化与脱敏 / PG 降级 / 失败红点 / next-fire 计算）。
- **桩任务真实 HTTP 冒烟**（`scratch-18291-*.json|txt`，scratch 库与 scratch 受管配置，端口 18291）：
  ① 白名单任务触发成功并入历史（`status=succeeded duration_ms=3015 items_processed=2`）；
  ② 运行中重复触发 → `409 job_already_running`；③ 完成后历史可见、失败样例可取
  （`stderr_excerpt` 里 sentinel 显示为 `api_key=[redacted]`）；④ 失败任务 `failure_flag=true`（红点）；
  ⑤ 连续 2 轮失败后第三次触发 → `409 job_breaker_open`（`breaker_open=true consecutive_failures=2`）；
  ⑥ 无 PG 环境下桩 PG 任务与**真实** `ops-milvus-backfill` / `ops-retrieval-validation` 均
  `503 job_postgres_unavailable` 且清单里 `available=false`；⑦ 开关关闭 → `202 skipped(switch_off)`，
   配额 0 → `202 skipped(quota_exhausted)`；附：真实任务参数注入 → `422 job_invalid_params`、未知任务 → 404、
   `/jobs` 页面 200。
- **全量套件**：`apps/admin-console` 改前/改后各跑一次 `uv run pytest -q`，失败集 `comm` 差异见
  `failures-before.txt` / `failures-after.txt`（结论见 `verification.md`）。
- **未验证项（如实声明）**：不跑任何真实采集（不消耗 Bocha/Serper/LLM 配额）；不装 cron（W6）；
  不写 `pipeline_run`；不接 W1 系统状态面板的新鲜度。

### 影响哪些问题

- 收尾规划 **§6 W2 验收线**（任选白名单任务手动触发成功并入历史 / 运行中重复触发被锁拒绝并提示 / 失败任务红点）
  三条全部落地并有真实 HTTP 证据；§3.2(d) 的"清单 + 下次运行 + 历史 + 失败样例 + 立即采集（同一闸门）"全部在页面上。
- **§4 C3** 的两条任务运维动作从"旧 SPA 断链（404）"变为"白名单任务 + 无 PG 时优雅降级"。
- **§5.5** 的成本护栏：熔断（连续 2 轮失败）与配额闸门落地；逐次计数仍待 W6 接线（已在设计文档写明边界）。
- **W6 的前置**：任务表的 argv/节奏/闸门元数据、`flock` 锁文件、运行记录库即是 W6 cron 入口要复用的东西；
  W6 只需写 cron 声明表 + 安装脚本 + 在脚本内接配额计数。
- **W8 的素材**：`/jobs` 页可作日常运维手册的操作面截图；恢复/熔断复位流程已可在页面上演示。
