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

---

# 第 5 轮（2026-09-19 凌晨）：采集源就地修改 URL

## 1. 做了什么

需求：学校站点会改版，seed 的 URL 不可能长期不变。此前只能「删除 → 重新新增」来换 URL，那会丢掉 id 和它的运行历史。

- 每行加 **「修改」**：点后该行就地变成三个输入框（学校 / 院系 / 名册 URL）+ **保存 / 取消**
- 进入编辑时自动聚焦并全选 URL 输入框；**回车 = 保存**、**Esc = 取消**
- URL 没写协议时自动补 `https://`（免得后端按 HttpUrl 校验回一个难懂的 422）
- URL 与别的采集源重复时，后端 409 → 页面提示「该名册 URL 已存在。」且**保持编辑态**，可直接改
- 保存成功提示「已更新采集源 N，下次触发生效」——改动只影响之后的触发，不追溯已跑过的记录

## 2. 怎么验证（真浏览器 + 库内核对）

scratch 实例（18297，独立认证、指向 `miroflow_collection_v1`，38 条真数据）：

| 路径 | 结果 |
|---|---|
| 点「修改」 | 行内出现输入框，值预填，URL 框已聚焦全选，按钮变 保存/取消，提示「回车保存 · Esc 取消」 |
| 改 URL → 保存 | 横幅「已更新采集源 30，下次触发生效。」；**库内值已变**（`seed_url` + `updated_at` 同步） |
| 改成另一条已存在的 URL | 横幅「该名册 URL 已存在。」，**行仍是编辑态**（可继续改） |
| 还原为原 URL → 保存 | 库内复原为 `https://am.sysu.edu.cn/szdw/index.htm`，总行数仍 38 |
| 页面测试 | **47 passed, 1 skipped**（跳过的是需要测试库的 CRUD 用例） |

## 3. 未做

- 没有做「历史 URL 归档」：改动即覆盖，旧 URL 不保留（如果以后要审计 URL 变更，可以在 `pipeline_issue` 或审计表里记一笔）
- 没有做批量修改（38 条量级下逐行改够用）

---

# 第 6 轮（2026-09-19）：/jobs 页面向操作者重写

## 1. 做了什么

反馈：客户的非技术管理者看不懂任务运维页——15 个任务平铺，列是 任务 / 节奏（下次运行）/ 闸门 / 最近运行 / 操作，
而「任务」列的主标题就是脚本路径（`企业新闻采集（scripts/run_company_news_ingest.py）`），既没有分组，
也没说什么时候该按哪个按钮。

- **后端任务表补两列**（`jobs.py` 的 `JobTask`）：`group`（日常采集 / 数据导入 / 教授采集源 / 构建与运维）
  与 `operator_hint`（一句人话：这活干什么、什么时候用）。15 个任务全部写上，`as_dict()` 一并交给页面；
  `description`（脚本路径）保持原样，只是不再当标题用
- **页面改成分四组**，每组一句用途：日常采集（按周期抓回四个域的新数据，系统自动跑，失败可重跑）、
  数据导入（上传页自动排队，失败可重跑）、教授采集源（去 Seed 管理页逐条操作）、构建与运维（需要构建期数据库）
- **每个任务一行**：中文名 + 一句话用途 + 状态徽章（成功/失败/跳过/运行中 + 本地时间；从未运行是中性灰；
  熔断追加「已熔断」；失败追加「连续失败 N 次」）+ 小标签（需构建库 / 消耗网络检索配额（上限 N）/
  消耗大模型配额（上限 N）/ 仅在采集时间窗内运行 / 受采集开关约束）+ 操作
- **操作**：`domain` 下拉中文化（企业/论文/专利/教授）＋「立即运行」；本机不可用时按钮禁用并在旁写明原因
  （`postgres_unavailable` → 需要构建期数据库）；需要页面外 token 的任务（2 条 seed、3 条上传导入）
  不给触发按钮，改为去签发 token 的那个页面
- **技术细节收进每个任务的折叠区**：任务 ID / 命令 / 超时 / cron 默认不显示
- **运行历史**：中文状态、本地时间、耗时改成秒/分、失败行就地显示原因（exit_code + stderr 摘要，截断并转义）；
  筛选 / 刷新 / 熔断复位 / 运行详情面板全部保留
- **顶部说明卡**：这个页面做什么 + 三条规则（同一任务不会重复运行；连续失败 2 次熔断，复位后再触发；
  手动触发与周期运行共用同一道闸门）

