# 配置中心收尾（P13 / R16 修订版）执行日志

> 只追加（append-only）。每轮一条：**做了什么 → 发现 → 怎么验证 → 影响哪些问题**。
> 关联：需求 [`2026-09-15-requirements-gap-plan.md`](./2026-09-15-requirements-gap-plan.md) §1 R16 / §2 G28 / §3.2 P13；
> 前一片（W1，已上线）[`2026-09-14-admin-config-center-log.md`](./2026-09-14-admin-config-center-log.md)；
> change-id `config-center-secrets-and-tests`；证据目录 `.agents/runs/config-center-secrets-and-tests/`。

---

## 2026-09-15 · 第 1 轮：密钥页面设置 + 连通性测试 + 新开关纳管

### 做了什么

1. **独立 worktree**：`.worktrees/config-center-secrets`（分支 `feat/config-center-secrets`，基线＝服务线
   `codex/canonical-v2-s12a-ready` @ `2fe4c16c`）。全程未碰 18188、未重启任何服务、未写任何生产 key 文件，
   E2E 只用 scratch 配置目录 + scratch 端口 18297。
2. **密钥页面设置（写受管密钥文件）**：新增 `config/managed/secrets.json`（白名单：bocha / serper / rerank /
   embedding / llm 五条连接），**原子写 + 权限 0600**（目录 0700），append-only 审计只记字段名、动作与**尾号 4 位**。
   页面「连接与密钥（可设置）」卡片：状态只显示**掩码 + 来源**（env / 受管文件 / 旧 key 文件），输入框为
   write-only（`type=password`），支持**覆盖**与**清除**（清除带二次确认）。
3. **统一"服务启动读取"**：新增 `managed_runtime.apply_managed_runtime_config()`，在**服务启动时**把受管文件里
   *操作员显式设置过*（≠ schema 默认值）的字段与密钥投射进进程环境；**env 永远优先**；**默认值不投射**；
   文件损坏/缺失＝no-op（不会让 boot 失败）。调用点两处：服务包打开路径
   （`open_serving_pack_authority`）与 V2 壳的 FastAPI startup 事件。**不做热读、不做热重载**；页面明确提示
   「修改后需重启服务生效」，且页面不会替用户重启。
4. **连通性测试按钮（每个连接一个）**：Bocha / Serper / rerank(`100.64.0.27:18006`) /
   embedding(`100.64.0.27:18005`) / LLM 档位。**先测后存**：可直接用页面上当前填写但未保存的值（密钥与端点），
   服务端做**一次最小调用**（单结果搜索 / 单文档打分 / 单文本嵌入 / 极短 completion），只返回
   **成功/失败 + 延迟 + HTTP 状态 + 脱敏原因**（响应体一律丢弃，绝不回显凭据）。
   **限频**：每连接 + 每客户端滑动窗口（默认 6 次/分钟、最短间隔 1 秒），超限返回 **429 + retry_after_seconds**
   且**不再发起调用**（防止按钮被刷成计费事故）。provider 主机（Bocha/Serper）在服务端**固定不可改写**，
   避免"页面把凭据指到任意主机"的外泄面。
5. **新开关纳入受管清单 + 逐个判断**（R16/缺口 G28）：

   | 开关 | 页面处置 | 理由 |
   |---|---|---|
   | `CANONICAL_V2_WEB_TOPICAL_FLOOR` | **可编辑** | web 轨召回下限/kill switch，是 R16 要"页面就能改"的典型 |
   | `CANONICAL_V2_RERANK_TIMEOUT_SECONDS` / `_MAX_DOCUMENTS` | **可编辑** | 延迟预算与成本上限，数值有界 |
   | `CANONICAL_V2_SERVING_RECEIPT_PATH` | 只读展示 | 取证路径由服务单元钉死；页面能改会让收据散落 |
   | `CANONICAL_V2_TURN_DEBUG_DIR` | 只读展示 | 调试目录开启即把原始轮次落盘，须由部署显式决定 |
   | `CANONICAL_V2_SERVING_FULL_VERIFY` | 只读展示 | 启动全量校验会把 boot 从秒级拉到分钟级，不能一键切换 |

   只读字段在接口里返回 `editable=false + readonly_reason`，页面渲染为禁用并显示原因；PATCH 尝试写入返回 422。
6. **CLI 消费者同步**：`scripts/settings_status.py --check-keys` 现在对 bocha/serper/local_llm 走同一套受管解析，
   输出 `origin=managed-file` 并标注本进程是否已采用（`adopted_from_managed`）。
7. **测试与证据**：新增 4 个测试文件共 **43 个用例**；scratch E2E（18297 + 本地 mock 18298）走通
   「设置 → 掩码回显 → 先测后存 → 限频 → 清除 → 再设置 → 重启读取生效」；admin-console 全量套件改前/改后对照。

### 发现

1. **"写文件就行"不成立：受管文件由页面保存时会写入整份文档（含默认值）**。若直接把"文件里出现的字段"投射进
   env，就会把出厂默认值伪装成操作员决策（例如把采集配额窗口钉死）。所以启动投射取
   **"与 schema 默认值不同"** 的字段——只有操作员真正改过的值才会进环境；有测试专门锁这一点。
