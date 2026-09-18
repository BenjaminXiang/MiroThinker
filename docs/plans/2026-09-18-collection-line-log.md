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
