# 采集线接通：配置单一真相源 + 库预置 + 花名册（2026-09-18）

> 关联 OpenSpec change：`connect-collection-line`（英文，代理侧门禁）。
> 状态：**已上线 18188**（A/B/D/E 实现 + C1/C2 接线完成；C3 页面级验收待有会话；F2 真跑进行中）。
> 触发问题：`/seeds` 在线上返回 503「seed 管理不可用（无构建期 PostgreSQL）」。

## 1. 症状与证据（都是现场实测）

| 事实 | 证据 |
|---|---|
| `/seeds` 页面 200，数据接口 503 | 服务日志 22:22:53：`GET /seeds → 200`、`GET /api/canonical-v2/admin/seeds → 503` |
| PG 探测读环境变量，线上服务**没有**任何 DSN 环境变量（库是用 argv `--database-url` 传的） | `jobs.py:1142` 的 `ENV_ORDER`；`/proc/<pid>/environ` 变量名清单 |
| 全仓**没有一处**把 argv 的 DSN 投射进环境 | 子代理静态 import 图 + 全仓 grep |
| 16 个 DSN 解析点，变量名/失败方式各不相同；探针认 `CANONICAL_V2_DATABASE_URL`，seeds 连接不认 → "探针绿、一读就 500" | `canonical_v2_seeds.py:109` vs `jobs.py:1142` |
| 本机 13 个库**没有一个**有 `professor_seed`/`pipeline_run`；43 版 alembic 链从未应用过 | 现场查询（information_schema） |
| 闸门 spawn 子进程时**不注入任何 DSN** | `jobs.py:1587-1592`（只复制父环境 + 4 个 `MIROTHINKER_*`） |
| 花名册（39 条历史种子）没有导入器；3 条 URL 无适配器可服务 | `scripts/e2e_seeds/*.md`；V022 注释自述 backfill 被推迟 |
| 失败不可诊断：`/seeds` 只有"失败"药丸，exit code/stderr 在 jobs 台账里 | `seeds.html:333-340`；`storage/seeds.py:96-190` |

## 2. 根因（一句话）

**没有一个"控制台用哪个库"的单一真相源**：库名在 16 处各写各的，而唯一持有 DSN 的地方（argv）从不投影到环境；同时这个库在本机从未被创建过。所以这不是"配一个环境变量就好"的问题，是契约缺失 + 从未预置。

## 3. 设计（冻结）

1. **一个名字、一个解析器**：`DATABASE_URL` = 控制台/采集库（沿用 `backend/deps.py` 既有契约）。新增 `resolve_console_dsn()` 作为唯一读取点，启动时解析一次、挂在 `app.state`。`CANONICAL_V2_DATABASE_URL` 保持它唯一含义——**服务库**（V2 operations 面），并**不再**被探针接受（那正是"绿探针 + 500"的来源）。
2. **进程边界各管一段**：控制台进程用 `app.state` 的值；闸门在 `JobRuntime._execute` 这**一个**接缝把 `DATABASE_URL` 注入每个 spawn 的子进程（和现有 4 个 `MIROTHINKER_*` 同一处）；服务线继续用 argv，不动。
3. **预置写进 runbook，不写进代码**：建库（带 destructive-target marker）+ `alembic upgrade head`（三个显式 `ALEMBIC_*`）+ drop-in 注入 + 重启。
4. **花名册导入复用现成解析器** `parse_roster_seed_markdown()`，写入口走控制台自己的 `create_seed`，按 `seed_url` 幂等去重，默认干跑、`--apply` 才写。
5. **适配器补齐**：`pkusz.edu.cn` 加注册表 matcher（抽取逻辑早就有）；两条 SZTU 坏 URL 改数据不改代码（放宽 matcher 会误吞非名册页）。
6. **入口诚实 + 失败可见**：共享的 `nav_auth.js` 按"控制台库不可用"隐藏 `[data-requires-postgres]` 入口（补 W3 只做了一半的 requirement）；`GET /seeds/{id}/runs` 带上 `status/exit_code/stderr_excerpt`，页面上就地展开失败原因。

## 4. 分期与验收

| 段 | 内容 | 验收 |
|---|---|---|
| A | 控制台 DSN 单一真相源（deps/main/seeds/uploads/status + 探针） | 只设 `CANONICAL_V2_DATABASE_URL` 时判"不可用"且 503（**不是 500**）；单元测试锁两个可接受名字 |
| B | 闸门注入 DSN | runner 测试断言子进程 env 里有它、未配置时没有；"env 不落库"旧测试保持绿 |
| C | 预置与接线（建库/迁移/drop-in/重启） | `/seeds` 200 空列表；真实建→改→删一条；`/jobs` 可见运行；`/upload` 预检绿 |
| D | 花名册导入 + 适配器 | 39 条幂等导入（二次跑 0 新建）；39/39 命中适配器 |
| E | 入口隐藏 + 失败可见 | 无库时导航隐藏 `/seeds`、`/upload`；失败行显示 exit code/stderr 摘要 |
| F | 验证收口 | 定向 + 全量 before/after 零新增失败；真跑一次 preview + 一次 sample（报配额消耗） |

## 5. 回滚

- 代码：`git revert` 本片提交；受管设置/密钥/服务包不动。
- 接线：删 drop-in + `daemon-reload` + 重启 → 回到 503 降级态。
- 库：`DROP DATABASE miroflow_collection_v1`（本片之前它不存在，回滚即恢复原状）。

## 6. 边界（本片不做）

- 不改检索/回答/服务包/`/chat`；不重挂 legacy PG 路由（`pipeline`/`pipeline_issues` 继续不挂）。
- 不把采集到的数据送进 `/chat`（那是 C6 的重建+切包）。
- 不开 LLM 主页富化（保持默认关；跑通后再单独决定）。
