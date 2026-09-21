# 客户现场迁移 · 执行日志（只追加）

> 计划在 [迁移计划 v2](./2026-09-21-customer-site-migration-plan-v2.md)；本文件只记"实际做了什么、发现了什么、怎么验证的"。
> 每轮一条，不改历史条目。

---

## 第 1 轮 · 2026-09-21 · "按现状能不能搬过去"——答案是不能，且阻塞点被定位到一行代码

**背景**：用户拍板"按现状部署到甲方服务器，后续优化再推"。所以这一轮的问题只有一个：
**今天的系统搬到甲方机器上，第一轮对话能不能出答案？**

**做了什么（只读取证，未动任何代码、未重启 18188）**：

1. 派子代理做全链路代码取证（启动期是否触网 / 请求期向量道失败会怎样 / 用户看到什么 / 有没有不改代码就能改端点的办法）。
2. 本机复核关键几行：道调度器的异常容忍面、适配器包装层的异常改写、规划器的默认道集合、嵌入解析的配置链、连接测试取的地址。

**发现（每条都带位置，逐行读过）**：

| 环节 | 事实 | 位置 |
|---|---|---|
| 规划器 | 普通问题固定五道，含 `vector` | `knowledge_serving_isolated.py:663` |
| 调度器 | 只放过 `TimeoutError`；非 web 道 `timeout_seconds=None`（无上限） | `knowledge_read.py:7579-7589` |
| 适配器包装层 | **把所有异常**（含拒连/超时）统一改写成 `IsolatedKnowledgeReadIntegrityError`（是 `ValueError`，不是 `TimeoutError`） | `knowledge_read_isolated.py:305-312` |
| 端点冻结 | bundle 逐字段相等校验（含 `base_url`）+ 代码常量 `_QWEN_EMBEDDING_BUNDLE_SHA256` | `knowledge_build_isolated.py:8186-8199` |
| 配置无效 | 受管配置只把字段投影成 `CANONICAL_V2_EMBEDDING_BASE_URL`，**全仓无读者** | `managed_config.py:74`（活线树） |
| 连接测试 | `/admin` 的嵌入连接卡取的是**冻结默认地址**，不是配置值 | `canonical_v2_runtime_sources.py:282-320`（`resolve_embedding` → `EmbeddingClient()`） |
| 启动期 | **不触网**：进程能起来、能保持（keep-warm 只在空闲周期跑且吞异常） | `canonical_v2_keepwarm.py:56-59` |

**结论**：**启动没问题；第一轮对话必死。**
向量道每轮一次嵌入 POST → 端点不可达（或超时）→ 被改写成 `ValueError` 系 → 调度器不放过 → 穿出 `execute()` →
SSE `event: error` → 页面红字。同一轮里其余五条道全健康，但检索层没有"少一条道也继续"的机制。

**这一轮修正的口径**（两条，都写回了计划 v2）：

1. 原 §1 的 D1 说"改 bundle JSON + 常量 + 哈希"——那是把**运维参数当数据身份冻**，正是要消除的过度设计。
   新口径：**F2 冻"身份"（模型 id / 维度 / 矩阵绑定），不冻"地址"**；地址走受管配置，bundle 文件不动、不重新封印。
2. 原 §3 只讲了"改端点"，漏了更严重的一半：**向量道失败不该杀死整轮**。新口径把 F1（降级）列在与 F2 同等的地位。

**验证方式**：纯代码路径取证（没有故障注入、没有重启服务）；计划 §7 把"失败多快发生"标为仍需现场确认。

**影响哪些问题**：迁移交付线（R17 第二步）从"照抄布局"改为"F1+F2 前置"；R2/R4（本地优先、TTFT ≤30s）
在这条路径上本来会被 180 秒超时直接违反——F1 同时是这两条需求的实现前提。

**下一步**：开 OpenSpec change 做 F1+F2（改完本机验证：把生效端点指向黑洞地址，同一轮问题仍出答案）。

## 第 2 轮 · 2026-09-21 · 前提更新：甲方可达我方模型服务 ⇒ 现状可部署；交付方案成文、打包与演练开工

**用户给定前提**：① 甲方服务器**可以访问我方部署的模型服务**；② 后续会改用阿里云提供的嵌入服务。

**因此改掉的口径（三条，都已写回文档）**：

