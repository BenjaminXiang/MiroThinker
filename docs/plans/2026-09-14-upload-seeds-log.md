# W3 数据正门承接：XLSX 上传导入 + 教授 seed 管理（2026-09-14 · 第 1 轮）

**本片要解决的问题**：管理区（V2 壳）没有数据入口——上传 XLSX 与教授 seed 管理的能力都还在旧代码里，
但两条链的 API 都没挂在 V2 上（`/api/{path:path}` 兜底 404），页面上也没有入口。收尾计划 §4-C1/C2 要求
把这两条链「以 V2 路由受限重挂」，§6 W3 给的验收线是：企业 XLSX 上传→批次跑完→域库有增量；seed CRUD
+ 触发抓取成功；同 hash 重复上传被去重。

对应变更：`add-admin-upload-seeds`（OpenSpec，英文）；分支 `feat/admin-upload-seeds`（基线 `3d9dd7c0`，
即 W2 尖）。

---

## 1. 做了什么

**先回答计划里点名的技术验证点（§7「旧链环境适配」）**：`upload`→`pipeline` 的 subprocess 链
（`uv run scripts/...`）在 V2 壳进程里能不能跑。做法是照 V2 壳的方式起一个探针进程
（`cd apps/admin-console && uv run python …`，scratch 端口 18292），在它内部调用 W2 自己的
`_spawn_subprocess` 跑 6 组用例，原始输出留档 `.agents/runs/add-admin-upload-seeds/probe/probe-result.json`。

| 用例 | 内容 | 结果 |
|---|---|---|
| A | `uv run python -c`（子进程自报 exe/cwd/env） | rc=0，0.06 s，cwd 与注入的哨兵环境变量都对 |
| B | `sys.executable -c`（旧链实际用法） | rc=0，0.03 s |
| C | `uv run python scripts/run_company_upload_enrichment_batch.py --help` | rc=0，0.75 s（模块级 import 全部成功） |
| D | 同一脚本走 `sys.executable` | rc=0，0.72 s |
| E | 超时 1 s（子进程 sleep 30） | `TimeoutExpired`，闸门记为 failed/exit 124 |
| F | cwd 不存在 | 启动即 `FileNotFoundError` → 记为失败运行 |

**结论：跑得通，不需要降级**（§7 的降级方案「保留 CLI 导入 + 简化状态页」未启用）。判据：env 透传、
cwd 正确、`uv` 在 PATH（`~/.local/bin`）、嵌套 `uv run` 只多一个 `UV_RUN_RECURSION_DEPTH`、超时可控；
首次 `uv run` 会做一次本地包构建（约 2.2 s），之后 0.03–0.06 s。

**实现（4 块）**：

1. **上传正门**（新模块 `canonical_v2/uploads.py`）：域白名单 `company/patent/professor`、只收 `.xlsx`、
   大小上限、sha256 内容身份、**跨进程 flock 咨询锁**（直接复用 W2 的 `JobLock`，没有另造）、
   重复上传 409 并回报首次上传编号、干跑（只解析不写库、不排富化、不吃配额）、暂存目录沿用旧 upload 根、
   **serving 侧上传台账**（`CANONICAL_V2_UPLOADS_DB`，SQLite）记录上传生命周期与闸门 run id。
2. **闸门复用**（改 W2 的 `jobs.py` 两处）：① 给 `JobTask` 加**服务端解析的 opaque token 参数**——
   调用方只能回传本服务自己签发的 id，形状校验（`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`）+ 服务端解析成
   受控路径，任何调用方文本都进不了命令行；② 新增 5 个任务（`upload-{company,patent,professor}-import`、
   `admin-seed-refresh[-sample]`），上传/seed 触发全部走 `JobRuntime.trigger()`，不绕过开关/配额/熔断/
   防重入/PG 探测。
3. **教授 seed 面**：CRUD 直接复用旧 `backend/storage/seeds.py`（唯一 URL、last_run 字段不给人改），
   触发分 `preview/full`（不带上限）与 `sample`（必须带上限，白名单 5/20/50/100）两个声明任务，
   run 轮询取自闸门运行历史；新增两个薄 CLI（`run_admin_upload_import.py`、`run_admin_seed_refresh.py`），
   只做参数接线与回写台账，真正的导入/抓取逻辑一行没动。