## 2. 怎么验证（测试 + 真实 payload 渲染；本片没开浏览器）

约束要求不改 18188、不重启服务，所以页面层的证据是「用真实 payload 跑页面自己的 JS」，
而不是第 4/5 轮那种 scratch 实例 + CDP 量化。

| 路径 | 结果 |
|---|---|
| 新不变量测试（4 个分组取值、非空人话、不得含 `scripts/` 路径、每组 id 集合精确、payload 带两列） | 改前 **RED**（`AttributeError: 'group'` / `KeyError: 'group'`）→ 改后 **47 passed** |
| 指定的 admin-console 套件（jobs-api / nav-gating / console-shell / admin-gate） | **47 passed** |
| jobs + uploads + seeds 套件 | **140 passed, 1 skipped** |
| 页面渲染校验（`jobs-page-harness/`：真实 `task_views()` payload → 页面自己的脚本 → DOM 桩） | **全部断言通过**：四组顺序与用途、15 条人话、状态徽章、五类标签、3 个禁用按钮+原因、2 个 /seeds 与 3 个 /upload 链接、失败行转义、触发 POST 体不变 |
| 全量对照 | 只有 `test_public_chat_uses_guoxian_brand_identity` 失败，**在 HEAD 上同样失败**（把本片全部改动 stash 后复现），与本片无关 |

## 3. 未做 / 偏差

- 三条上传导入任务的链接指向 **`/upload`** 而不是 `/seeds`：它们同样带 `token_params=["upload_id"]`，
  一律指向 Seed 管理页会把「导入专利表格」的人送到「教授花名册」页
- 运行历史的失败行目前只有 `exit_code`：列表接口按 `as_dict(include_samples=False)` 序列化，不带
  `stderr_excerpt`；页面已按「有就显示」写好（照抄 /seeds 的 `failureReason`），要真正显示需要后端一行修改，
  而本片约束不允许改 backend Python。完整 stderr 仍在「运行详情」里
- `mode` / `limit` 下拉当前看不到：只有两条 seed 任务声明它们，而它们按规则只给链接、不给触发按钮
- 没有浏览器实测（第 4/5 轮那种 scratch 实例 + CDP 量化）：留给有会话的页面级验收

---

# 第 7 轮（2026-09-19 凌晨）：/jobs 上线的收口（第 6 轮实现 + 本轮补齐）

## 1. 做了什么

- **第 6 轮**（子代理）：任务目录新增 `group` + `operator_hint` 两列（15 个任务全部写了人话用途），并加了不变量测试——**以后新增任务没写人话就测试失败**；`/jobs` 页面按用途分四组重写（日常采集 / 数据导入 / 教授采集源 / 构建与运维），每任务：中文名 + 一句话用途 + 状态徽章 + 通俗标签 + 操作；任务 ID / 命令 / 超时 / cron 收进折叠的「技术细节」
- **本轮补齐两处**（子代理上报的缺口）：
  1. 运行历史的失败行原本只有 `exit_code`——因为列表接口按 `include_samples=False` 序列化。改成 `include_samples=True`，失败原因（stderr 摘要）现在就地可见
  2. token 任务的路由：`seed_id` → `/seeds`，`upload_id` → `/upload`（子代理自己发现并纠正了我简报里的错）
- **线上**：活线 ff 到 `6a37bfaa` → **01:17:44 重启**（新 payload 字段由服务进程提供，必须重启）

## 2. 怎么验证

| 检查 | 结果 |
|---|---|
| 分组渲染 | **日常采集 / 数据导入 / 教授采集源 / 构建与运维** 四组，15 行 |
| 人话用途 | 页面文本命中 **15/15** 条（逐条比对，无遗漏） |
| 任务 ID 是否暴露 | 主视图**不含**任何 task_id（已收进折叠区） |
| 标签 | 「消耗网络检索配额（上限 200）」「仅在采集时间窗内运行」「受采集开关约束」「从未运行」等 |
| 链接路由 | seed 任务 → `/seeds`，上传任务 → `/upload` |
| 失败行带原因 | 列表端点已 `include_samples=True`（源码断言 + 47 passed） |
| 测试 | 定向 **119 passed**；不变量测试 RED→GREEN（回退后 `AttributeError: group`） |
| 线上页面 | 刷新即见（静态页）；payload 字段在重启后生效 |

## 3. 未做

- 「运行详情」面板仍显示原始 argv / JSON / run id（有意：那是排查用的技术面）
- 触发成功横幅里仍带 run id（操作者需要引用它；任务名已换中文）