1. **D1 结案**：嵌入服务落点＝**用我方现有模型服务**（冻结地址 `100.64.0.27:18005` 本次**不动**）⇒ 第 1 轮"现状不能直接部署"的判定只适用于"够不到我方模型"的情形，可达时**现状即可部署**（迁移计划 v2 §1 已加前提注记）。
2. **F1/F2 重新定位**：F2（端点可配置）＝**切到阿里云或自建嵌入之前必须完成**（不是首交付前提）；F1（向量道降级）＝**模型服务抖动的保险**（仍是"稳定上线"的要求，但不再阻塞搬迁）。
3. **交付方案成文**：`docs/plans/2026-09-21-customer-site-delivery-plan.md`（执行版：范围、八项交付物、前置条件、路径契约、P0–P5 步骤与验证点、分层验收、三级回退、周期更新模型、风险、待确认项）。

**这一轮新增的两个认知（值得记住）**：

- **代码树路径可以换，数据路径不能换**：三处冻结的是 `index_root` 等**数据**路径；代码根换个目录只需重写命令文件（演练正是要验证这一点）。
- **命令文件里 ~85 个参数中大部分是"解析期要求存在"的构建期账本**：不做参数清理，现场就得按 `site-paths.txt` 造一批占位目录/文件（含 `data-rebuild` 树路径）；清理到 11 个则可以整类消失。已列入 P0-6（建议做，需一次启动回归）。

**已开工**（后台执行，产出证据后回报）：

- 交付件打包器 `deploy/build-delivery-kit.sh`（code.tar + checksums + `site-paths.txt` + kit manifest）；
- 现场自检 `deploy/preflight.sh`（路径/校验和/端口/状态目录/依赖/出网 + **三条模型探针：嵌入断言 200 且维度 4096**）；
- **本机"模拟甲方"演练**：scratch 代码根 + 端口 18299 + scratch 状态目录，用真实服务包走一遍现场步骤（记录 `uv sync` 耗时、启动相位、`/chat`、replay 门），并把它当成 runbook 的第一次实跑。

**未完成 / 待验证**：F1+F2 的实现片仍在飞（独立 worktree，OpenSpec + 验证合同先行）；演练不覆盖"不同数据根路径"（路径冻结，本机不可模拟）与甲方自身的网络/系统差异。

**影响哪些问题**：R17 迁移交付进入执行态；"能否部署"的判定从"需要先改代码"变为"按交付方案执行，F2 在切阿里云前补齐"。

## 第 3 轮 · 2026-09-21 · 交付件打包 + 本机"模拟甲方"演练通过（裸机路径）

**做了什么**：`deploy/build-delivery-kit.sh`（打包器）+ `deploy/preflight.sh`（现场自检）落地；把 `code.tar` 解到 scratch 代码根、`uv sync`、拿真实服务包在 **scratch 端口 18299 + scratch 状态目录**完整拉起一遍，跑冒烟与 replay 门，跑 preflight，停服。**18188 全程未被触碰**（演练后仍 200，pid 519941 未重启）。

**实测数字**（证据：`.agents/runs/delivery-kit-rehearsal/verification.md` + 同目录原始产物）：

| 环节 | 结果 |
|---|---|
| 打包 | 56 s 冷跑 / 15 s 复跑；`code.tar` 429 MB（4,677 项），sha256 已记录 |
| 解包 | 0.46 s |
| `uv sync --frozen` | **1.3 s**（热缓存）/ **7.9 s**（强制冷缓存，247 包） |
| 启动 | **291.0 s**（走收据路径） |
| 内存 | RSS 17.24 GiB（跑 19 轮后 17.34 GiB；活线对照 17.33 GiB） |
| 冒烟 | 「优必选科技有哪些专利」HTTP 200、**首字 1.64 s**、总 30.51 s、**12 条本地专利引用**、无 `event: error` |
| 管理面 | 登录 200 → `/api/auth/me` 200 → `/admin` 200（`admin-auth.key` 首次登录时惰性创建） |
| replay 门 | **G1–G7 全 PASS**（19 轮，均 15.7 s，总 4 m 59 s） |
| preflight | `failures=0 warnings=3` → READY（53 PASS）；服务在跑时能正确 FAIL 并点名端口持有者 |

**新发现（6 条，已写进交付方案 §4）**：

