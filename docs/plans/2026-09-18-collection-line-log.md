# 采集线接通执行日志（2026-09-18 · 第 1 轮：诊断 + 库预置）

> 计划：[2026-09-18-collection-line-wiring.md](./2026-09-18-collection-line-wiring.md)
> OpenSpec change：`connect-collection-line`（代理侧门禁）
> 状态：**设计中**（A–F 分段；本轮完成诊断与 C1 的库预置）

## 1. 做了什么

**诊断（只读）**

- 服务日志：`/seeds` 页面 200、`GET /api/canonical-v2/admin/seeds` 503（22:22:53）
- 运行期事实：服务进程环境里**没有**任何 DSN 变量（库是 argv `--database-url` 传的）；全仓没有把 argv DSN 投射进环境的地方
- 静态 import 图 + 全仓 grep：16 个 DSN 解析点（运行期可达 5 处），变量名与失败方式各不相同
- 现场查库：本机 13 个库**没有一个**有 `professor_seed` / `pipeline_run`；43 版 alembic 链从未应用过

**库预置（C1 的前半）**

- 干跑：`miroflow_collection_dryrun` 跑完整迁移链 → **V001→V042，0.8 秒，42 张表**
- 正式：建 `miroflow_collection_v1`（dom marker `miroflow:destructive-target:v1:isolated-candidate:miroflow_collection_v1`）→ 迁移到 V042 → 5 张关键表齐全
- 离线全链预演（不重启、不碰线上）：控制台存储 `create/list/get/update/delete` 全通；爬虫 `_load_seed` 能读控制台建的行；适配器解析 `sustech → sustech-roster`、`pkusz → None`（符合预期）；预演后表内 0 行

## 2. 发现了什么

1. **根因是契约缺失，不是配置漏项**：库名散在 16 处，而唯一持有 DSN 的 argv 从不进环境。
2. **最危险的组合**：探针认 `CANONICAL_V2_DATABASE_URL`、seeds 连接不认 → 那个形态下"探针绿、一读就 500"。
3. **闸门不给 spawn 的子进程注入 DSN**（`jobs.py:1587-1592` 只复制父环境 + 4 个 `MIROTHINKER_*`），爬虫子进程能否连库全靠环境继承。
4. **入口隐藏只做了一半**：`jobs.html` 会禁用按钮，但 `main.html` 的 `/seeds`、`/upload` 链接是静态硬编码，永远显示。
5. **花名册已有解析器** `parse_roster_seed_markdown()`，不该再写一个；39 条里 3 条无适配器，其中 2 条是 URL 形态问题（改数据即可）、1 条缺注册表 matcher（pkusz，抽取逻辑早已存在）。
6. **失败不可诊断**：`pipeline_issue` 在 V2 页面无任何入口；`/seeds` 只显示状态药丸，运行详情（exit code/stderr）在 jobs 台账里，`GET /seeds/{id}/runs` 已挂载但没带这些字段。

## 3. 怎么验证

- 迁移：干跑与正式两次，命令 + 输出（head=V042、42/42 表、marker 与库名一致）
- 离线预演：真实签名调用（控制台 store × 爬虫读 × 适配器解析），跑完表内 0 行
- 全量证据（A/B/D/E 段）在实现完成后统一落 `.agents/runs/connect-collection-line/verification.md`

## 4. 影响哪些问题

- 直接解决 `/seeds` 不可用（C 段接线后）
- 为 C6 周期更新（采集 → 构建 → 切包）提供**本机第一个真实存在的采集库**（本片之前没有）
- 收掉 W3 遗留的两条：入口隐藏、失败可见

---

# 第 2 轮（2026-09-18 深夜）：实现 A/B/D/E + 接线 C1/C2

## 1. 做了什么

**代码（三个子代理并行，文件域互不重叠）**

| 段 | 内容 | 提交 |
|---|---|---|
| A/B | `deps.resolve_console_dsn()` 唯一解析点；`main.py` 启动解析一次挂 `app.state`；seeds/uploads/status 改读该值；缺失时稳定 **503 `console_database_not_configured`**（不再 500）；`PostgresProbe` 只认 `DATABASE_URL`/`DATABASE_URL_TEST` 并暴露 `resolved_dsn()`；`JobRuntime._execute` 在**同一处**给每个 spawn 的子进程注入 `DATABASE_URL`；`/seeds/{id}/runs` 带 `status/exit_code/stderr_excerpt` | `a014a987` |
| D | `pkusz-szdw-hub` 适配器（复用既有抽取路径）；`import_professor_seeds.py` 幂等导入器（干跑默认，复用 `parse_roster_seed_markdown()`）；梁永生条目改为学院名册 URL | `5947a518` |
| E | `nav_auth.js` 按可用性隐藏 `[data-requires-postgres]`（fail-open）；`main.html` 标记 `/seeds` `/upload`；`upload.html` 降级态文案与按钮一致；`seeds.html` 就地显示失败原因 + 新 503 文案 | `a9949fc8` |