4. **两个页面** `upload.html` / `seeds.html` + 六页共享导航（`/browse` 原本没有顶部导航，这次补上同一组链接）。

**明确没做（留给别的片）**：W4（issues/工作台/SPA 退役）、W6（周期调度）、W7（发布流水线）。

## 2. 发现了什么

1. **孤儿进程缺陷（W2 闸门既有缺陷，本片修掉）**：`subprocess.run(timeout=…)` 只杀直接子进程，而
   `uv run` 把真正干活的进程作为**孙进程**启动。复现（探针 §2.1）：超时 3 s 后 `uv run python -c sleep(90)`
   的 python 进程仍然活着。后果很实际——闸门记 failed 并**释放 flock**，而孤儿还在跑、还能花配额、还能写库，
   锁一放还允许第二次启动。修复：`start_new_session=True` + 超时 `os.killpg(SIGKILL)`；回归测试
   `test_a_timed_out_spawn_leaves_no_grandchild_behind`。
   **归属**：缺陷在 W2 的 spawn helper 里（跨片），W3 因为要声明走 `uv run` 的任务而必须修；W2 原有测试全部保持通过。
2. **富化批次表名写错（本片自己的 bug，冒烟抓到）**：我最初按 `company_enrichment_item` 读明细，
   实际表是 `company_enrichment_company_state`；detail 里也用错了 batch id（顶层是 import batch，
   富化批次在 `enrichment.batch_id`）。已在 `5f9ee2c9` 修掉，冒烟复查通过。
3. **上传链需要 PG，两条路径要分开**：提交导入（`pipeline_run`/`import_batch`/`company_snapshot`/
   `company_enrichment_batch`）必须 PG；**干跑只做本地解析**，所以在没有 PG 的现场薄部署上，
   干跑与台账仍然可用——这正好落在 §2 原则 4 的降级口径里。
4. **企业身份靠统一社会信用代码**：第一版测试工作簿没有信用代码列，3 行被归并成 1 个企业（同一 null key）。
   自造测试数据补上 3 个合成信用代码后，域库正确新增 3 条。这也解释了「域库有增量」该看哪个口径。
5. **seed 触发模式与闸门参数的对应关系**：`sample` 必须有上限、`full`/`preview` 不接受上限，
   所以拆成两个声明任务（而不是在闸门里加可选参数）——保持「每个任务的 argv 是固定元组」这条不变量。

## 3. 怎么验证

**新增测试（本片写的，全部通过）**：

| 文件 | 锁什么 |
|---|---|
| `tests/test_canonical_v2_uploads_registry.py` | W3 声明任务的闭环：脚本存在、argv 固定、closed set 越界/未声明参数/畸形 token/未知 token 全部拒绝；token 形状矩阵（空格、`;`、`/`、`..`、超长） |
| `tests/test_canonical_v2_uploads_store.py` | 台账：准入/列表按时间倒序/域过滤/重复查询；失败不毒化 hash；摘要截断与凭据打码；不存文件内容 |
| `tests/test_canonical_v2_uploads_runtime.py` | 准入：域白名单、`.xlsx`/空/超限、sha256 身份、**持锁排他**、重复 409 带首次编号、失败可重试、干跑不写、闸门跳过/拒绝落到台账状态、配额注入到子进程环境 |
| `tests/test_canonical_v2_uploads_api.py` | HTTP：202 准入、409 重复、422 域、400 形状、413 超限、503（无 PG 提交）、列表/详情、六个页面与共享导航、页面降级标记 |
| `tests/test_canonical_v2_seeds_api.py` | seed 面：无 PG 全端点 503、`sample` 缺上限 422、模式/上限越界 422、触发走声明任务（含 argv 与 run 记录）、CRUD 往返（有测试库时） |
| `tests/test_canonical_v2_jobs_runner.py`（扩充） | **R5 回归**：超时后进程组无残留 |