1. **发布 bundle 副本里冻着我们的 `envelope_path`**——现场要么把这条路径树建出来（容器形态天然满足），要么改 bundle 副本并重算哈希（`content_sha256` + `--recorded-serving-bundle-sha256` + 刷新 `checksums.sha256`）。**这是现场最容易漏、且启动会 fail-closed 的一步。**
2. `--envelope-output` 必须等于 `<gate-root>/s12a/complete-candidate-build-envelope.json`，且 `s12a/` 必须存在（空目录即可）。
3. **端口不是自由的**：runner 只认 18188，除非走 `s12e` 包装脚本（现场换端口靠它）。
4. chat 档位在 `config/managed/settings.json`（决定端点与密钥文件名），不在命令文件里；密钥文件沿代码根向上找。
5. `apps/admin-console` 会**另建一个 venv**（216 包）——容器形态应预先同步，否则现场跑 replay 门要联网。
6. **每次启动都会重写挂载收据**（包的父目录必须长期可写）；日志被 `PydanticSerializationUnexpectedValue` 刷屏（**8 分钟 4.7 万行**）——运维需按此规划日志空间，且值得单独立一个"日志降噪"小项。

**未证明（诚实记录）**：不同数据根路径（路径冻结，本机无法模拟）、现场 OS/网络/文件系统差异、冷页缓存下的启动耗时、Chromium 抓取质量、PostgreSQL 相关页面（本机没装 PG）、密钥交付渠道、以及"85→11 清理后仍能启动"。

**影响哪些问题**：R17 迁移交付有了**第一个端到端证据**（不是"按文档应该能跑"，而是"按现场步骤真跑通了"）；v1 冻结（`delivery-v1`）的交付件从此可复核（kit + checksums + preflight + 演练记录）。

## 第 4 轮 · 2026-09-21 · F1/F2 完成并验证：向量道降级 + 嵌入端点可配置（迁移阻塞项解除，归 **v1.1**）

**做了什么**（分支 `fix/embedding-lane-f1f2`，6 个提交，基线 `36df47b8`；**不进 v1 冻结**）：

- **F1**：传输类失败在唯一发 HTTP 的地方（`company/vectorizer.py::EmbeddingClient.embed_batch`）归一为内建 `TimeoutError` / `ConnectionError`（含非 2xx、非 JSON 两类边界），`_ValidatingEmbeddingAdapter` 对这两个内建**原样透传**——`_invoke_lane` 里**早就存在**的 fail-open 钩子这才真正生效；向量道新增 **8 s 外层等待上限**（`CANONICAL_V2_VECTOR_LANE_TIMEOUT_SECONDS`）与 **连续 2 次失败 → 300 s 跳过**的短熔断（新 `embedding_lane_resilience.py`，状态放在适配器里，keep-warm 因此共享）。
- **F2**：新增唯一解析点 `resolve_embedding_base_url`（受管配置 `extraction_endpoints.embedding_base_url` 优先 → 否则用发布包记录的地址）；冻结校验保留 `content_sha256` / 模型 / 维度，**不再携带 `base_url` 字面量**；管理页改为上报并测试**生效地址**，地址行可编辑、文案不再声称端点被冻结。**发布包一字节未改、未重新封印。**

**发现**：

1. 红气泡根因坐实：`except Exception` 把"连不上/超时"洗成"完整性失败"，而调度器只放过内建 `TimeoutError`/`ConnectionError` ⇒ **一直在的 fail-open 钩子永远不触发**。
2. **AC6 口径修正**：发布包的 `content_sha256` 就是文档自身的自哈希、`base_url` 在哈希之内 ⇒ "改包内地址同时保留自校验"在密码学上不成立。可行且更严格的形式就是实现取的这条：**包冻结 + 运行期覆盖地址**。
3. 熔断放在适配器内的副作用：**构建期**端点打不通时也会在第 2 次失败后跳过（端点死了构建本来就跑不成，净效果相同）——记录在案。

**怎么验证**（关键部分本机独立复跑过）：