2. **`env > 文件` 的方向要能被看见，否则管理员会怀疑"我改了没用"**：于是接口回报每条密钥/字段的
   **来源**（env / managed-file / legacy-file），并用一个只含变量名的 `CANONICAL_V2_MANAGED_ENV_APPLIED`
   标记"本进程从受管文件采用了哪些变量"——不含任何值。E2E 里表现为：保存后 `adopted=false`，重启后
   `adopted=true`（这正是"启动读取、不热加载"的可观测证据）。
3. **本地 embedding 端点需要凭据**：对 `100.64.0.27:18005/v1` 的一次真调用返回 **401**（端点可达、凭据被拒绝，
   4ms）。也就是说"embedding 无密钥也能用"的假设不成立——这恰恰是页面现在能设置 embedding 密钥的价值所在。
4. **`Bocha`/`Serper` 环境变量在主仓 shell 里是存在的**（本机 env 有真 key）：E2E 必须显式 `env -u` 掉，否则
   测的是 env 而不是受管文件；同时这也验证了来源标注正确（E2E 第 2 节显示 `legacy-file:.bocha_api_key`，
   即 env 未设时回落到仓库根的旧 key 文件，只读、不改写）。
5. **INFO 日志在 uvicorn 默认日志配置下不会落到 stderr**（root logger 无 handler）。所以启动采用凭证的
   "日志证据"在本机 E2E 里看不到；**权威证据改为接口的 `applied_to_process_env` 标记**（含变量名，不含值）。

### 怎么验证

- **新增测试 43 个**（全部用本地生成的假密钥，无任何真 key 进 fixture）：
  - `tests/test_managed_secrets_store.py`（11）：掩码上限（≤3 头 + 4 尾、≤12 字符、短值进一步退化）、
    缺失/损坏文件＝未配置、**0600 + 原子替换 + 无临时残留**、覆盖/清除、**审计无明文**（只留尾号）、
    白名单拒绝、`env > 文件 > 旧 key 文件` 解析、`apply_to_environ` 不覆盖已有 env、描述不含明文。
  - `tests/test_managed_runtime_bootstrap.py`（5）：文件字段投射、**env 已设则跳过**、
    **默认值绝不投射**（含"页面保存整份文档"的场景）、回执不含值、损坏文件 fail-open、
    "启动前进程环境里没有该密钥"（不热读）。
  - `tests/test_canonical_v2_connection_tests.py`（11）：五个连接各构造一条最小请求、
    成功/401/传输失败/超时的结果化处理、缺凭据不发起调用、不安全端点拒绝、限频（间隔 + 每分钟上限 +
    连接维度与客户端维度双作用域）。
  - `tests/test_canonical_v2_admin_secrets_api.py`（11）：**响应永不回显明文**、审计/健康检查无明文、
    **重启才生效（非热读）**、覆盖/清除、白名单与空体 422、**先测后存 + 仅一次调用 + 不落盘**、
    回落受管值、**HTTP 429 + Retry-After 且不再调用**、连接名/端点校验、
    `serving.*` 可编辑字段 + 只读策略 422、`/admin` 页面含密钥卡片与重启提示。
- **scratch E2E（真实 HTTP，18297）**：`/admin`、`/config`、`/system-status`、`/providers/health-check` 全部 200；
  PATCH 设置假密钥 → 文件 0600、明文在文件里（载体）但**响应/审计/日志/页面 0 命中**；
  掩码 `sk-…beef`；先测后存（rerank → 本地 mock，HTTP 200 / 1ms / mock 侧仅 1 次调用）；
  紧接着的第二次调用 **429**（未再发起）；mock 返回 401 时如实报"端点可达、凭据被拒绝"；
  **真端点仅 1 次**（embedding 100.64.0.27:18005 → 401，4ms）；清除 → 再设置；
  重启前 `adopted=false` / 重启后 `adopted=true`；`serving.full_verify` 写入被 422 拒绝、
  `web_topical_floor` 写入成功；重启后 `CANONICAL_V2_WEB_TOPICAL_FLOOR=0` 生效而
  `CANONICAL_V2_RERANK_TIMEOUT_SECONDS=9.0`（env）压过文件里的 2.5。逐字记录见
  `.agents/runs/config-center-secrets-and-tests/e2e-scratch-18297.md`。
- **既有套件对照**：admin-console 全量 pytest 改前（基线 worktree `2fe4c16c`）/改后失败集合逐行比对，
  见 `verification.md`。
- **未动**：检索/融合/rerank/回答路径零改动（仅新增"启动时读受管文件"这一条开关输入）；18188 未重启。

### 影响哪些问题

- **R16（修订）**：页面可设置密钥（掩码回显、可覆盖可清除）+ 每连接连通性测试（先测后存、限频）+ 统一"服务启动读取"
  → 本轮闭环，待 18188 部署后由用户验收。
- **缺口 G28（新开关未纳入受管配置）**：`serving.*` 六个开关纳入白名单，其中三个可编辑、三个只读展示并给出理由。
- **P13 验收线「页面完成'设置 → 测试 → 服务读取生效'闭环；密钥明文不出接口/日志」**：闭环与断言均已产出。
- **待办（非本片）**：18188 部署（需重启，走重放门 + 用户放行）；`.bocha_api_key` 等旧 key 文件与受管文件的
  优先级关系已在页面呈现（受管文件 > 旧 key 文件），若日后要"完全以受管文件为准"，需另立切片清理旧文件消费路径。