**库与接线**

- 干跑库 `miroflow_collection_dryrun`：43 版迁移 **0.8 秒**跑完 → V042、42 表
- 正式库 `miroflow_collection_v1`（marker `miroflow:destructive-target:v1:isolated-candidate:miroflow_collection_v1`）→ V042 → 5 张关键表齐全
- 离线全链预演（不重启、不碰线上）：控制台 store 的 CRUD × 爬虫 `_load_seed` × 适配器解析，跑完表清空
- drop-in `~/.config/systemd/user/canonical-v2-backend.service.d/database-url.conf` → `daemon-reload` → 活线 ff 到 `73d1fd58` → **23:20:56 重启**
- **花名册导入**：`--apply` 写入 **38 行**（50 条解析 → 去重 39 → 1 条跳过），二次跑 0 新建；全部 `never_run`

## 2. 发现了什么

1. **零新增失败**：全量套件失败集 before 130 行 ↔ after 130 行，`comm` 双向为空。
2. **首次 preview 被我自己的 280s timeout 杀掉**（缓冲输出丢失），但库里留下了一行 **status=`running` 的孤儿 run**——`pipeline_run.py` 没有心跳/超时兜底，页面会永远显示"进行中"。**新缺口，记入候选**（闸门侧的 jobs 台账知道真相，只有 registry 视图会卡住）。
3. 启动日志 `console_database=...` 是 INFO 级，当前进程日志配置不落地（代码对，可见性需要日志配置）。
4. 上传提交的预检在"未配置"时仍可能 500（不经闸门的那条路径），与改动前一致。
5. `backend/deps.py` 两条 ruff F401 是 HEAD 上就有的，未动。

## 3. 怎么验证（分层）

- **① 本片新增测试**：admin-console 侧 13（DSN/注入/runs 载荷）+ 10（导入器）+ 9（页面门控）；agent 侧 5（pkusz 适配器）
- **② 合并后定向**：`132 passed, 1 skipped`（admin-console 组合）、`251 passed`（professor adapter/roster 子集）；**全量 before/after 失败集逐行一致**
- **③ 线上（无会话可验的部分）**：boot 660s → `/api/health` 200；服务进程 env 含 `DATABASE_URL`（1 条）；真实调用 `_resolve_console_database()` → `app.state.console_dsn` 为该库；**`PostgresProbe.describe()` → `{'available': True, 'source': 'DATABASE_URL'}`**；公开面 `/chat` 200、`/admin` `/seeds` `/upload` 302；静态页标记（failureReason / console_database_not_configured / data-requires-postgres）均已上线
- **待办**：C3 的页面级验收需要已登录会话（我会从访问日志读状态码确认）；F2 的 preview/sample 真跑

## 4. 影响哪些问题

- `/seeds` 的 503 根因（探针读不到 DSN）已消除；页面能否点通只差一次会话级验收
- 采集链现在有**真实存在的落点**（`miroflow_collection_v1`，38 条花名册就位），C6 的"采集 → 构建 → 切包"有了上游
- 收掉 W3 遗留：入口隐藏 + 失败可见
- 新登记缺口：被 kill 的采集留下永久 `running` 行（需要超时/心跳兜底）

---

# 第 3 轮（同日 23:35–23:50）：F2 真跑 + 顺带修掉"运行时长恒为 0"

## 1. 做了什么

- **真跑**（走闸门 spawn 的同一入口 `run_admin_seed_refresh.py`，`DATABASE_URL` 按新注入方式给）：
  - preview（seed 11 = 南科大）：**7.5 分钟**，`succeeded`，`items_processed: 1`
  - sample `limit=5`：`succeeded`，`items_processed: 5` → 落库 **professor 5 / professor_affiliation 5 / source_page 9**
  - registry 视图（`/seeds` 渲染的那份）：`id=11 → success / 15:33:48Z`
