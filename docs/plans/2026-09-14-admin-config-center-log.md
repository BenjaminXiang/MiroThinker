# 管理配置中心（W1）执行日志

> 只追加（append-only）。每轮一条：**做了什么 → 发现 → 怎么验证 → 影响哪些问题**。
> 关联文档：干跑盘点 [`2026-09-14-admin-config-center-dry-run.md`](./2026-09-14-admin-config-center-dry-run.md)；
> 上游规划 [`2026-09-07-system-wrapup-config-center-and-periodic-refresh.md`](./2026-09-07-system-wrapup-config-center-and-periodic-refresh.md) §3 / §6；
> change-id `add-admin-config-center`；证据目录 `.agents/runs/admin-config-center-w1/`。

---

## 2026-09-14 · 第 1 轮：干跑盘点 + 首片落地（配置中心 MVP）

### 做了什么

1. **独立 worktree**：`.worktrees/admin-config-center`（分支 `feat/admin-config-center`，基于线上活线 commit
   `f961eece`）。全程未碰 `.worktrees/canonical-v2-s11-consolidation`（18188 活线）与 `.worktrees/data-rebuild`
   （另有一个 20 小时数据重建在跑），未重启任何服务、未改 live 资产。
2. **真干跑**：读活进程 `/proc/1992450/environ`、活 serving pack 的 `manifest.json` 并校验成员哈希、只读
   `PRAGMA quick_check` + 行数统计三个 SQLite 库、回算活索引 marker 的 sha256、探 `df` / `crontab` / PG 端口。
   原始产物：`.agents/runs/admin-config-center-w1/dry-run-inventory.json`（探针脚本同目录 `dry-run-probe.py` 可重放）。
3. **受管配置文件**：`config/managed/settings.json`（白名单 Pydantic schema、缺文件/缺字段回落默认值、临时文件 +
   `os.replace` 原子写、`audit.jsonl` 追加审计含 operator/before/after/changed）；仓库内提交 schema 模板
   `config/managed/settings.example.json`，运行时文件被 gitignore。**敏感项一律不进这个文件**。
4. **API（挂 V2 壳管理区）**：`GET/PATCH /api/canonical-v2/admin/config`、
   `GET /api/canonical-v2/admin/system-status`、`POST /api/canonical-v2/admin/providers/health-check`。
5. **修掉 status 500**：`GET /api/canonical-v2/admin/status` 由 500 改为 200（详见"发现"第 1 条）。
6. **页面** `backend/static/admin.html`（与 `/browse`、`/logs` 同体系静态页，无新前端栈）：状态面板 + 白名单配置
   表单（仅渲染 schema 允许字段）+ provider key 只读区（含"立即检查"）+ 共享导航条（并在 `/logs` 补上"管理配置"入口）。
7. **接一个真实消费者**：`apps/miroflow-agent/scripts/settings_status.py`（读同一份文件与同一套 env 优先规则，
   输出每字段 `env|file|default` 来源；`--json` / `--check-keys` / `--require`）。
8. **测试与证据**：3 个新测试文件共 34 个用例；scratch 端口 **18288** + scratch 配置目录的真实 HTTP 冒烟；
   18188 只做了只读探测（未重启）。

### 发现

1. **status 500 的真根因**（不是 deploy/README 记的"operations 运行环境未配置"）：pack 模式的 runtime 装配把
   **内存态临时 gap feedback** 当成了带 `list_for_admin` 的 operations 对象，调用即
   `AttributeError: '_EphemeralKnowledgeGapFeedback' object has no attribute 'list_for_admin'`
   （2026-09-13 journalctl 抓到完整栈：`canonical_v2_admin.py:631` ← `canonical_v2_consumers.py:109`）。
   修法取"降级"而非"给临时对象加能力"：状态端点对**能力缺失**返回 `gap_summary.state="unavailable"` + 原因；
   真正的存储异常仍然 500（新测试同时锁住这两种情况，且"有 list_for_admin 时仍返回完整页"）。
2. **各域"上次成功采集时间"在服务机上拿不到**：`pipeline_run` 只存在于构建期 Postgres（alembic V001），
   服务机连的库里没有该表，活进程也没有 `CANONICAL_V2_DATABASE_URL`。面板改为展示
   **pack 构建时间 + 各域记录数（来自 pack 清单）+ 各运维库最近时间**，采集历史显式标"不可用（构建期库不可达）"。
   即：验收线里"各域新鲜度并排可见"以产物口径达成，采集史以**如实降级**呈现，不编数字。
3. **原以为要建、实际不需要**：serving 侧 SQLite `settings` 表（计划 §3.3 原方案）——文件更可 inspect、免迁移、
   且不会与 env 争真相源；"keepwarm/会话缓存状态"字段没有可暴露的运行时状态；manifest 里没有独立"版本号"
   （只有 `release_id`/`pack_id`/`schema_version`）；serving-pack 路径不适合做可编辑项（进程 argv 钉死值）。
4. **原计划没写、实际必需**：活索引 marker 的**期望 sha256**；pack 清单**各域记录数**；
   access-log / corrections / manual-recall **行数与最近时间**；日志保留期 90 天（写在清理脚本里，此前页面不可见）；
   `CANONICAL_V2_DATABASE_URL` 未配置的**降级标记**。
