# 客户现场迁移计划 v2（2026-09-21 重新定基线）

> 取代 `2026-08-14-customer-site-migration-plan.md`（该文件保留，作为当时的决策记录）。
> 重写原因：08-14 以来系统变了四处（服务包取代老布局、Milvus 退出服务包、配置中心上线、
> 采集线引入 Postgres），旧计划自己就要求"执行前按当时 HEAD 复核"。
> 本文的每条断言都带 `path:line` 或实测，来源是两轮只读侦察 + 本机实测。

---

## 1. 先看结论：现状**不能**直接部署——迁移前有两个必须先做的代码改动

> 2026-09-21 第二轮修订（原 §1 的 D1 写的是"改 bundle JSON + 常量 + 哈希"；代码级取证推翻了那个口径，
> 见 §3.1 的逐行证据）。

**判定：把服务按现状搬到"够不到学校内网"的甲方机器上，第一轮对话就会失败——不是降级，是报错。**

- 普通问题固定带向量道（`("exact","structured","lexical","vector","web")`），向量道每轮要对 query 做
  **一次**嵌入调用；地址冻死在 `http://100.64.0.27:18005/v1`（学校机器）里，页面改不动。
- 端点不可达时，**失败被改写成"完整性错误"**（不是 `TimeoutError`），道调度器不认 → 异常穿出检索层 →
  用户看到红字 `canonical_v2_release_mismatch`；黑洞路由下要等 **180 秒**才报。
- 同一轮里 exact / structured / lexical / relationship / web **五条道全是好的**，但没人去用它们。
- 现场无 GPU（08-14 已确认）⇒ 嵌入服务只能来自外部同模型服务，而端点地址目前不可配置。

⇒ 迁移的前置不是"照抄布局 + 搬文件"，而是 **F1（向量道降级）+ F2（嵌入端点配置化）** 两个小改动（§3）。
两处都是行为变更，走 OpenSpec change；**不触发重建、不重新封印**（bundle 文件一个字节都不动）。

| # | 决定 | 选项与后果 | 建议 |
|---|---|---|---|
| **D1** | **现场的嵌入服务从哪来** | (A1) 甲方提供 OpenAI 兼容、**同模型同维**（Qwen3-Embedding-8B / 4096）的端点——我们改一处配置即可；(A2) 甲方给一张 GPU，我们在其机器上起嵌入服务；(A3) 打通甲方到学校 `18005` 的网络（tailnet / 内网路由）；(A4) 换可在 CPU 跑的小模型——**要重建索引 + 重新封印 + 重跑测试集**，不在本次范围；(A5) 不要向量道（只做 F1）——语义召回没了，点名/词法/关系/web 照常 | **(A1)**；拿不到就推 (A2)。(A4) 是"彻底去掉服务期网络依赖"的长期选项，单独立项 |
| **D2** | **现场装不装 Postgres** | (a) 装：`/seeds`（花名册）、`/upload`（导入）、3 个运维任务全可用；(b) 不装：这三个面 **503**、导航自动隐藏，**`/chat` 完全不受影响** | **(a)**——R12 要的"周期性更新本地库"就落在这条线上 |
| **D3** | **路径策略** | (a) **同构**：目标机复刻完全相同的绝对路径；(b) 异构：重新封印——但封印需要 **7.8 GB 的构建信封**（`--envelope-output` 的父目录必须存在且路径被逐字符冻在 serving bundle 里），等于把信封也搬过去 | **(a) 同构**。异构的实际代价远超收益 |

**一句话**：迁移的技术风险是 **§3 的两个改动 + D1 的嵌入服务落点**；其余仍是"照抄布局 + 搬文件 + 预置状态目录"的工程活。
**需要你/甲方提供的输入见 §8**——其中第 1 条（甲方能不能访问学校 `18005`）直接决定 D1 走哪条。

---

## 2. 交付物清单（按今天的系统重算）