另外补了两个 W2 测试的「事实更新」（不是放宽锁）：任务表从 §5.3 白名单扩成了「§5.3 + W3 五个动作」，
原测试写的是精确相等集合；现在写成 `PLAN_WHITELIST | W3_ADDITIONS`（多一个少一个都会红），并把 token 参数
纳入「固定元组」用例（用桩 resolver 喂 token）。行为锁（未知任务/未声明参数/越界值被拒）一条没动。

**全量套件 before/after**：after 侧 `cd apps/admin-console && uv run pytest -q` 一次；
before 侧不重跑——W3 的基线就是 W2 尖 `3d9dd7c0`，直接复用 W2 的
`full-suite-after.txt` / `failures-after.txt`（同为无 `DATABASE_URL_TEST` 环境）。差异用 `comm`，**新增失败 0**。
明细见 `.agents/runs/add-admin-upload-seeds/verification.md`。

**scratch-18292 真机闭环**（一次性 PG 容器 18293 + scratch 存储/配置，3 行企业工作簿 + 2 行专利工作簿）：

```
health=200；/upload /seeds /jobs /browse /logs /admin 全部 200
企业上传（提交）→ 202 → 闸门 run succeeded（exit 0, 1888ms）→ company 3 条、import_batch 1、enrichment batch 1
同内容再传 → 409 duplicate_upload，回报首次 upload_id
批次进度 → batch available=true, companies 3/3, items {queued:3}
专利干跑 → succeeded, rows_read=2, imported=0（不写库）
seed：create 201 / list 200 / update 200 / trigger(preview) 202 / runs 200 / delete 204 / 再查 404
sample 不带 limit → 422
无 PG 阶段：上传提交 503 upload_requires_postgres；seeds 列表/创建/触发 503 seeds_require_postgres；
            /upload /seeds 仍 200（降级块存在）；台账仍可读 200；health 仍 200
```

跑完停服务，`ss` 确认 18292 无监听；18188 全程未动（health 200，PID 不变）。

**配额消耗：0 次 web search、0 次 LLM、0 次外部网络抓取。** 手段：全部用自造工作簿、专利只跑干跑、
`COMPANY_UPLOAD_ENRICHMENT_DISABLE_AUTORUN=1` 关掉富化自动执行（批次只创建不跑）、seed 只跑 `preview`
且指向合成的 `.invalid` 学校（无适配器，实际不发外部请求）。

## 4. 影响哪些问题

- **收尾计划 §6 W3 验收线**：企业上传→批次跑完→域库有增量 ✅；seed CRUD + 触发 ✅（抓取本身因合成 seed
  无适配器而止于 `adapter_missing`，见缺口 G1）；同 hash 去重 ✅。
- **§4-C1/C2 承接**：两条链以 V2 路由受限重挂，旧模块（`backend/api/upload.py`、`backend/api/seeds.py`）
  **一行未改**，CLI 仍是回退路径——回滚就是摘路由。
- **§2 原则 4（无 PG 降级）**：上传提交与 seed 全端点 503 + 页面入口隐藏，台账与干跑仍可用，服务不炸。
- **§7 W3 风险（旧链环境适配）**：**关闭**，结论是「无需降级」，证据在 `current-state.md` §2。
- **W2 闸门**：被复用而不是被旁路；顺带修掉一个 W2 遗留的进程组缺陷（§2.1）。

## 5. 缺口与后续

1. **G1 seed 抓取本身未验证**：合成 seed 无适配器（`adapter_missing`）。要真验一次，需要用真实学校名册
   跑 `preview`——会对外发起真实抓取，按本片「只准 preview」的口径应由你拍板是否执行。
2. **G2 无测试库时 seed CRUD 用例会 skip**：本次 CRUD 的实测证据来自 18292 冒烟（真实 scratch PG）。
   若要把集成用例纳入常规回归，需要常备一个 `DATABASE_URL_TEST` 测试库。
3. **W4 依赖**：`issues.html`、工作台动作（confirm_ready/send_to_review）与 SPA 退役仍属 W4；本片未动。
4. **跨片建议**：`uv run` 常驻任务（W6 周期采集）也应确认走同一 spawn helper，才能一并享受进程组超时清理。