- **修掉一个既有缺陷**：`open/close_pipeline_run` 用 `now()`（Postgres 里是**事务开始时间**），而抓取全程在一个事务里 → `finished_at` 恒等于 `started_at`（7.5 分钟的抓取记成 3 毫秒）。改成 `clock_timestamp()`，并在真库上取证：修复前 2 秒口径差 = `0:00:00`，修复后 = `0:00:02.002`
- 回归测试 `test_close_records_elapsed_time_not_the_transaction_start`：**RED 1 failed → GREEN 4 passed**（临时库，跑完已删）

## 2. 发现了什么

1. **首次 preview 被我自己的 280s timeout 杀掉**，库里留下一行永久 `running` 的孤儿 run（无心跳/超时兜底）——已手工释放并在 `error_summary` 里写明原因；登记为候选切片。
2. 采集的**真实耗时在分钟级**（南科大 7.5 分钟；preview 只做发现阶段），页面/闸门的 5400s 上限是必要的。
3. `pipeline_run.seed_id` 列是 TEXT 且实际为空——seed 关联走的是 `run_scope->>'seed_id'`（store 的 SQL 就是这么写的）；直接查列会查不到。

## 3. 怎么验证

命令与输出都在 `.agents/runs/connect-collection-line/verification.md` 的 "F2" 一节（含修复前后 delta 对照、RED/GREEN 测试输出、落库计数）。

## 4. 影响哪些问题

- F2 完成：**采集链在真实库上端到端跑通并写出数据**（这是"采集流程能否正常运行"的直接答案）
- `/seeds` 的"最近运行/运行时长"从现在起是真实值
- 待有会话的只剩页面级点击验收（C3 的 UI 半边）

---

# 第 4 轮（2026-09-19 凌晨）：/seeds 页面中文化与排版

## 1. 做了什么

- **操作列全部中文**：`preview` → **预览抓取**、`sample(20)` → **抽样抓取**、`运行记录`、`删除`（各带 title 说明）；抽样抓取会先确认，因为它会真实访问学校网站
- **排版重做**：固定列宽 + 表格 `min-width`（窄屏改为表格内滚而不是压扁 URL）、`.card { min-width: 0 }`（grid 子项默认 `min-width:auto` 会把整页撑宽）、行高统一 66px、URL 单行省略 + title 完整显示
- **编号从独立列改为学校旁的 `#id` 标记**：列表按学校排序，独立编号列读起来像乱序序列；挪进单元格后腾出的宽度给了 URL 列
- **状态语义**：`未运行` 改中性色（原来 36 行都是琥珀色警告），且不再显示空时间；时间戳从原始 ISO 改为本地 `YYYY-MM-DD HH:mm`
- **点击反馈**：点「运行记录」会把下方运行面板滚入视野（它在 3000px 处，原来点了屏幕没反应）；顶部提示条也会滚入视野
- **对比度**：主按钮白字对比度 4.16:1（低于 AA 4.5）→ 深色化到 `#0f6f68`；副标题去掉开发者黑话 "CRUD"

## 2. 怎么验证（真浏览器 + 量化，不是肉眼）

起了 scratch 实例（端口 18297，独立认证库 + 指向 `miroflow_collection_v1`，38 条真数据），用 agent-browser 量 DOM：

| 指标 | 改前 | 改后 |
|---|---|---|
| 1440 宽 URL 截断数 | 5–7 / 38 | **3 / 38** |
| 1024 宽 URL 列宽 | 153px（38/38 全截断） | **308px（10/38）** |
| 1024 宽页面横向滚动 | 有（表格撑宽整页） | **无**（表格内滚 927→1092） |
| 行高 | 不一致（无院系的行更矮） | **38 行全部 66px** |
| 操作按钮换行 | 有 | **38 行全部单行** |
| 点「运行记录」 | 无任何可见反应（面板在 3000px 处） | **滚入视野**（scrollY 0→1977，面板可见） |
| 页面测试 | — | **52 passed**（含页面壳/门控/上传页） |

## 3. 未做（有意）

- 导航里的 `Seed 管理` 保持英文（6 个页面统一，且被测试锁定）；「Seed」是 /jobs 也用的既有术语
- 后端 `list_seeds` 仍按 `(school, department, id)` 排序——改排序要重启服务才生效，本轮用前端呈现解决；若想改成 id 序，放进下次重启窗口
- 未运行的 36 行仍是同色中性药丸（信息本身如此，不是样式问题）