| 批次 | 内容 | 尺寸 | 备注 |
|---|---|---|---|
| 代码包 | 整个 worktree（排除 `.venv`、`htmlcov/`、`report.html`），含 `deploy/`、`config/managed/*`（**gitignore 掉的，必须显式带上**） | ~2 GB | `.venv` 到现场 `uv sync` 重建（需联网）；`_editable_impl_*.pth` 里是绝对路径，**移动 checkout 必须重建 venv** |
| **服务包** | `serving-pack-run16-readerbound/`：`manifest.json`(11M) + `relationships.json`(**3.47G**) + `lookup.sqlite3`(896M) + `institution_catalog.json` + marker | **~4.4 GB** | v2，**无 `milvus.db`**；父目录里同级还要能写 `<pack>.mount-receipt.json` |
| **索引根** | `index-v3-v2/`：`lookup.sqlite3`(896M) + `vector_matrix.npz`(1.68G) + marker | **~2.6 GB** | **必须有，且必须是 pack manifest 里记的那个绝对路径**；**不得**含 `milvus.db` |
| 发布 bundle | `serving-bundle-run16.json`、`qwen-embedding-bundle-v1.json`（+ `--recorded-decision-bundle`、`--source-manifest` 两个服务路径不读但 argparse 要求存在） | 几 MB | serving bundle 里冻了 `index_root` / `envelope_path` / `database_name`，改任一项都要重算它的 sha 并同步 `--recorded-serving-bundle-sha256` |
| 门禁目录 | `--accepted-backup-gate-root` 指向的**另一棵树**（data-rebuild），其 `<root>/s12a/` **必须存在** | 空目录即可 | 信封文件本身服务路径**从不打开**，但父目录必须存在且祖先链无软链 |
| 密钥 | `.deepseek_api_key` `.bocha_api_key` `.serper_api_key` `.sglang_api_key`（放代码根**或祖先**目录）**或**改用 `config/managed/secrets.json` | 几 KB | 独立加密渠道；落位后 0600 |
| 状态目录 | `/var/tmp/mirothinker-canonical-v2-s12f/`（**目录必须先存在**） | 首启自动建库 | 账号库/会话密钥/首启口令/access-log 都落这里；目录不存在时**只有一行 warning**，管理面直接不可用 |
| 运行期依赖 | Chromium（`uv run playwright install chromium` + `install-deps`，要 root）；`sudo loginctl enable-linger` | ~300 MB | Chromium 是**运行期**依赖（网页抓取 tier-1），不是构建工具 |
| 可选 | Postgres（D2=(a) 时）：建库 + `alembic upgrade head`（V042，42 表）+ 注入 `DATABASE_URL` | — | 受管配置**不允许**承载 DSN（schema 显式拒绝），只能走 systemd drop-in / env |

**不再需要**：旧计划里的 1.3 GB 老 `milvus.db`——服务路径对它**零 I/O**，只比一个路径字符串。

---

## 3. 迁移前的两个代码改动（F1 / F2）

### 3.1 现状取证（本机代码级，2026-09-21；逐行读过，未做故障注入）

| 环节 | 事实 | 位置 |
|---|---|---|
| 规划器 | 普通问题固定五道，含 `vector` | `knowledge_serving_isolated.py:663` |
| 向量道取 query 向量 | 每轮一次 `embed_batch((query,))` | `serving_pack_loader.py:1697-1699` |
| 传输 | 单 POST、无重试、无熔断、`timeout=180`、`trust_env=False`（代理环境变量不生效） | `company/vectorizer.py:39-59` |
| 异常改写 | 适配器层把**所有**异常（含拒连/超时）统一包成 `IsolatedKnowledgeReadIntegrityError`（`ValueError` 系） | `knowledge_read_isolated.py:305-312` |
| 调度器 | 只放过 `TimeoutError`；非 web 道 `timeout_seconds=None`（无上限） | `knowledge_read.py:7579-7589` |
| 用户可见结果 | 异常穿出 `execute()` → SSE `event: error` → 页面红字 `canonical_v2_release_mismatch`；同步口 HTTP 409 | `api/canonical_v2_chat.py:434-451`、`static/chat.html:2017-2029` |
| 端点冻结 | bundle 逐字段相等校验（含 `base_url`）+ 常量 `_QWEN_EMBEDDING_BUNDLE_SHA256` | `knowledge_build_isolated.py:8186-8199` |
| 配置无读者 | `CANONICAL_V2_EMBEDDING_BASE_URL` 只有字段→env 映射；连接卡测的是冻结默认地址 | `managed_config.py:74`、`canonical_v2_runtime_sources.py:282-320` |
| 启动期 | **不触网**（keep-warm 只在空闲周期调用且吞异常） | `canonical_v2_keepwarm.py:56-59` |

**读法**：启动没问题；**第一轮对话必死**，且死的不是向量道一条，是整轮。

### 3.2 F1 —— 向量道降级（fail-open）

**根因**：把"**运输失败**"和"**身份/完整性失败**"混成了同一个异常。前者应当降级（少一条召回道），
后者必须 fail-closed（数据身份不对就不能答）——现在两者都走 fail-closed。

改法（四处，都是删错逻辑而不是加补偿）：

1. `_ValidatingEmbeddingAdapter.embed_batch`：只把**校验类**失败包成完整性错误；底层适配器的传输异常**原样上抛**
   （`TimeoutError` / `ConnectionError` 正是调度器已经认得的两种）。