- 新增 **52 个测试全绿**；我复跑 4 个 miroflow-agent 新文件 = **29 passed / 22.0 s**，管理侧 `test_embedding_effective_endpoint.py` = **8 passed / 0.83 s**。
- admin-console 全量套件前后**失败集合逐字节一致**（25F/105E/1481P → 25F/105E/1490P，130 条 ID `comm` 无差异）——没有引入新失败。
- miroflow-agent 定向 **376 passed + 1 failed**（该失败**在基线上同样失败**，既有红）。
- **真实探针**（scratch 端口 18285；18188 全程未动，事后 `/chat` 200、pid 519941 未重启）：嵌入地址指向黑洞 `10.255.255.1:9` → 一轮真实 `/api/chat/stream` **39.8 s 正常结束、无 `event: error`**、向量道 `unavailable`、其余四路照常答题、访问日志 `completed`；换回真实地址 → 向量道 `succeeded`、128 候选、车道耗时 0.87 s。

**未验证 / 遗留**（诚实记录）：

- `tests/canonical_v2/test_knowledge_build_isolated.py` 两次都在 25 分钟预算内没跑完（~55%），**该文件的基线对比缺失**（补跑命令已写在 verification.md）。
- `failure_kind` 不出现在 SSE 帧里（只在引擎层证明）；熔断"稳态第 3 轮零请求"用注入时钟 + 真实连接计数证明，未做端到端驱动。
- **身份探针未做**：同维度换模型仍会被静默接受（连接测试目前只验 200 + 维度 4096）。
- 车道上限目前是**环境变量**，尚未纳管到配置页。

**影响哪些问题**：① "客户机器上每轮普通提问都红气泡"这一迁移阻塞项解除——注意它**与"甲方能否访问我方模型"无关**，是通用稳健性；② 拿到"地址可由现场运维在页面设置、无需重封发布包"的能力，这是**切阿里云/自建嵌入的前置**；③ 版本归属：**v1.1**（v1 冻结不动，分支待并入）。

## 附轮 · 2026-09-21 · 容器交付路径（对照）：镜像 tar + compose，本机演练通过

> 与第 3 轮（裸机路径）并行的一路：甲方允许装 Docker，所以另做一条**容器形态**对照。
> 详细版见 [容器交付路径](./2026-09-21-customer-site-docker-path.md)，
> 现场 runbook 在 `deploy/docker/README.md`，原始证据在分支 `delivery/docker`
> 的 `.agents/runs/delivery-docker/{current-state.md,verification.md}`。

**做了什么**：冻结交付 v1（`delivery-v1` = `36df47b8`）之上只加交付工具（Dockerfile / compose /
入口脚本 / 验收与 replay 脚本 / 构建脚本 / runbook / `.dockerignore`），**服务代码与冻结参数一行未改**；
冻结命令文件里那些"解析期要求存在"的账本绝对路径在镜像内直接建好（两个真实小文件随镜像 COPY），
代码路径用一条符号链接 `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation -> /opt/mirothinker`
承接 ⇒ 容器内 entrypoint 直接 exec **同一个** `deploy/start-canonical-v2.sh`。

**发现**（四条值得进方案/风险表的）：
1. **只读数据根不会让启动失败** —— 服务侧写 mount-receipt 失败只打 warning，代价是每次启动全量重新哈希
   （原假设"只读会崩"不成立）。
2. **验收门依赖受管配置**：全新首启（`config/managed` 空）时 replay 门 **6/7**，`G1_framing` 第 3 轮
   因答案走降级渲染（首句是 `（以下为基于本地数据的简要信息）`）而失败；把 `/admin` 该配的配上（chat LLM 档）
   即 **7/7** ⇒ 验收前的 P3 配置步骤是门的前置。
3. **uid 不匹配的症状是 `PermissionError` 而非"缺文件"**（本机 Python 3.12.3 下 `Path.is_file()`
   对 EACCES 抛异常）—— 看起来像崩溃，实际是权限；容器入口预检把它翻译成指名路径 + uid 的人话。
4. **构建机容器出网是白名单**（PyPI/GitHub CDN 不在内）⇒ 构建必须 `--network=host`；
   现场不受影响（载镜像即可，不 apt / 不 PyPI / 不 uv sync）。

