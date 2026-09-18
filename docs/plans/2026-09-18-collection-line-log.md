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