2. 向量道加**超时上限**（web 道已有 `timeout_ms` 机制，向量道给默认值，如 8s）；黑洞路由不再挂 180 秒。
3. 连续失败 → 短熔断（照 `web_lane_resilience.py` 的形状），避免每轮都等超时；keep-warm 走同一判定。
4. 降级要**可见但不打扰**：检索 trace 里向量道 `status=unavailable`、访问日志可查；给用户的答案照常出、不报错。

**验收**：把生效端点指向一个黑洞地址 → 同一轮问题仍出答案（本地引用 + web），TTFT 不超预算；
端点恢复后按熔断窗口自动恢复（不需要重启服务）。

### 3.3 F2 —— 嵌入端点：冻"身份"，不冻"地址"

**原理**：该冻的是**身份**（模型 id / 维度 / 索引矩阵与包的绑定——换了索引就作废）；
不该冻的是 **HTTP 地址**——它是运维参数。为换一个地址而重新封印（41 分钟）并搬 7.8 GB 信封，
正是"证明做在了错的层"。

改法（**不动 bundle 文件、不重新封印**）：

1. 运行时 base_url 解析顺序：受管配置 `extraction_endpoints.embedding_base_url`（页面可改、可连测）
   → 缺省回落 bundle 里记录的值。
2. 冻结校验：除 `base_url` 外逐字段相等；`base_url` 只要求非空 http(s)。
   `content_sha256` ↔ `_QWEN_EMBEDDING_BUNDLE_SHA256` 的比较**保留**——这才是"我们发出去的 bundle 就是我批准的那份"，
   一处一次。
3. `/admin` 嵌入连接卡改测**生效地址**（现在测的是冻结默认值，页面上看不出差别）。
4. 生效时机与配置中心其余项一致（保存 → 下次重启生效；页面已有"待重启"标记）。
5. （建议同切片）**身份探针**：构建期把一条固定探针串的向量存进 bundle；连测时用生效端点重算并比对
   （余弦 ≥0.999），防"地址对、模型错"。现在这类错**静默**产生错排序——向量轨迹校验在 2026-08-30 被关过
   （`knowledge_read_isolated.py:8066-8076`）。

**验收**：页面改地址 → 连测通过 → 重启后向量道可用；地址写错时连测明确失败、服务不崩。

### 3.4 端点之外的三件事（现状，迁移时按此核对）

- **rerank 反而是完全配置化的**（页面可改端点/模型/超时/密钥）；**活线今天是关的**，现场要看再开。
- **chat LLM 是"代码内置 7 档 + 配置选档"**（活线 `deepseekv4flash`，key 独立渠道）；要加表里没有的端点仍需改代码。
- **维度/模型不能变**：`vector_matrix.npz`（1.68 GB）由 Qwen3-Embedding-8B 构建，换模型/换维度 = 索引作废（→ D1-A4）。

---

## 4. 10 步路线（1–5 复核更新，6–10 补齐）

| 步 | 内容 | 状态 |
|---|---|---|
| **1** | 目标机条件确认（**无 GPU**、可联网、Ubuntu+root） | 已完成（08-14）；**建议复核**（§8 第 2 条） |
| **2** | 本机打包（§2 清单；每包附 `sha256sum`） | **待重做**：内容与尺寸全变了，旧清单作废 |
| **3** | 目标机基础环境：uv、同名用户、**完全相同的绝对路径**、`uv sync`、Chromium、`loginctl enable-linger`、`/var/tmp` 豁免 | 复核更新 |
| **4** | 数据落位与校验：逐文件 `sha256sum -c`；**新增**：pack manifest 的 `index_root` 必须与落位路径逐字符一致；状态目录预建；属主统一（`milvus.db` 议题已消失） | 复核更新 |
| **5** | **代码改动 F1 + F2（关键路径，最先做）**：见 §3；打包以改动后为准。另外：chat LLM 选档；rerank 视需要开（页面可配） | **重写** |
| **6** | **密钥与启动参数**：密钥走受管密钥页或键文件（0600）；命令文件按"同构"核对（**85 个参数里只有 11 个有服务语义**，其余是构建期账本，见 §5） | 新写 |
| **7** | **首启冒烟**：起服务 → 看 `console_database=configured`、`Uvicorn running`、pack authority 相位耗时 → `/chat` 问一句 → `/main` 登录（首启口令文件）→ 五个管理页 200/302 | 新写 |
| **8** | **反代与对外发布**：端口 18188（runner 钉死 `0.0.0.0:18188`）、防火墙、反代与 TLS、管理面访问控制 | 新写 |
| **9** | **守护与日常运维**：systemd 单元 + drop-in 清单、`/var/tmp` 清理豁免、台账/日志保留期、周期更新（构建 8h + 封印 41min + 切包 291s） | 新写 |
| **10** | **回退预案与验收**：保留旧包与旧命令文件，切包 = 改一个 token + 重启；验收 = replay 7/7 + 两个逐字探针 + 你的实际体验 | 新写 |

