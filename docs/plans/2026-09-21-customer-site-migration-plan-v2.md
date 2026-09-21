# 客户现场迁移计划 v2（2026-09-21 重新定基线）

> 取代 `2026-08-14-customer-site-migration-plan.md`（该文件保留，作为当时的决策记录）。
> 重写原因：08-14 以来系统变了四处（服务包取代老布局、Milvus 退出服务包、配置中心上线、
> 采集线引入 Postgres），旧计划自己就要求"执行前按当时 HEAD 复核"。
> 本文的每条断言都带 `path:line` 或实测，来源是两轮只读侦察 + 本机实测。

---

## 1. 先看结论：三个必须拍板的决定、一个真阻塞

| # | 决定 | 选项与后果 | 建议 |
|---|---|---|---|
| **D1** | **现场 embedding 端点** | (a) 客户提供一个托管 **同模型同维**（Qwen3-Embedding-8B / 4096）的 API——我们改 bundle JSON + 常量 + 哈希（一次评审，属代码变更）；(b) 现场自建——**与"无 GPU"冲突，排除**；(c) 关掉向量道——主要召回通道没了，不推荐 | **(a)**。这是**唯一真正的代码级阻塞**，也是关键路径 |
| **D2** | **现场装不装 Postgres** | (a) 装：`/seeds`（花名册）、`/upload`（导入）、3 个运维任务全可用；(b) 不装：这三个面 **503**、导航自动隐藏，**`/chat` 完全不受影响** | **(a)**——R12 要的"周期性更新本地库"就落在这条线上 |
| **D3** | **路径策略** | (a) **同构**：目标机复刻完全相同的绝对路径；(b) 异构：重新封印——但封印需要 **7.8 GB 的构建信封**（`--envelope-output` 的父目录必须存在且路径被逐字符冻在 serving bundle 里），等于把信封也搬过去 | **(a) 同构**。异构的实际代价远超收益 |

**一句话**：迁移的技术风险集中在 **embedding 端点**（一处代码改动）；其余全是"照抄布局 + 搬文件 + 预置状态目录"的工程活。

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

## 3. 唯一的代码级阻塞：embedding 端点

实测（三方只读侦察）：

- 服务期 embedding 适配器来自**内容寻址的发布包 bundle**，函数把文件内容与代码里的期望值**逐字段相等**比对：
  `base_url = http://100.64.0.27:18005/v1`、`dimension = 4096`、`model_id = Qwen/Qwen3-Embedding-8B`
  （`knowledge_build_isolated.py:8186-8199`），且 `content_sha256` 必须等于代码常量 `_QWEN_EMBEDDING_BUNDLE_SHA256`。
- **没有运行期覆盖**：受管配置虽然把 `extraction_endpoints.embedding_base_url` 投影成
  `CANONICAL_V2_EMBEDDING_BASE_URL`，但**全仓无任何读者**（页面自己也标了只读、写明了原因）。
- 维度不能变：索引向量矩阵（`vector_matrix.npz`，1.68 GB）由该模型构建，换模型/换维度 = 949M 索引作废。

**改法（现场迁移的前置片，须过一次评审）**：生成指向客户 embedding 端点的新 bundle JSON →
更新 `_QWEN_EMBEDDING_BUNDLE_SHA256` 常量 → 更新 `--recorded-embedding-bundle` 指向 →
冒烟验证"同一条 query 的向量道可用"。

> 对比旧计划说的"embedding/rerank 两处默认值改成读环境变量"——今天做不到，那两处已经不是普通默认值，
> 而是内容寻址权威。**rerank 反而是完全配置化的**（页面可改端点/模型/超时/密钥），
> **chat LLM 是"代码内置 7 档 + 配置选档"**（要加表里没有的端点仍需改代码）。

---

## 4. 10 步路线（1–5 复核更新，6–10 补齐）

| 步 | 内容 | 状态 |
|---|---|---|
| **1** | 目标机条件确认（无 GPU、可联网、Ubuntu+root） | 已完成（08-14） |
| **2** | 本机打包（§2 清单；每包附 `sha256sum`） | **待重做**：内容与尺寸全变了，旧清单作废 |
| **3** | 目标机基础环境：uv、同名用户、**完全相同的绝对路径**、`uv sync`、Chromium、`loginctl enable-linger`、`/var/tmp` 豁免 | 复核更新 |
| **4** | 数据落位与校验：逐文件 `sha256sum -c`；**新增**：pack manifest 的 `index_root` 必须与落位路径逐字符一致；状态目录预建；属主统一（`milvus.db` 议题已消失） | 复核更新 |
| **5** | **模型端点改造（关键路径，最先做）**：按 §3 换 embedding bundle；chat LLM 选档（或加档）；rerank 视需要开（页面可配） | **重写** |
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
- **回退**：`--serving-pack` 换回旧包 + 重启（291 s）；或整个服务停掉。
  现场首启若硬失败，日志会明确说是 pack / index root / bundle / 门禁目录哪一项，不需要猜。

## 7. 未验证项（诚实记录）

- embedding 不可达时"只有向量道失败、其他道仍能答"是**从代码路径推断**，未做故障注入。
- `/api/canonical-v2/admin/status` 的 500（`deploy/README.md` 里的既有待办）本次未复现。
- 3.47 GB `relationships.json` 在**目标机**（可能更慢的磁盘/更少内存）上的启动耗时未测——
  本机 authority 相位约 125 s、进程 RSS 17.3 GB，目标机需按此配内存。
