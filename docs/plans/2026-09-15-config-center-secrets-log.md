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


---

## 2026-09-15 · 第 2 轮：真端点验收暴露的"解析链不一致"修复（align to runtime）

### 做了什么

1. **先定位运行期真实来源**（只读取证，不打印任何明文；`/proc/<pid>/environ` 只取变量名）：
   - 活线进程 pid 1886109 的环境里 **没有任何凭据变量**，只有 `CHAT_LLM_PROFILE=deepseekv4flash`
     与几个路径变量；因此所有凭据都来自**仓库根的 key 文件**。
   - embedding：端点由 **release embedding bundle 冻结**（`knowledge_build_isolated.py:6720-6728`，
     `http://100.64.0.27:18005/v1`），实际调用形如 `{base}/embeddings` + `Authorization: Bearer`
     （`company/vectorizer.py:22,40-53`），凭据来自 `load_local_api_key()`
     （`providers/local_api_key.py:8-31`：`API_KEY`→`OPENAI_API_KEY`→`SGLANG_API_KEY`→`.sglang_api_key`），
     调用点在 `knowledge_build_isolated.py:6570`。**没有任何运行期代码读 `EMBEDDING_API_KEY`** ——
     这正是"服务在正常 embedding、页面却报 401"的原因。
   - rerank：`canonical_v2/rerank_client.py:224-236` 的 `configured_reranker()` 在
     **未设置 `CANONICAL_V2_RERANK_BASE_URL` 时返回 None** —— 活线**没有启用 rerank**，也没有默认端点；
     我上一轮的 spec 里那个 `100.64.0.27:18006` 默认端点是**页面自己编的**，所以探到 401 是"测了一个
     运行期根本不用的东西"。
   - LLM：`knowledge_serving_isolated.py:2087-2096`（另见 5972、6070、`llm_judgments.py:304`）按
     **当前 chat profile**（`CHAT_LLM_PROFILE`，活线为 `deepseekv4flash`）解析 → base_url
     `https://api.deepseek.com`、model `deepseek-v4-flash`、凭据 `DEEPSEEK_API_KEY` / `.deepseek_api_key`
     （`professor/llm_profiles.py:14-20,55-66,130-136,244-288`）。上一轮用的是采集侧
     `extraction_endpoints.llm_base_url`（未配置）——**取错了来源**。
2. **把 spec 的解析链对齐到运行期**：新增
   `apps/admin-console/backend/services/canonical_v2_runtime_sources.py`，五条连接逐一按运行期代码路径解析
   （模块头注释里带 file:line）；**删掉所有"页面自造"的默认端点**；连接未启用时**如实报"未启用"并且不发起调用**；
   页面新增"运行期已启用/未启用 + 说明"与端点/模型占位（显示运行期实际值）。
3. **把凭据写到运行期真正读取的变量**（`managed_secrets.SECRET_SPECS`）：
   `embedding.api_key` → `SGLANG_API_KEY`（并接受 `API_KEY`/`OPENAI_API_KEY` 作为解析别名）；
   `llm.api_key` → **当前 profile 的 `api_key_env`**（活线即 `DEEPSEEK_API_KEY`，逐进程解析）；
   `rerank.api_key` 保持 `CANONICAL_V2_RERANK_API_KEY`（与 `rerank_client.py:33-38` 一致）。
4. **区分"现在生效"与"待重启生效"**：受管文件要到重启（启动投射）才进环境，所以页面报告**当前真实来源**
   （env / 旧 key 文件），并把已保存但未生效的值标为 `pending_restart`（页面显示"重启服务后生效"）；
   测试按钮**优先用刚保存的值**并在结果里标注 `managed-file(pending-restart)`，避免"我测的是刚填的值"被误解为运行期现状。

### 发现

1. **"健康检查"曾经在骗人**：embedding 用假来源（`EMBEDDING_API_KEY`）→ 必然 401；rerank 用自造端点 →
   把"未启用"报成"可达但被拒"。**根因不是端点问题，是 spec 没有走运行期解析链**。
2. **两个 rerank 路径要分清**：活线用的是 `canonical_v2/rerank_client.py`（env 驱动、未启用即 None），
   而离线侧 `providers/rerank.py:35` 用 `load_local_api_key()`。已在报告里如实标注：
   rerank 的凭据链 = `CANONICAL_V2_RERANK_API_KEY` → 其 key 文件 → 本地凭据（标注为 `local-key:*`）。
3. **测试隔离性是个安全属性**：第一版对齐测试没注入 key 根目录，导致解析走到了**真实 key 文件**，
   pytest 失败信息里一度出现真实凭据片段。已改为：解析全部注入 fixture 根目录 + 环境变量一律 scrub +
   记录器对非 fixture 值一律 redact（`<redacted-non-fixture-value>`），并在 API 测试里 autouse 清除环境中的
   凭据变量。**明文纪律不因为"这是测试"而放宽。**
4. **泄漏检查要用精确值匹配**：最初的"凭据样式"正则把 8 字符掩码 `k8#…0204` 也算命中（掩码是按设计暴露的
   3 头 + 4 尾）；改成"读取真实 key 文件后在内存里精确计数"后：`/secrets`、`/config`、`/admin`、服务日志
   **全部 0 命中**，`/secrets` 只有 1 个掩码串。

### 怎么验证

- **新增测试 19 个**（本轮）：`tests/test_canonical_v2_runtime_sources.py`（13）锁住"rerank 未配置=未启用而非 401"、
  "embedding 用 bundle 冻结端点 + 本地凭据"、"`EMBEDDING_API_KEY` 不被读取"、"LLM 跟随 chat profile（含切档）"、
  "固定 provider 主机"、"env 优先于 key 文件"、"pending vs adopted"、"公开视图不含凭据"、
  **与官方 `resolve_professor_llm_settings` 的反漂移交叉校验**；另有 6 个补进连接测试/API/存储/bootstrap 套件
  （未启用不发起调用、chat 路径 `/chat/completions`、`/secrets` 带运行期块、显式端点仍可先测后存、
  凭据变量目标、profile 驱动的投射）。受影响簇 106 passed。
- **真端点五连接复跑**（scratch 进程 18297，环境与活线一致，**18188 未重启**；脚本可重放）：
  bocha ✅ 287ms / serper ✅ 1855ms / **rerank ➖ 未启用（0 次调用）** / embedding ✅ 30ms /
  llm ✅ 234ms —— 与运行期现实一致（embedding、llm 都能通，正是服务在用的那条链）。
  本轮真调用 **4 次**（每条已启用连接 1 次），rerank 0 次；逐字记录
  `.agents/runs/config-center-secrets-and-tests/e2e-real-connections.md`。
- **明文复核**（精确值匹配，只输出计数）：四个真实凭据在 `/secrets`、`/config`、`/admin`、服务日志中 **0 命中**。

### 影响哪些问题

- **R16 的验收口径被纠正**：连通性测试必须反映**运行期真实解析链**；"未配置/未启用"要如实说，不能误报 401。
- **交付状态**：本片改动在 admin-console 侧（含 `managed_secrets` 的凭据元数据），**需要一次 18188 重启才生效**；
  线上当前仍是上一版（`e31f173d` 的部署）。交接已写明窗口需求。
- **遗留**：rerank 若要真正启用，需配置 `CANONICAL_V2_RERANK_BASE_URL`（页面可填，重启生效）；
  LLM 档位切换（`CHAT_LLM_PROFILE`）目前是部署侧 env，不在页面可改范围（profile 表由数据线维护）。