---

## 5. 顺手可做的一件事：把命令文件从 85 个参数减到 11 个

实测：**85 个参数 token 里只有 11 个在 `--serve --serve-existing --serving-pack` 路径上被消费**，
其余（`--database-url`、`--candidate-staging-root`、`--source-manifest`、15 个 `--source-batch-id`、
6 个版本对、决策 bundle、两个 original-milvus 哈希、信封路径）都是**解析后从不读取**的构建期账本。

迁移前把它们从服务命令文件里摘掉，收益有三：
1. 现场"哪些参数是真的"一目了然，减少误改（现在很容易改到一个看起来相关的死参数）；
2. 三个 `--accepted-original-milvus-*` 里有两个是**纯死参数**，现场不必纠结它们指向的文件在不在；
3. 后续换机器/换路径时，要核对的面从 85 个变成 11 个。

代价：一次改动 + 一条"服务模式不需要这三个参数"的测试（旧计划 §"摘掉 1.3G"里已写过同样的改法）。

---

## 6. 验收与回退

- **验收基准（与本地一致）**：replay 门 **7/7**；G1–G7 逐条通过；`/chat` 与五个管理页可达；
  TTFT 与本机同量级；**你自己在目标机上问几个真实问题**。
- **新增两条（本轮的 F1/F2 专属）**：
  1. **降级探针**：把生效嵌入端点指向黑洞地址 → 同一轮问题仍出答案（本地引用 + web），TTFT 不超预算；
     访问日志记 `status=ok`、trace 里向量道 `unavailable`。
  2. **端点改配置探针**：在 `/admin` 改地址 + 连测 → 重启后向量道可用；写错地址时连测明确失败、服务不崩。
- **回退**：`--serving-pack` 换回旧包 + 重启（291 s）；或整个服务停掉。
  现场首启若硬失败，日志会明确说是 pack / index root / bundle / 门禁目录哪一项，不需要猜。

## 7. 已取证 / 仍未验证（诚实记录）

**本轮由"推断"升级为"取证"**（逐行读过代码，未做故障注入、未重启服务）：

- 嵌入端点不可达时**不是**"只有向量道失败、其他道仍能答"，而是**整轮失败**（§3.1 的链路）。
- 启动期不触嵌入端点：进程能起来并保持（keep-warm 只在空闲周期调用且吞异常）。

**仍需现场或另测**：

- 失败**多快**发生：拒连（无路由 → 立即 `ConnectError`）vs 黑洞（有默认路由 → 挂到 180 s 超时）。
  这条取决于甲方网络，本机未验证；F1 的超时上限正是为此而加。
- 3.47 GB `relationships.json` 在**目标机**（可能更慢的磁盘/更少内存）上的启动耗时未测——
  本机 authority 相位约 125 s、进程 RSS 17.3 GB，目标机需按此配内存。
- `/api/canonical-v2/admin/status` 的 500（`deploy/README.md` 里的既有待办）本次未复现。

## 8. 需要你（或甲方）提供的输入

| # | 输入 | 为什么它决定方案 |
|---|---|---|
| 1 | 甲方机器**能不能访问学校 `100.64.0.27:18005`**？（有没有专线/VPN/tailnet） | 直接决定 D1 走 A1（他们给端点）/ A2（他们给 GPU）/ A3（打通网络）/ A5（先不要向量道） |
| 2 | 甲方机器规格：内存（**≥64 GB**）、CPU 核数、磁盘（≥50 GB 空余）、**有没有 GPU** | 内存是硬约束（本机 RSS 17.3 GB）；有没有 GPU 决定 A2/A4 是否可能 |
| 3 | 装不装 **Postgres**（D2） | 决定 `/seeds` `/upload` 与 3 个运维任务是否可用（周期更新落在这条线） |
| 4 | 出网能力：默认网关 / 代理 / 防火墙白名单 | chat LLM（DeepSeek）、web 轨（Bocha/Serper）、Chromium 抓取都要出网 |
| 5 | 部署窗口、执行人、是否允许 root + systemd + `loginctl enable-linger` | 决定 §4 步骤 3/8/9 的形态 |
| 6 | 对外域名 / 反代 / TLS 由谁提供 | §4 步骤 8 |
