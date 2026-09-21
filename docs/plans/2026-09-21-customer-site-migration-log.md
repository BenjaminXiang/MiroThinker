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