**怎么验证**（实测数字）：启动 482–486 s（首启/有 receipt/带配置三次一致）；稳态 RSS **17.64 GiB**
（对照活线 17.32 GiB）；`/chat` `/main` `/api/health` 全 200；嵌入探针 **HTTP 200 + 4096 维**；
真实问答 `query_type=A:answer`、6 条引用、575 个流式 chunk、无 error 事件；replay 门 6/7 → 7/7；
镜像 4.30 GiB（tar 4.37 GiB，gzip **1.40 GiB**，`docker load` 实测 21 s）。
活线 pid 519941 全程未动（RSS 18 168 732 → 18 168 708 KiB，未重启），活线数据根的 receipt mtime 仍是 02:12。

**影响哪些问题**：① 交付形态从"一条路"变成"两条可比的路"，选主路径前**必须对齐一件事**：
裸机的 291 s（第 23 轮实测）与本机容器的 486 s 差在哪 —— 需要在同一台机器上背靠背比一次再下结论；
② 容器形态把「现场装环境」整段消灭，但**新增**受管配置丢失、uid/属主、cgroup 内存（无 swap 兜底）、
数据面仍 7 GB、启动相位不变等边界，已逐条写进 runbook §9；
③ 冻结路径契约从"宿主机必须同构"改为"compose 的容器内 target 必须同构"，宿主机放哪儿都行。

## 第 5 轮 · 2026-09-21 · 容器线补完：PostgreSQL 进栈并端到端验收 + **启动耗时归因找到根因并修复**

**做了什么**（分支 `delivery/docker`，本轮 4 个提交：`6216c5d7` `51cac2bb` `0a0988c6` `e802fe25`；主仓与容器线工作区均已干净，无遗留容器，活线 pid 519941 未动）：

- **PostgreSQL 进 compose 栈**：`db` 服务 = `postgres:16`，库名固定 `miroflow_collection_v1`，pgdata 用具名卷 `mirothinker-pgdata`，**不对宿主发布端口**（应急 `127.0.0.1:5432` 以注释保留）；凭据走 `secrets/postgres.env`（0600，不入 git，模板随 kit）；app 入口从 `POSTGRES_*` 组装 `DATABASE_URL`（口令 URL 转义、从不打印）；新增 `migrate.py` 做**幂等迁移**（有界等 PG → `COMMENT ON DATABASE` 写身份标记 → `alembic upgrade head`，失败只降级）；镜像加 `UV_NO_SYNC=1`（作业门里的 `uv run` 才不会联网装 dev 组）。
- **启动耗时归因（原 486 s vs 291 s）**：找到根因并修复，详见下。

**发现（本轮三条，第一条是大鱼）**：

1. **解释器补丁版本会静默让每次启动多花 ≈190 s**。包的 release binding 含 `reader_contract_digest = sha256(python 补丁版本 + pydantic + canonical_v2 源码字节)`；包由 **CPython 3.12.12** 封印，而 Ubuntu 24.04 自带 **3.12.3** ⇒ 摘要不符 ⇒ **每次启动重放重建 ≈190 s（不报错、日志看不出）**。证据链：两侧原始 CPU/JSON/分配/哈希/numpy 完全相同、Chromium 0.5–0.6 s、6 个 provider 主机都通；SIGABRT + faulthandler 抓到卡点在 `serving_pack_loader.py:1021 _canonical_sha256`；把镜像换成托管 CPython 3.12.12 后摘要与包逐字节一致。**这条对两条交付路径都成立**——即使解释器换成未来某个 3.12.13 也会同样变慢。
2. **只读数据根不阻塞启动**（第一轮已验证）：写 mount-receipt 失败只打一行 warning；代价是每次全量重哈希，可用 `CANONICAL_V2_SERVING_RECEIPT_PATH` 指到可写路径规避。
3. **验收门依赖受管配置**：空配置首启 replay 门 6/7（答案走降级渲染），配好 chat LLM 档即 7/7 ⇒ **验收顺序必须是"先配置（P3）再跑门"**。

**怎么验证**（原始数字）：