5. **新隐患（本片不修，转 W6）**：Bocha / Serper 的 key 文件查找只沿"导入路径 + cwd"向上找，而
   `.bocha_api_key` / `.serper_api_key` 只在主仓根；**从 worktree 启动的采集脚本会读不到 key**（`llm_profiles.py`
   已能越过 worktree 根，这两个 provider 不能）。W6 接 cron 前必须处理，否则"未配置"会静默变成采集失败。
6. **两个"答案 LLM"读数不同**：教授/采集侧 `LLM_PROFILE`，serving 答案侧 `CHAT_LLM_PROFILE`（线上
   `deepseekv4flash`）。本片只做只读展示，不做端点编辑——serving 端点改动会牵动已冻结的重放证据。

### 怎么验证

- **新增测试 45 个**：`tests/test_managed_settings_store.py`（26，锁 schema 默认值/白名单与凭据拒绝/原子写无残留/
  审计 before-after-operator/append-only/env 优先与类型不匹配/非法值边界/重启后保留），
  `tests/test_canonical_v2_admin_config_api.py`（15，锁 GET→PATCH→GET 往返、4xx（未知字段/凭据字段/类型/窗口/空体）、
  system-status 各块独立降级、runtime manifest 优先、health-check 不回显 key 明文、`/admin` 与 `/logs` 导航），
  `tests/test_canonical_v2_admin_status_repair.py`（4，锁 500 缺陷的两种形态 + 真存储异常仍 500）。全绿。
- **scratch 冒烟（18288，真实 HTTP，非 18188）**：`/admin` 200；config 往返 PATCH→GET 落盘并留审计
  （operator=`smoke-operator`，changed 两个字段）；非法请求 422（未知字段 / 凭据字段 / 类型错误）且文件字节不变、
  审计不增；system-status 200 且读真数据：pack `candidate-v2-20260819-r1`（生成 2026-09-10）、
  marker 期望=实测 `8848197c…97c8`、各域 7089/24520/11504/3958、access-log 960 会话 1599 轮、
  corrections 3 纠错+2 手工新增、lookup 47,071 文档、milvus.db 1.0GB 且锁在、磁盘 `/` 36.7% 与 `/md1` 88.9%。
- **凭据不外泄**：health-check 响应体内只出现 4 位尾号（4 个 provider），无任何长 token；服务日志零凭据样式行；
  测试里用进程内生成的哨兵串断言"响应体不含明文"。
- **CLI 消费者**：对 scratch 配置目录读到 `[file]` 来源（712 / 45），对默认路径读到 `[deflt]`，`--check-keys` 只输出
  尾号与来源，`--require` 未设字段时退出码 1。
- **既有套件**：`apps/admin-console` 全量 pytest 改前/改后对照：
  **改前 96 failed / 979 passed / 29 skipped / 122 errors**，
  **改后 96 failed / 1024 passed / 29 skipped / 122 errors**（+45 正好是新增用例），
  失败集合逐行 `comm` 比对**零差异**（无新增红、无误删红）。证据目录
  `.agents/runs/admin-config-center-w1/{full-suite-before,full-suite-after,failures-*,verification}.md`。

### 已知既有红（非本片引入，已用 `git stash` 对照确认）

- `tests/test_main_milvus_env.py::test_main_sets_milvus_real_client_env_when_absent`——V2 壳不设该 env（属旧 SPA 时代）。
- `tests/test_canonical_v2_consumer_migration.py::test_s9j_static_chat_uses_typed_public_copy`——静态 chat 文案与断言漂移。
- `tests/test_canonical_v2_consumer_migration.py::test_s11b_candidate_app_exposes_only_release_bound_v2_consumers`——工厂签名断言。
- `tests/test_canonical_v2_review_http.py`（17 个 error）——评审台应用工厂的既有 setup 问题。
- 另有约 90 个失败/120 个 error 属"需要 Postgres 域库（DATABASE_URL_TEST）"的环境性失败。

### 影响哪些问题

- **计划 §1.1 的"已知缺陷：admin/status 直连 500"**：根因已定位并在本片修复（降级式），
  线上 18188 需下次重启才生效——本片**不重启**，所以线上数字今天不变（见汇报"未做项"）。
- **计划 §3.2(a) 系统状态面板**：落地。
- **计划 §3.2(b) 采集/调度配置**：以受管配置文件 + 白名单表单落地"开关/配额/窗口"；但**消费者要到 W6**（cron 接线）
  才真正读它——本片先接 CLI 消费者，避免制造无人读取的字段。
- **计划 §3.2(c) provider key 状态**：落地（只读 + 立即检查 + 尾号 4 位）。
- **计划 §3.2(d) 任务运行面**：**不在本片**（W2）。
- **计划 §3.3**：按 2026-09-13 用户定案改为受管配置文件（原"serving 侧 SQLite settings 表"不建）。
- **W6**：多了一条硬前置——Bocha/Serper 的 key 文件查找范围要覆盖 worktree 场景。