- **PG 验收全绿**：db healthy 2 s；迁移首次 `{"revision_before":"","revision":"V042","tables":42,"waited_seconds":0.196}`，二次/三次 `revision_before=V042==revision`（**幂等**）；app 日志 `console_database=configured`；登录 200；`/seeds` `/upload` `/jobs` `/admin` 全 200、4 个管理 API 200（`postgres.available=true`）；**真跑一次 preview**：`succeeded`、443 s、`written_profile_count=0`、`diagnostic_profile_count=995`，run 行在 `/jobs` 可见；**`pg_dump` 116,484 B → 灌进 scratch 库 → 42/42 张表行数全等**；`/admin` 面板 `state=ok / freshness=ok`（此前是 `unavailable`）；`down` + `up` 后数据仍在。
- **启动耗时背靠背**（同机、同数据根、热页缓存）：裸机（3.12.12）**275 s** ／ 容器（3.12.3）**466 s** ／ 容器（预编译 18,915 个 pyc，仍 3.12.3）**466 s** ／ **容器（3.12.12）276 s** ✅。⇒ runbook 承诺数字从 486 s 改为 **≈276 s（与裸机同档）**。
- 最终 kit：镜像 `3ad327d3`、tar 5,260,715,520 B `c308d2c2…`、**gz 1,670,300,769 B `a83b6c82…`**。
- **配额**：3 次 preview 触发只有 1 次真抓取（SUSTech 名录 996 次页面抓取）；另两次 1–1.2 s 即结束（`adapter_missing` / `parser_low_quality`，≈0 花费）——其中一次是驱动脚本缺"已有 seed 就跳过"守卫导致的多触发，已记为该脚本的已知粗糙点。

**未验证**：bind-mount 版 pgdata、`--env-file` 分支、物理卷还原、并发压测、下一轮封印（run17）后解释器是否同步。

**影响哪些问题**：① 你要的"PostgreSQL 进容器"落地并端到端验收（采集线在容器形态下可用，含 `pg_dump` 备份路径）；② 主交付形态的**唯一硬缺口（启动耗时未归因）已消除**，容器与裸机同档（276 vs 275 s）；③ 新增一条**跨两条路径的交付要求**：钉死 CPython **3.12.12**（已写入交付方案 §3 前置条件）；④ 裸机线正被派去补"解释器钉版本 + preflight 检查"。

## 第 6 轮 · 2026-09-21 · 解释器补丁版本变成硬检查（裸机路径补齐），并用**真实不匹配**复现了惩罚

**做了什么**（活线树两个提交 `0b70b97c` `b2df6de6`）：

- 新增 `.python-version` = **`3.12.12`**（`uv python pin`）——这正是 `uv sync` / `uv run` 真正读取、决定解释器的那个文件；刻意不动 `requires-python`（它只能表达下限，且会触发锁重解）。`.gitignore` 加否定规则，确保它随 kit 发货。
- `deploy/preflight.sh` 新增 **interpreter contract** 段，三臂检查：① pin 存在且为 `3.12.12`；② **启动解释器**与 pin 一致；③ **reader-contract 摘要与包内记录（`ebc22047…`）一致**（权威那一臂）。版本号全树只出现在 `.python-version` 一处，preflight 内**没有任何版本字面量**。`build-delivery-kit.sh` 的 `site-paths.txt` 增加 `@python-pin` 行。

**发现（真实复现，不是模拟）**：装了一个真的 **CPython 3.12.11**，对同一份 site / 包 / index / 状态目录 / 命令文件启动 ⇒ **426.0 s vs 3.12.12 的 291.0 s（+135 s），日志逐字相同、零报错**。容器侧对照是 +190 s（3.12.3）。方向与机制一致，绝对差随宿主而变。另测"摘要漂移"臂：给 `canonical_v2/__init__.py` 追加一行注释即 FAIL（随后逐字节还原，`326ac3e8…`）。

**怎么验证**：match / mismatch / digest-drift 三臂的原始输出都留了证据（`rehearsal-preflight-interp-{match,mismatch,digest-drift}.txt`、`rehearsal-mismatch-boot.log`、`rehearsal-python-pin-probe.txt`）；kit 重打后 `code.tar` 新 sha256 `5df43c3d…`（含 `.python-version` 与新 preflight 段，本机复核过 tar 内容与摘要）；活线全程未动（`/chat` 200、pid 未变）。

**未验证**：pydantic 那一项只有推理、没有实测；真实的 Ubuntu 3.12.3 没拿到（只弄到 3.12.11）；**systemd drop-in 里设 `UV_PYTHON` 会绕过该检查**（已作为一句规则写进交付方案 §3）。

**影响哪些问题**：把"启动是 291 s 还是 466 s"从一个**运气问题**变成**可检查的交付契约**——两条路径（裸机/容器）现在共用同一个硬检查，且不依赖硬编码版本号。
