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

## 第 7 轮 · 2026-09-21 · 用户授权"可以动交付包"→ 顺带量清了"代码补丁到底要传多大"

**背景**：用户授权：如果新修复需要动交付包（发布包/数据面），可以动。我原来的顾虑是"动包要重新封印 41 分钟"，所以身份探针刻意做成"不改包"的两臂版。

**核对到的机制（`serving_pack_loader.py:257-281`）**：reader contract digest = `python 补丁版本 + pydantic 版本 + canonical_v2 包内全部 *.py 的字节`。它只决定一件事：**是否跳过重建证明**。digest 相同 → 直接信包；不同 → 启动时**真的重跑重建并与封印记录对账**——这是设计使然，docstring 自己写着"代码与封印代码不同时，重放才证明得了东西"。

**量到的两个事实**：

1. **任何 `canonical_v2/*.py` 改动 ⇒ 每次启动多花 137–190 s**（裸机 291→426、容器 276→466，日志完全相同）。所以我方每次改服务代码，要么重新封印，要么现场每次启动都慢 3 分钟。
2. **重新封印的增量只有一个文件**：对比 `serving-pack-run16-sealed` 与 `serving-pack-run16-readerbound`——`relationships.json`(3.47 G)、`lookup.sqlite3`(896 M)、`institution_catalog.json`、包 marker、索引根 marker **全部逐字节相同**；只有 `manifest.json` 变了（11,116,133 → 11,116,235 B，gz 后 ≈2.5 MB）。serving bundle 只引用 `index_root`/`release_id`/`index_target_id`，不含包文件哈希 ⇒ 不因重封而变。

**结论（已写进交付方案 §8.2）**：**代码补丁 = 代码 tar + 新 `manifest.json`（≈2.5 MB gz）**，不需要重传 1.4 GB 数据面（前提是该次没有重建数据）。这把"代码增量 ≤15 分钟"从一句口号变成了有实测支撑的可执行流程。

**对进行中工作的影响**：身份探针仍按"不改包"的两臂版实现（对甲方现场够用：包内记录的端点地址对他们是可达的）；如果后续要把"参考向量"放进发布包，正好搭下一次重封（v1.1 因代码改动本来就要重封一次）。

**未验证**：下一次封印（run17 或 v1.1 重封）时"只变 manifest"是否仍然成立（数据不变的前提下应成立，但需实测复核）。

## 第 8 轮 · 2026-09-21 · 换 embedding 模型可行性探针（**结论：必须重建**）+ 一键安装器交付

### 一、换模型探针（用户给的候选：`qwen3.7-text-embedding-flash`）

用同一条探针串打了三方，**实测**：

| 项 | 结果 |
|---|---|
| 新端点默认维度 | **1024**（延迟 0.28 s） |
| 请求 `dimension: 4096` | **HTTP 400**（不支持） |
| 我方参考（Qwen3-Embedding-8B） | **4096** 维，0.05 s |
| Matryoshka 截断假设（我方前 1024 维归一 vs 新模型） | cosine **-0.03** ⇒ **近似正交，完全不同空间** |

**结论**：换成这个模型**不是"改地址"，而是换掉整个索引的向量空间** ⇒ 必须**全量重建**（51k 文档重嵌 + 新矩阵 + 新包 + 重新封印 + 数据面重传）。对比之下，"同模型换端点"（例如自部署的 Qwen3-Embedding-8B）才是零重建、只改地址。

**新发现的一条硬阻塞**：该入口是 **DashScope 原生形状**（`input: {texts: [...]}`，响应 `output.embeddings[].embedding`），而我们的构建期与服务期客户端是 **OpenAI 兼容形状**（`company/vectorizer.py:47-56`：`POST {base}/embeddings`，body `{"input": [...], "model": ...}`，响应 `data[].embedding`）。⇒ 换模型前必须先解决：要么该网关提供 OpenAI 兼容路径，要么写一个薄适配层。

**迁移清单（六项，按序）**：① 端点形状适配（代码面，半天）→ ② 身份三件套改动（新 bundle：`model_id`/`dimension=1024`/`base_url` + 重算 `content_sha256` + 更新 `_QWEN_EMBEDDING_BUNDLE_SHA256`/`_QWEN_EMBEDDING_DIMENSION`，`knowledge_build_isolated.py:266-275`）→ ③ 全量重建 8 h（嵌入本身受 TPM 1M 限制约 10–20 分钟，8 小时是其余流水线）→ ④ **质量重验**（replay 门 7/7 + 语义类 g2/g5/g7 + 泛化命中率；**这关不过就不该换**）→ ⑤ 凭据与合规（key 走受管密钥页；该域名是第三方网关，需确认数据留存/稳定性；**用户贴出的 key 需轮换**）→ ⑥ 顺带收益：索引小 4 倍（1.68 GB → ~420 MB）、数据面传输件大幅变小；代价是每轮查询 +0.28 s 远端延迟。

**排期建议**：不阻塞 v1.1 发车；换模型单列 v2（先做 ①+②，再重建与质量对比，最后用 F2 + 身份探针切换；回滚 = 换回旧包与旧 bundle）。

### 二、一键安装器交付（容器线）

- **产物**：`deploy/docker/{build-site-bundle.sh, install-site.sh}`（提交 `59ccc3bc` `aa406a4f`）；bundle 在 `/var/tmp/mirothinker-site-bundle/`（15 文件、3.0 GB，其中 13 个硬链接）。
- **八步安装**：预检 → 两归档 sha256 → 解包到冻结宿主路径 → 十件校验 → 状态目录 0700 → `docker load` → 写 `.env`/PG 凭据/密钥检查（缺则 exit 12 且**不起半配置的栈**）→ `compose up -d` + 有界健康等待 → `verify` → 打印入口与口令路径。退出码 0/2/10/11/12/13/14，支持 `--dry-run/--fast/--no-up` 等。
- **冷装演练**（端口 18296）：校验 19 s → 解包 44 s → 十件 40 s → load 23 s → 首启 **459 s**（冷数据面）→ verify 全通；**到"装完"合计约 11 分钟**；幂等重跑 22 ok；**第二启 289 s**（对上裸机 275 s / 容器热态 276 s）。
- **顺手修掉两个真 bug**：磁盘检查算在前缀路径上误报"可用 0 GB"；幂等重跑把"本栈自身占用的端口"当冲突。
- **未验证**：跨文件系统传送后的完整链路、以真正 root（sudo）跑一遍、`--strict-probes` 失败分支、bind-mount 版 pgdata、PG 物理卷还原、首启 459 s 的冷热拆分量。

## 第 9 轮 · 2026-09-21 · 口径修正：甲方"只填 key"的**主路径是配置页面**，不是密钥文件

**用户指正**：`/admin` 配置页面已经能填密钥（`config-center-secrets-and-tests` 已上线并验收：掩码回显、原子写 0600、审计不含明文、先测后存），甲方直接在里面填新 key 就行——不需要让他们碰文件。

**修正后的口径（三条）**：

1. **文档主路径 = 配置页面**：`CONFIG-GUIDE.md` 里"密钥"一节以页面为主（4 个 key 各自从哪来、在页面上填哪一格、填完点连测、重启生效）；密钥文件降级为"首启前/无页面时的等价手段"。
2. **首次启动前的空档要靠安装器补**：服务没起来就没有页面、也没有账号。所以把安装器改成**交互式提示输入 4 个 key**（只输入值，路径与权限由安装器处理）⇒ 甲方从安装到运行**全程只输入 key**，不碰任何文件路径。
3. **页面不能被填的东西（边界，必须写明）**：页面上可填/可改的是**凭证**与**同模型下的端点地址**（v1.1 的 F2，带连测 + 身份探针守卫）；**模型身份（model id + 维度）不在页面可改范围**——这是防止"不同模型的向量被静默塞进同一个矩阵"。所以换不同模型（如 1024 维候选）必须先由我方交付带新身份的版本，之后甲方在页面填该服务的 key 即可。

**待你拍的一个小项**：端点/模型行是**只读**（减少误操作面，只留 key 可填）还是**受守卫可编辑**（连测 + 身份探针通过才允许保存）。倾向后者——将来甲方可能自己托管嵌入服务。

**影响哪些问题**：① 甲方上手成本从"看路径放文件"降到"在页面上贴 key"；② 安装器增加交互式输入（小改动，待排）；③ 换模型的边界被写清楚，避免甲方自行改模型导致静默错排。

## 第 10 轮 · 2026-09-21 · 召回回归 harness + **基线已冻结**（换模型的度量尺就位）

**交付**（分支 `feat/recall-regression`，4 个提交；`apps/admin-console/scripts/eval_recall_canonical_v2.py` 1030 行 + 19 个自洽测试 + 三份 case 集 + scratch 启动器）：

- `testset-cases.json`：测试集 25 轮 / 17 组，人工复核实体 GT（18 有标注 / 5 概念 / 6 无标注 / 1 禁项）；
- `semantic-probes.json`：12 条向量道探针（4 有标注、8 结构性）；
- `--diff A B` 直接按方案 §4.4 出判定行与退出码（`0 PASS / 1 FAIL / 2 REVIEW`）；对基线自比 → **PASS**（自洽性验过）。

**基线（已冻结，sha256 `7af37a34…`）**——用真实包/索引经 scratch 18295 跑，活线 18188 全程未动：

| 指标 | 数值 |
|---|---|
| 轮次 | **37/37 成功，0 错误，698.7 s** |
| 实体断言 | 37 条：答案/引用命中 **31**、候选层命中 **22**、全命中 **20** 例 |
| 向量道候选数 | 中位 **61.0**（n=34；3 轮本就不规划向量道），分布**双峰** {1×1, 16×15, 58×1, 64×2, 128×15} |
| 引用 | 本地 **239** / 网络 **80**；35/37 为 `llm_synthesized` |
| 已知缺口（记下避免误算） | **6 条断言在基线就未命中**：`q12t1`（遥操作/动捕数据/真机实测）、`q16t1`（关键点措辞≠答案措辞）、`s09`（爱博合创——**真实既有缺口**：类目探针点不到它，尽管 `q10t1` 点名召回得到）；禁项检查干净 |
| 配额 | 网络检索 **323 次** + 40 次缓存；LLM **下界 ≈72 次**（服务侧无用量账本，精确值需看网关面板） |

**子代理自己标出的缺口（我采纳为待办）**：

1. **没有噪声底**（最大缺口）：只跑了一遍，所以单次"命中→未命中"无法归因 ⇒ **必须补一次同配置对照跑**（已派同一人去做，并要它给出"哪些用例自身会翻、向量中位数的run-to-run 波动有多大、默认严格判"概念类"是否站得住"）。
2. 概念类默认严格（`--lenient-concepts` 可放宽）——待对照跑数据后定。
3. 服务只流式给计数、不回 ranked top-k ⇒ §4.4.2 的"掉出 top-k"实际实现为"从召回候选集合里消失"（抓得住丢失，抓不住名次移动）。
4. 向量候选数双峰 ⇒ 中位数是粗粒度跳闸线，**读用例列优先**。
5. 不覆盖：答案质量/精度、replay 门、多轮指代、时延、新索引身份（属重建片）。
6. 6 条无标注用例只能人工复核（`q7t1`、`q14t1` 价值最高）。

**影响哪些问题**：① 换模型的阻塞门现在**可执行**（同一命令跑两遍 + `--diff` 出判定）；② 基线与 6 条既有缺口被冻结，将来不会把"本来就差"算成"换坏了"；③ 下一步就是对照跑（噪声底）→ 端点适配 + 新 bundle → 重建 → 复测。

## 第 11 轮 · 2026-09-21 · 三条遗留收口：身份校验（含一个真 bug）、等待上限进配置页、构建套件对比

**#3 嵌入端点身份校验（最重要）**：装在**运维改地址时站的那张卡**上，两臂：
- **对照端点臂（优先）**：固定探针在"发布包记录的地址"与"配置地址"各嵌一次，cos ≥ **0.999**；
- **索引臂（记录端点不可达或就是它自己时）**：从服务包取一篇文档原文，用配置端点嵌入，与索引为它存的向量比对，cos ≥ **0.99**，并在 798 行抽样里确认"它仍是自己的最近邻"。

**真实数据标定**（生产 `verify_embedding_identity`，活线资产）：同空间 **1.000000 / 0.999933** 通过；不同空间 **-0.007435 / 0.004543** 拒绝——阈值与两侧都留约千倍间隔；15/15 次重复实测恰好 1.0。失败文案直接说"不要切换到这个端点，换来的排序会整体失真"；跑不了时明确显示"未校验"，**从不假通过**。发布包一字未改（不重封）。

**标定过程中抓到并修掉一个真 bug**：手写读取 `vector_matrix.npz` 的行**必须按 `.npy` 头偏移**；否则读到"看着合理但完全错"的行（cos ≈0.02），会把**正确端点误判成不同空间**。已修并用与 `np.load` 对齐的测试钉死。阈值标定这件事本身把这个 bug 暴露出来了。

**#2 向量道等待上限进受管配置**：`serving.vector_lane_timeout_seconds`（默认 8 s、边界 0.1–120、页面可见可改、启动投影进环境、**读取点仍只有一处**、8.0 兜底被测试钉到 schema 默认值）；越界保存被拒并点名字段。12 个新测试 + 受管配置面 138 通过。

**#1 构建套件基线对比**：`test_knowledge_build_isolated.py` 不是卡住而是**慢**（单个测试 9 分钟）。两侧各覆盖同样测试：1–128 号 **14 failed / 114 passed，失败集合逐字节相同**（那 14 个是本机 Postgres/boundary 既有红）；129–131 号两侧各 3 passed。**尾部 12 个未对比**（每个约 10 分钟，配对约 4 小时）——已量化残余风险：那 12 个属 store-replay / 企业回填 / 申请人绑定族，**不 import 本次改动的模块**，命令与风险写在 `verification.md` §⑤。

**回归**：admin 全量套件失败集合与基线**逐字节一致**（25 failed / 105 errors；1519 vs 1481 通过 = 新增 38 个通过）。

**它报的一条信号，我核查后澄清**：报告称活线命令上出现第三个进程。实测——**18188 只有一个监听者**（pid 519941，`/chat` 与 `/api/health` 均 200），第三个进程是**召回对照跑的 scratch 实例**（20:46 起，监听 18295，命令行同源所以看起来像）。**不是事故**。

**新增一条待办（v1.1 集成时处理）**：索引臂需要 `CANONICAL_V2_SERVING_PACK`（受管字段 `paths.serving_pack_dir`），而现役服务单元没有设置它 ⇒ **客户机上索引臂会显示"未校验"**（对照端点臂不受影响）。建议把这一项加进部署命令/compose 环境。

**未验证**：本机没有真实的第二个嵌入模型（用仓库自带 token-hash 4096 维假端点代替——协议对、维度对、空间错，正是要拒的失败形状，但不能排除"某个真实模型恰好 >0.99"；对照端点臂覆盖这种情况）；未在真实服务进程里跑过该探针；未做浏览器渲染验证。

## 第 12 轮 · 2026-09-21 · 甲方配置指南交付 + "只填 key"**实测通过**（含一条差点踩中的降级陷阱）

**交付**（容器线，2 个提交 `5220d2d5` `a0cd5c13`）：

- `deploy/docker/CONFIG-GUIDE.md`（165 行中文，写给甲方运维）：一句话结论 / 4 个密钥清单表（谁申请·放哪·**不填会怎样**）/ 页面等效填法 / 页面唯一要用的配置 / **不要动的东西 + 报错原文** / 症状→原因→动作表 / 网络前提 / 验收三步；
- `deploy/docker/site-config/managed-settings.json`（**预置受管配置**：chat LLM 档位、端点、采集窗口、四域开关——非机密）；
- `README-FIRST.txt` 与 runbook §13 互链；交付包已重建。

**关键发现（差点让甲方拿到降级答案）**：代码里 `CHAT_LLM_PROFILE` 的**默认是 `gemma4`**（`knowledge_serving_isolated.py:2140`）——**光放 `.deepseek_api_key` 不够**，必须由我们把档位预置成 `deepseekv4flash`。这正是新增的 `managed-settings.json` 的作用；没有它，客户现场会得到"模板化答案"而不是大模型成文。

**"只填 key"实测（两阶段，冷 scratch、端口 18296、无 sudo）**：

| | 阶段 1（3 个 key，缺 `.deepseek_api_key`） | 阶段 2（**只补那 1 个 key**） |
|---|---|---|
| 安装 | 21 ok / 5 warn / **0 FAIL**、`boot=284 s`、verify 全通 | — |
| 嵌入连接测试（= 页面点一次"测试"） | `ok:true`、HTTP 200、33 ms、`model=Qwen/Qwen3-Embedding-8B`、来源标注齐全 | 同左 |
| `/chat` 真实问题 | 8 条引用（本地 1）、**`degraded_template=true`** | 8 条引用、**`degraded_template=false`**（576 字成文） |
| replay 门 | **6/7** | **ALL PASS 7/7** |

**确切的"人工输入清单"**（除此之外没有任何编辑/填地址/建库/改路径）：① 4 条 `sudo install -m 600 /dev/stdin secrets/.<name> <<< "<key>"`；② 一行 `sudo ./install-site.sh`；③ 后补 key 时一行 `docker compose up -d --force-recreate app`；④ 浏览器 `/main` 登录改密 + `/admin` 点一次"测试"。⇒ **与"只填 key"无偏差**。

**演练修掉两个真 bug**：① docker 会在缺失的 bind 源处**建同名目录**（导致"后补 key"无法覆盖，且旧校验把目录当"已配置"**假绿**）⇒ compose 加 `create_host_path: false` + 安装器识别清理 + 空 0600 占位；② **换 key 只 `restart` 不够**（bind 绑的是 inode，覆盖写会换 inode）⇒ 指南直接给 `--force-recreate`。

**未验证**：`--force-recreate` 那条是从 inode 语义**推断**、未做反向实验；页面上"手填 key"只验到运行时凭据解析与连接测试，**没有在浏览器里真提交一次表单**；真 root（sudo）下的安装；跨文件系统传送后的链路。
**另注**：`mount-receipt.json` 在 20:50 被重写**不是它**——是同一时段另一个 agent 的 scratch 实例（pid 1231373，20:41 起）读同一数据根所致；活线服务未动（pid 519941、`/chat` 200）。

## 第 13 轮 · 2026-09-21 · 召回门的**噪声底**：按字面规则会对噪声喊狼来了 → 已按实测重标定

**做了什么**：同配置再跑一遍（各 37 轮、同包同索引同 case 序、只换 label 与输出路径），得到 `control.json`（sha256 `54a695ac…`），并据此标定判定规则（方案 §4.4 已改写）。

**关键数字（两跑对比）**：

| | 基线 | 对照 |
|---|---|---|
| 答案层实体命中 | 31/37 | 31/37 |
| 候选层命中 | 22/37 | **29/37** |
| **向量道候选数中位数** | **61.0** | **61.0**（**0/34 用例变化**） |
| 引用（本地/网络） | 239/80 | 228/128 |
| 网络检索调用 / 缓存命中 | 323 / 40 | **94 / 260** |
| **网络 provider 超时** | **17** | **0** |

**发现（本轮最重要的一条）**：**按方案字面规则（任何一轮命中→未命中即失败），两次相同配置的运行之间就已经 FAIL**——翻的是 3 条**概念类**断言（如 `q15t1` 丢"物理仿真引擎生成/生成式模型生成/基于规则生成"）。根因逐字查清：**基线那次是"网络道降级跑"**（冷缓存、17 次超时、网络候选为空），对照组热缓存、0 次超时、104 条网络候选 ⇒ 答案随之变化。
⇒ 这不是召回退化，是**网络检索的天气**。而**换模型真正会动的指标（向量道）零噪声**。

**重标定后的规则（已实现进 harness）**：有标注实体"候选+答案同时消失"才是 **FAIL**；只丢答案层 / 只丢候选层 / 概念类 / 探针 GT 丢失 / 单用例向量候选掉 >50%（**新增 ≥8 下限**）⇒ **REVIEW**；**中位数掉 >30% 保持 FAIL**（零噪声，不会误报）；概念字符串从候选层计分里移出。判定行带 `[web timeouts=n]` 与网络道锚列。

**降低噪声的便宜办法**：**换后跑两遍、只看第二遍**（第一遍热缓存：94 vs 323 次实时调用、超时 0 vs 17）——"有标注实体 0 翻转"正是在热缓存条件下验证的。

**配额**：对照跑 **94 次**实时网络调用（bocha/serper 各 47）、0 超时、489.8 s；整个链条该 scratch 实例今日 **bocha 220 / serper 218 = 438**（含基线 323 与约 21 次冒烟/中断）。LLM 仍不可观测（下界 ≈72 次/跑）。

**未验证**：冷缓存下的答案层地板（对照跑的网络证据大量来自基线的缓存）；换向之后的任何结论；n=1 之外的第二条对照（再做一次约 94 次调用）。

**影响哪些问题**：① 召回门从"会误报"变成"可执行"——**没有这一步，换模型后大概率会因为网络天气而被误判为退化**；② 基线那份"网络降级跑"的事实被记进协议（`protocol.md` §5），换后复测必须用同一协议（跑两遍看第二遍）；③ 方案 §4.4 已同步为标定后的规则。

## 第 14 轮 · 2026-09-21 · v1.1 切片 A 完成：三合一 + 重封 42.08 min；**"只有 manifest 变"成立**

**合并**：三个分支**无冲突**合并（路径不相交，`deploy/README.md` 等预期冲突没发生），并有 `union-check.py` 证明"合并树 = 三个分支的并集"（每个改动路径都属某分支、blob 相等、无冲突标记、无删除）。服务路径文件动了 12 个（全部来自 F1/F2）。

**测试（前后对比）**：

| 套件 | 合并后 | 基线 `36df47b8` | 判定 |
|---|---|---|---|
| admin-console 全量 | 25F / 105E / **1543 passed** | 25F / 105E / 1481 passed | 失败集合 **130 条逐字节一致**（+62 通过 = 分支新测试） |
| miroflow-agent 定向 | 2F / 375P | 2F / 346P | 同一批既有红（+29 通过） |
| ruff（29 个改动 .py） | 2 错 | 2 错 | **均既有、0 新增** |

**重封**：用**官方 sealer**（`s12c/build_serving_pack.py`），不是一次性的 `s12g/reseal_serving_pack.py`（理由：round-23 记录称一次性工具"不是本次路径"，且本次相位集合与官方 sealer 完全一致）。总 **2524.6 s = 42.08 min**（上次 41.41 min，逐相位差 <4%）：`envelope_validate` 2024.1 · `index_snapshot_verify` 11.2 · `index_artifacts_copied` 1.7 · `authority_documents_written` 178.7 · `manifest_written` 5.5 · `dogfood_open` 303.5。

- 新包：`/var/tmp/mirothinker-data-v2/serving-pack-run16-v11`（4.28 GB）
- 新 `manifest.json` sha256 **`588fdd9e…`**；新 `reader_contract_sha256` **`79e7492b…`**（与合并树独立算出的值一致）
- **快路径验证**（每次新进程）：新包 + 收据 → 打开 **119.9 s**（跳过重放）；把**现役包**挂在 v1.1 代码下 → **284.4 s**（重放）；两者内容一致（47,068 文档 / 51,026 点 / 关系 sha 相同），且重放**复现了它记录的请求哈希、无完整性错误** ⇒ 这是**读侧等价性**证据，不只是结构 diff。

**增量证明（决定甲方更新要传多大）**：**"只有 manifest 变"成立** —— `relationships.json`(3,477,354,956 B)、`lookup.sqlite3`(896,270,336 B)、`institution_catalog.json`、两个 marker **sha256 与现役包完全相同**；只有 `manifest.json` 不同（11,116,235 → 11,116,227 B），且内部只有三个字段变（`generated_at`、`generator_run_id`、`reader_contract_sha256`）。⇒ **甲方更新 = 一个 11.1 MB 的 manifest**，不是 4.28 GB 的包。

**未验证 / 待复核**：① **没有做启动级端到端**（没绑端口，活线未动）⇒ 切换前必须用 scratch 实例跑一次 replay 门（切片 B 的演练会覆盖）；② `test_knowledge_build_isolated.py` 未重跑（继承缺口）；③ 容器镜像与站点包仍基于 `36df47b8` ⇒ **v1.1 的交付包必须重建**（切片 B）；④ 新包收据现在记为 `verification: "receipt"`（无害）；⑤ 下一轮可用更便宜的重封路径（`s12g/reseal_serving_pack.py` 逐字拷贝 + 只改 manifest，可省 33.7 分钟的信封校验）。

**影响**：v1.1 的"代码身份 + 数据身份"齐了，且更新成本从 GB 级降到 **11 MB 级**；切片 B 只剩"重建镜像/数据件 + 冷装演练 + 重开下载"。

## 第 15 轮 · 2026-09-21 · 换模型切片 1 完成（**惰性**）：网关存在 OpenAI 兼容路由 + 适配层已备好

**关键探测（无需 key，用状态码区分"无路由"与"需鉴权"）**：

| 路径 | 状态 | 结论 |
|---|---|---|
| `/v1/embeddings` | **404** | 无此路由 |
| `/compatible-mode/v1/embeddings` | **401**（"No API-key provided"） | **路由存在**（与官方 DashScope 同前缀） |
| `/api/v1/services/embeddings/text-embedding/text-embedding` | 401（InvalidApiKey） | 原生路由存在 |
| `/compatible-mode/v1/models` | 401（OpenAI 形状错误体） | 兼容面存在 |

⇒ **该网关确实提供 OpenAI 兼容入口**。如果它在那里服务 flash 模型，切换就退化成"改 provider + base_url"，**零新代码**——一次带鉴权的调用即可定论，这是切换切片要做的第一件事。

**同时把适配层也做好了（惰性，什么都没切换）**：

- 新增 `providers/dashscope_embeddings.py`：请求 `input.texts`、响应按 `text_index` 回位（顺序不对/行数不对/空向量 ⇒ `ValueError`＝"答案不可用"，不是传输故障）；错误分类与 F1 契约定相同（超时→`TimeoutError`、非 2xx/拒连/非 JSON→`ConnectionError`）。
- **按 bundle 的 `provider` 字段选择实现**，把批处理/缓存/去重/向量校验抽成共享核心 ⇒ OpenAI 路径行为逐字节不变，流水线不分叉。
- **凭据槽隔离**：候选模型的 key 走 `CANONICAL_V2_EMBEDDING_API_KEY`，**永不** `load_local_api_key()` ⇒ 本地端点的 key 不可能被带去第三方（构造上保证 + 测试）。
- 新身份：`...flash-embedding-bundle-v1.json`（1024 维、`provider=dashscope-native`、`content_sha256 cdddcdfd…`）+ `_QWEN_FLASH_*` 常量入授权集；**配对不匹配在三层 fail-closed**（包授权 / 索引矩阵 / 校验适配器），每种都有测试——包括"**新 bundle 配旧索引**"这种最容易犯的形状。

**测试**：新增 31+1 全绿；四文件回归在 `-n 2` 下 **89 passed**（`-n 8` 会因 milvus-lite 既有问题抖动，与本改动无关）；`test_knowledge_build_isolated.py` 全量在本机**两棵树**上都跑不到汇总（`test_real_boundary_*` 家族卡在不可达的数据库，属既有红）。

**遗留（交给切换切片）**：① **先试兼容路由**（一次带鉴权调用，可能省掉整个适配层）；② 切换本身**需要一份 OpenSpec change**（本切片惰性、无行为变更，故未立）；③ **凭据接线**：受管密钥页的 `embedding.api_key` 目前写的是 `SGLANG_API_KEY`，候选模型需要 `CANONICAL_V2_EMBEDDING_API_KEY` 这条槽；④ **两处合并交互**：F1 的透传、F2 的 `base_url` 排除与 `resolve_embedding_base_url`，合并时必须同样应用到 `dashscope-native` 分支，否则候选包会"钉住主机"而现役包可配。

## 第 16 轮 · 2026-09-21 · v1.1 出包完成并演练通过（含一个"不加就起不来"的发现）

**交付件**（`delivery/docker` 三个提交，工作区干净）：

| 件 | 路径 / 尺寸 / sha256 |
|---|---|
| 镜像 | `mirothinker-serving:v1.1`（6.82 GB；tar 6.95 GB；**gz 2.16 GB**，`f842f6de…`；构建 144 s） |
| 数据面 | `serving-data-v1.1.tar.gz` **1,481,979,537 B**（10 条目 = 新包 5 + 索引 3 + 2 目录，无 receipt；打包 9 s），`beb9449d…` |
| 校验清单 | `/var/tmp/mirothinker-delivery-kit-v1.1/`（10 件 checksums + sizes + 两个发布 bundle） |
| **可发交付包** | **`/var/tmp/mirothinker-site-bundle-v11/`（3.4 GB，17 文件）** |

**演练**（scratch 根 + 端口 18296 + 无 sudo，两轮：首轮与"最终包本体"复核轮）：校验 21 s / 解包 44 s / 10 件 41 s / `docker load` 30 s；`mirothinker-verify` **0 FAIL**；**replay 门 6/7（空配置）→ 7/7（预置配置）**；`pg_dump`→恢复 **42/42 表**；turn-trace 写失败 **0 次**（修复后）。

**身份校验两态都验到了**：空受管配置 → `arm=null`「未校验：未配置服务包目录」；**预置配置 → `arm=index, passed=true, cosine=0.999933`（阈值 0.99）** ⇒ 我们补的 `CANONICAL_V2_SERVING_PACK` 接线生效、"索引臂"真的跑起来了。

**启动耗时口径（重要）**：**首装冷启 433–503 s（7–8.5 分钟）**；**热重启 288 s**。差异已归因：无 receipt 的首次全量校验 + 索引投影（205→243 s）与冷读相位（关系图 37.5→40.9 s、lookup 16.1→23.6 s），即机器负载/页缓存方差。**"≈276 s"那个数是热重启口径**，交付说明里必须写清"首装 8–9 分钟、之后重启 ≈5 分钟"。

**v1.1 接线是"三处"不是两处，第三处不加就起不来**：① 冻结命令文件（只换 1 token，构建期断言；容器内 cmdline 实测指向新包）；② 受管字段 `paths.serving_pack_dir`（身份校验从"未校验"变 index 臂通过）；③ **镜像入口脚本 `/usr/local/bin/mirothinker-entrypoint` 把旧包名写死** ⇒ 实测 `预检失败：缺少 …serving-pack-run16-readerbound`、容器 **exit 78**；已用 `entrypoint-v11.sh` 只读覆盖修复（全盘 grep 确认启动路径上只有这两处硬编码）。顺带修掉 `TURN_TRACE_DIR`（代码默认相对路径 `var/turn-trace`，容器 cwd 不可写 ⇒ **每轮 PermissionError，v1 时代就存在**）。

**未能验证 / 与期望不符（如实）**：① **sudo / 真实路径安装未测**（无 sudo，用 scratch 前缀），目标机首次实装仍需一次真人演练；② 未跑单测/CI（本片只改 shell/compose/探针）；③ **首启全量校验路径刷 47,087 行 `PydanticSerializationUnexpectedValue(Expected PathEligibilityRequest)` 警告**——产品侧缺陷，未修（要改代码 + 重建镜像），列为后续小项（与"日志降噪"合并）；④ `README.md` 仍是 v1 叙述（v1.1 差异写在 `README-FIRST.txt`/`BUNDLE-MANIFEST.txt`）；⑤ `kit-manifest.txt` 里 `data_plane_not_included` 行仍写旧包名（未重生成，已在 BUNDLE-MANIFEST 说明）；⑥ 演练密钥是符号链接且 664 ⇒ 安装器告警（正式交付要求 0600）。

**客户上传前复核（6 条，已写进交付包）**：传 `-v11` 全目录（3.4 GB，`secrets/` 里放 4 个 0600 密钥）→ 传后 `sha256sum -c` 两个 `.sha256` → 确认 `serve-command-v11.sh` 与可执行的 `entrypoint-v11.sh` 在位 → `sudo ./install-site.sh --dry-run` 先看 → 目标机 ≥64 GB 内存 / ≥25 GB 盘 / 18188 空闲 / 能出网 → 装完 `/admin` 只需补密钥（端点与档位已预置）。

**影响**：v1.1 交付包**可发**；启动耗时的现场口径被纠正（首装 7–8.5 分钟）；两处硬编码旧包名与 turn-trace 权限这两个"只在真装时才暴露"的缺陷已在包内修掉。

## 第 17 轮 · 2026-09-21 · 换模型：预重建门全部关闭，**预检 READY（OK=42 / WARN=0 / FAIL=0）**

**批量上限（两条路由一致，实测）**：`25 → 200`（25 行、index 完整、1024 维）；**`26 → 400`**（"should not be larger than 25"）；`32 → 400`。两个候选 bundle 按 **25** 重冻：

| bundle | 新 `content_sha256` |
|---|---|
| 原生 | `81a536916053106114aa4c70ff43983bf6a12c8ecb0b5c562b43f9f02409b46a` |
| **兼容（推荐路线）** | `2db8f03b255e138a13081566c6196db06d7af1a8a83c12cec2cbfaea00b22e3d` |

常量与两个冻结文档同步更新，**现役授权（32）未动**；新测试把"声明的批量"钉到实测上限。选 25 而非 16 的理由：重建是 **token-bound（TPM 1M）而非请求数 bound**。

**更长噪声采样（5 种文本 × 60 次 = 8,850 对，0 错误）确认 0.99 阈值稳**：

- pooled **min 0.998002**；**没有任何一对低于 0.9985 / 0.998 / 0.9975 / 0.995 / 0.99**；
- 余量 **0.008002 = 整个观测跨度的 4.0 倍**（按四轮 ~10.5k 对的历史最低 0.997556 算 3.8 倍）；
- 分布**离散、随文本而异**（每种文本的配对只取 2–4 个确切值）⇒ 阈值必须从**最小值**推；
- 对照：**跨路由最高 0.9594**（新上界）⇒ 0.99 仍留 **0.031** 间隔（≈噪声到阈值距离的 26 倍）；不同文本 0.2366–0.2434；512 维重复最小 0.998790。

**预检与 switch-line 就位**：预检脚本两个旧哈希换成新哈希、批探针 32→25；新建 `switch-line` worktree（分支 `switch/embedding-model-to-qwen37-flash` @ `a5c276a3`，含 v1.1 合并）。

**复跑 `precheck.sh --full` → `OK=42 WARN=0 FAIL=0 RESULT: READY`**（76 s 量级），覆盖：8.3 GB 信封哈希与路径、解释器对（3.12.12 + pydantic 2.12.5）、两个候选 bundle 自哈希、凭据槽、**回滚锚点**（包 marker / lookup 尺寸 / mount receipt / 索引 marker / 4096 矩阵 / 现役启动命令）、构建库连接与 alembic、磁盘、**召回门 7 项冻结物 sha256**、端点带鉴权探测（200 / 1024 维 / 0.229 s）。

**唯一未跑的**：`--batch-probe`（可选的一次额外调用；25 已被直接实测过两次）。

**下一步（只差一句话）**：用户确认用哪个运营方 —— (a) 就用该网关（立刻启动 7–9 h 窗口）；(b) 官方百炼端点（先换 base_url 重冻，约 15 分钟）；(c) **同模型自部署（不重建，当场结束）**。

## 第 18 轮 · 2026-09-22 · 模型与用法拍板（flash@1024 + 原生路由 text_type）、B 方案落地并启动构建

**用户拍板**：模型选 **`qwen3.7-text-embedding-flash` @ 1024 维**；用法选 **B（原生路由 + 查询侧 `text_type`/`instruct`）**。

**决策依据（实测，全部我用带鉴权调用量过）**：

| 事实 | 数据 |
|---|---|
| 非 flash 支持的维度 | 1024 / 1536 / 2048 / 2560（4096 → 400） |
| flash 支持的维度 | 只到 1024，且**请求 2048 会静默返回 1024**（不报错）⇒ 维度必须写进身份并由校验拦住 |
| **两者是否同空间** | **否**：同文本余弦 0.042 / 0.017 / −0.061 ⇒ **选定即绑定，事后换＝再来一次 8 小时** |
| 批量上限 | 文档写 20；实测 flash 放行到 25（26 → 400）、非 flash 恰好 20 ⇒ **按文档声明 20**（防服务方某天收紧到文档值，那时声明 25 会让每轮调用 400 → 静默降质） |
| 官方文档揭示 | **`text_type`(query/document) 与 `instruct` 仅原生接口支持**；文档明说"短文本匹配长文本时应区分 query 和 document"（正是我们的场景）⇒ 这是选 B 的理由 |

**B 方案落地（switch-line `ac44b404`，17 文件）**：

- bundle 新增并**冻结** `query_text_type: "query"` + `query_instruct`（英文、场景化）；`batch_size 25 → 20`；重算哈希（原生 `67927ea0…`、兼容 `d5ff0ffb…`）。
- **角色贯通**：`load_content_addressed_embedding_adapter(path, *, role)` 必填；`_BatchingEmbeddingAdapter.role` 受校验；原生适配器**仅在 role=query 时**发那两个参数（有测试钉死"document 角色发不出 query 形状"）。构建侧=document、服务侧=query。
- **身份校验的两个臂分开角色**：索引臂=document（它重嵌的是包里存的文档向量）、参考臂=query ✓（这是 B 引入后最容易误报的地方，已处理并有测试）。
- 测试：`test_embedding_model_switch_v2.py` **62 passed**（+5 新）；身份校验 **28 passed**；**预检 `--full` → OK=42 WARN=0 FAIL=0 READY**。

**实测"参数是否真的生效"（B 有没有意义的关键）**：同一文本 query 角色（含 instruct）vs document 角色 → **余弦 0.912177**，而该车道**自身重复 = 1.0** ⇒ **参数确实生效且远超噪声**，B 买到了真实的查询侧处理。

**执行判断（采纳子代理的建议）**：`git apply --check` 通过 ≠ 构建线能跑——那棵树还缺 4 处 `role=` 调用点，且**其 runner 拒绝 run16 那个固定信封路径**（被 8.3 GB 回滚锚点占着）⇒ **从 switch-line 启动**（自带 runner/sealer/gate root 与新代码），移植 patch 降为**文档化退路**。

**已启动**：从 switch-line 按 runbook 步 0–5 启动构建（detached、原生路由、batch 20），并盯 30–45 分钟的两个"窗口杀手"（每批 400 / 向量审计假失败）。

**新增遗留（不阻塞本次）**：① 管理页的**身份校验卡验不了原生路由**（只讲 OpenAI 形状 → 对 `/api/v1` 得 404 → 显示"未校验"，**从不假通过**）；要补就把 DashScope 客户端接进那张卡。② 服务方若把上限收紧到 **低于** 20，需再次重冻。③ 若哪天启用兼容孪生端点，查询会**丢掉**这两个参数（且向量不同源）——"只用一条路由"仍是硬规则。

## 第 19 轮 · 2026-09-22 · 构建确证在跑（两个窗口杀手用证据排除、`src` 树陷阱记档）；遗留"车道超时纳管"核对为已关闭

**做了什么**：不看子代理的转述，独立核对构建进程本身（cmdline / environ / 启动脚本 / bundle / 日志 / 取样器）；把用户点名的遗留项逐条**拿到代码里**核对，而不是核对计划文本。

**发现**：

1. **`src` 树陷阱（第一次发射 12 秒即死）** — 报错 `TypeError: load_content_addressed_embedding_adapter() got an unexpected keyword argument 'role'`。根因：部署 venv 把 `src` 以 editable 装在**活线树**上（`_editable_impl_miroflow_agent.pth` → `/home/longxiang/MiroThinker/apps/miroflow-agent`），而**脚本方式启动时 `sys.path[0]` 是脚本目录不是 cwd** ⇒ 构建进程 import 的是活线树的 `canonical_v2`（没有 `role` 参数、没有候选身份）。修法：启动器导出 `PYTHONPATH=<switch-line>/apps/miroflow-agent`（PYTHONPATH 排在 `.pth` 之前），已实测生效。
   **切换时必须带上（第 12 步）**：现役 18188 是 cwd=自己的树、无 PYTHONPATH 启动的；切换后的 serve 命令若不把 cwd/PYTHONPATH 钉到 switch-line，就会**用旧树的代码服务新包**。

2. **窗口杀手一（每批 400）已排掉，且验的是构建自己的代码路径**：`build-embedding-path-probe.json` — document 角色、batch 20、20 篇（最长 15,078 字符、合计 171,111 字符）→ **20 行 × 1024 维、1.605 s**（0.0802 s/篇），authority 哈希与冻结值一致。**不是 curl 探针**。

3. **窗口杀手二（向量审计假失败）已排掉**：从 `/proc/2077915/environ` 读到 PYTHONPATH 确实钉在 switch-line，再读那棵树的常量 `index_projection_isolated.py:76` → `_MIN_VECTOR_COSINE_SIMILARITY = 0.99`（活线树仍 0.999）。实测重复噪声最小 0.998002 ⇒ 余量 4 倍跨度。

4. **构建的阶段钟就是它自己的打印**：`P4_MERGE_LEDGER` → `APPLICANT_BINDING_LEDGER`（两行已打出）→ 下一个是 `PATENT_COMPANY_BINDING_LEDGER` → 之后才进嵌入阶段 → 最后 `envelope_sha256=`。所以**"日志不动"不等于卡住**（合并/绑定阶段本身不打行）；判活看 PID 的 CPU 时间与取样器。

5. **遗留"车道超时纳管"核对结论：已在 switch-line 关闭**（迁移计划 §3.1 那一行已过期）。整条链现在闭合：
   - `providers/dashscope_embeddings.py:93-102`：`httpx.TimeoutException` → 内置 `TimeoutError`；`(httpx.HTTPError, OSError)` / `JSONDecodeError` → 内置 `ConnectionError`；
   - `knowledge_read_isolated.py:328-333`：传输类异常**原样上抛**，其余才包成完整性错误；
   - `knowledge_read.py` `_invoke_lane`：恰好 catch 这两个内置类型 → 记 `timeout` / `connection_failure`，车道降级而非整轮死；
   - `knowledge_read.py:713`：向量道整道预算 **8.0 s**（受管字段 `serving.vector_lane_timeout_seconds` 可调，坏值回落到默认，不会被"坏旋钮"取消上限）；
   - `canonical_v2/embedding_lane_resilience.py`：进程级熔断器，车道读与 keep-warm 共用。

6. **kb_isolated 基线对比现状（agent-79 在跑）**：`test_knowledge_build_isolated.py + test_serving_pack_no_milvus.py` 共 **159 项**，跑到第 **128** 项时已有 **14 个 F**，第 **129** 项（`test_unrecoverable_or_quarantined_input_records_typed_gap_without_placeholder_fact`，一个"在测试内跑完整构建"的集成项）**转到 100% CPU 不再前进**（20 分钟以上）。日志 `/tmp/switch-line-canonical-v2-tests.log`。**它不在封印路径上**（runbook 步 1–12 无 pytest 门），不阻塞构建；但"14 个失败是既有还是本次引入"必须有答案。

**怎么验证**：`/proc/2077915/environ` + cmdline（进程真的在用 switch-line 的代码树）；bundle 逐字段（provider / model / dim / batch / query 侧参数 / `content_sha256 67927ea0…`，文件 sha256 `35104c06…`）；`build-embedding-path-probe.json`；两棵树 `index_projection_isolated.py` 常量对比；httpx 异常 MRO 实测（**确认不是内置类型**，故"钩子永响"的判断成立）；F1 五处逐行。

**影响哪些问题**：① 切换命令多一条硬要求（钉代码树）；② 遗留清单划掉一项（车道超时纳管）；③ "kb_isolated 套件不可作为快速红绿门"入账，其失败归因待基线对比。

**并行结构（本回合）**：三条线同时跑 — 构建（PID 2077915，99% CPU，日志零 400 零 traceback，内存 7.8 GB / 503 GB 非约束）+ 身份探针（agent-80）+ 首启日志刷屏（agent-81）。三片都必须**在封印前**合入：任何 `canonical_v2/*.py` 改动若不重新封印，会让每次启动多花 137–190 s。

## 第 20 轮 · 2026-09-22 · 容器线开张（关最后 4 项）；首启刷屏修复完成（含一个额外发现的功能缺陷）；构建交班与 45 分钟取证

**一、容器交付线开张（用户指令：现在就把这条线开起来）**

把"4 项未验证"设计成**一次连贯演练**，而不是四次互不相干的操作——因为 4 项的合体恰好就是甲方的真实动作路径（我们打包 → 他们下载 → 上传到自己的机器 → 跑脚本 → 在页面填 key）：

| 命题 | 判据（要可观察，不接受"从语义推断"） |
|---|---|
| ① `--force-recreate` 反向实验 | 必须有一个**可观察结果**证明"换 key 后只 `restart` 不够"——不接受仅凭 inode 语义推理 |
| ② 管理页手填 key 真提交 | 浏览器里真的登录 `/main`、真的在 `/admin` 填并保存、真的点一次"测试" |
| ③ 真 root（sudo）安装 | 本机 `sudo` 免密可用；上次演练是**无 sudo** 的 |
| ④ 跨文件系统传送链路 | `/var/tmp`（`/`，剩 881 GB）与 `/home`（`sda1`，剩 1.3 TB）**就是两个文件系统**，可就地真做：传送 → `sha256sum -c` → **从传送后的副本**安装 |

**边界（写进派工简报，违反即失败）**：不许碰活线 18188；不许碰构建 PID 2077915 与其 `staging-v4/index-v4`；不许碰 18297 上别人的 scratch（pid 1335614）；演练端口用 **18298**；site root 新开、不复用上次的 `/var/tmp/mirothinker-delivery-rehearsal`；不跑 `docker system prune`；不回显密钥。

**用的交付件（都在盘上，不重建）**：容器 kit `/var/tmp/mirothinker-docker-kit-v11/`（`mirothinker-serving-v1.1.tar.gz` 2.16 GB / `sha256 f842f6de…`；镜像已 load，image id `sha256:04c3cfcd465f…` 与 `kit-manifest.txt` 一致）；数据面 `/var/tmp/mirothinker-data-face-xfer/serving-data-v1.1.tar.gz` 1.48 GB；站点包与 bundles `/var/tmp/mirothinker-delivery-kit-v1.1/`。安装器 `deploy/docker/install-site.sh` 自带 `MIROTHINKER_SITE_ROOT` 前缀 ⇒ 可在不碰真实路径的前提下排练。

**关于"改不改交付件"的判断**：v2 会重打镜像与数据面，所以**手改 v1.1 产物没有意义**；值得改的只有脚本/文档里的**机制缺陷**（`install-site.sh`/`compose.yaml`/`README.md`/`entrypoint.sh`），改了随 v2 重打自动带上。

**二、首启刷屏修复完成（分支 `v2/boot-log-noise`，`513b9e65` + `4d7fa03a`）**

根因：`serving_pack_loader.py:1060-1065`（修前）把 `relationships.json` 里的 `public_path_eligibility_requests` **以原始 dict 挂进**一个声明为 `tuple[PathEligibilityRequest, ...]` 的字段；pydantic 容忍但**每次 dump 对每个元素告警一次**，47,068 条 ⇒ 一行约 4.7 万行的告警。有两条 boot 路径会 dump 该字段（无收据的全量校验 `serving_pack_loader.py:1104`，以及**每次启动都会走的** `knowledge_read_isolated.py:984`）。修法＝用加载器已有的 `_parse_models` 挂成声明类型（与兄弟字段 `public_path_eligibility_results` 同款处置），不是全局静音。

**额外发现（比刷屏本身更重要）**：同一处原始挂载**还是个功能缺陷**——`knowledge_read_isolated.py:4093-4098`（教授→论文道）会调 `PathEligibilityEngine().evaluate(path_request)`，而 `path_eligibility.py:516-519` **拒绝任何不是 `PathEligibilityRequest` 的对象**。所以修复前那条道拿到的是 dict，是被拒的形状。

证据：真实日志 before（`/var/tmp/mirothinker-docker-logs/container-rw2-timed.log` 47,413 行、其中 47,360 行含该告警）；fixture 前后对照（同一代码路径 4 条请求：修前 4 条 PE 告警 → 修后 0）；dump 载荷**逐字节相等**；新测试 1 条 + 既有套件 32/35/49/1 全绿。

**它自己承认的残余风险（已授权它去验）**：类型化之后，任何一条校验不过的生产请求会**让新包 fail-closed 拒绝启动**（修前能启动）。它没能在真包上验（读 3.5 GB 会与构建抢 I/O）——**已授权续跑**：拿真包 `serving-pack-run16-readerbound/relationships.json`（3,477,354,956 B，单 JSON，顶层键 `public_path_eligibility_requests` ≈ 47,068 条）逐条 `model_validate`，并给出往返逐字节相等性的不一致条数与形状，以及峰值 RSS/墙钟/对构建的影响对照。**这是"这个修复能不能在封印前合入"的直接判据。**

**三、构建交班与 45 分钟取证**

| 时刻 | 已跑 | CPU | RSS | 日志 | 末行 |
|---|---|---|---|---|---|
| 00:12 | 1:34 | 93% | 2.3 GB | 796 B | `P4_MERGE_LEDGER` |
| 00:20 | 9:35 | 98.8% | 3.8 GB | 1050 B | `APPLICANT_BINDING_LEDGER` |
| 00:56 | 44:50 | 99.7% | 11.8 GB | 1050 B | 同上 |

仍在**恢复/合并阶段**，`ss` 显示零 socket ⇒ **尚未发出任何一次网关调用**（所以 batch-20 的证明还没被真实负载检验过，下一阶段才是）。阶段钟：`P4_MERGE_LEDGER` → `APPLICANT_BINDING_LEDGER`（已出）→ 下一个 `PATENT_COMPANY_BINDING_LEDGER` → 嵌入阶段 → 最后 `envelope_sha256=`。

**交班隐患已处理**：原采样器带 `timeout 3900`（65 分钟）会自己退出 ⇒ 已重新挂一个 `timeout 30000`（8.3 小时）的采样器，整夜有记录。

**四、一处重要更正**：kb_isolated 那 14 个失败**不是本次引入**。归因是**环境相关**——`*_nonfresh_database_*` 家族指向 Postgres **5432**，而本机构建道是 **55458**，它们断言"非新库应拒绝"，而代码答的是另一件事（candidate 迁移版本与活线单 head 不一致）。另外我先看到的"进度线更差"是**两次并发运行互相污染**所致。它不在封印路径上（runbook 步 1–12 无 pytest 门）。

**它另外标出的 4 个后段风险（记录备查）**：① 嵌入段任何传输错误都会中止整段（无 checkpoint、无重试）⇒ 只能重来；② 0.99 是**逐点**比较、覆盖约 51k 点，单个病态点仍可能掉出；③ 切换的 `src` 陷阱是**最高风险的静默失败**（新包 + 旧树代码）；④ 步 7 的转换脚本必须取自 switch-line 的 `.worktrees/drop-milvus-from-serving-pack/convert_index_to_v2.py`，禁止从构建树取。

## 第 21 轮 · 2026-09-22 · 抓到两条静默陷阱（路由标签被写反、`src` 树由谁决定）+ 切换命令校验器与草案 + 两个打击"只填 key"承诺的阻塞项

本轮是"不等构建、把后段会踩的坑提前排掉"的产物。**两条陷阱都不会报错，只会静默降质或静默换树**——正是最该在窗口前解决的类型。

**一、陷阱 A：runbook 把两条嵌入路由的标签写反了（会静默丢 B 方案 + 跨空间检索）**

runbook §0 原文把 **compat 孪生**标成 `(chosen route)`、**native** 标成 `(fallback)`，而第 12 步的表把服务侧指向 `$BUNDLE_COMPAT`。**这与 2026-09-22 的拍板相反**：选 B 的全部理由就是 `text_type`/`instruct` **只有原生接口支持**，而正在跑的构建用的正是 native。两处注释里的哈希（`45e45855…`/`cdddcdfd…`）也是上一轮冻结前的旧值（batch 25 那次；现已重冻为 batch 20）。

实测身份（本轮核过）：

| bundle | provider | dim | batch | query 侧参数 | content_sha256 | 文件 sha256 |
|---|---|---|---|---|---|---|
| native（**构建实际在用**） | `dashscope-native` | 1024 | 20 | `text_type=query` + `instruct` | `67927ea0…` | `35104c06…` |
| compat 孪生 | `openai-compatible` | 1024 | 20 | **均为 None** | `d5ff0ffb…` | `d7d2f57f…` |

**为什么是静默的**：两条路由**不是同一个向量空间**（同文本跨路由余弦上界 **0.9594**，而同路由重复是 1.0）。若构建用 native 嵌入文档、服务用 compat 嵌入查询，查询向量就落在与文档不同的子空间里——**没有任何报错，只是召回质量下降**，而召回门是对着 4096 维旧基线比的，信号本身是混的。

**已修**：§0 的两行重写（标签对调 + 新哈希 + 写明"构建与服务必须指名同一个 bundle"的理由），第 12 步表里 `--recorded-embedding-bundle` 改为 **`$BUNDLE_NATIVE`**。

**二、陷阱 B：`src` 到底由谁决定——三种启动形态实测**

现役 18188 用 `uv run python <自己 worktree 的 launcher>`，**它用的是那个 worktree 自己的 venv**（`candidate-v2-s11-consolidation/.venv`，其 editable 安装指向**它自己那棵树**）⇒ 树是被 venv 钉住的。而 switch-line **没有 `.venv`**。所以"照抄现役命令、只改路径"这条路是错的：`uv run` 会在现场**同步一个新解释器**（要联网，且 reader 指纹很可能不同 ⇒ 每次启动从 ~120 s 快路径掉到 ~285 s 重放路径）。

实测（判决性，同一台机同一分钟）：

| 启动形态 | `import src.data_agents.canonical_v2` 解析到 |
|---|---|
| 主 venv，无 `PYTHONPATH` | `/home/longxiang/MiroThinker/apps/miroflow-agent/...`（**主仓树**） |
| 主 venv，`PYTHONPATH=<switch>/apps/miroflow-agent` | `<switch-line>/apps/miroflow-agent/...` ✅ |
| `uv run`（cwd=switch-line，无 `.venv`） | 会现场同步——不可用于切换 |

三套解释器核对：主 venv **3.12.12 + pydantic 2.12.5**；现役线的 venv **3.12.12 + pydantic 2.12.5**；switch-line 无 venv。⇒ **切换应采用"主 venv + PYTHONPATH"**：它既钉住树，又**就是封印用的那个解释器**，reader 指纹因此与封印一致。已写进 runbook 第 12 步的新表行（含实测与理由）。

**三、切换命令：校验器 + 草案**

- **校验器** `…/embedding-model-switch-v2/check-cutover-command.sh`：把上面两条陷阱变成**可以判红的检查**——树是否被显式钉住、有没有残留现役树/现役包/现役索引、嵌入 bundle 是不是 native（出现 `-openai-compat` 直接 FAIL）、密钥是否注入、两处 64-hex 是否已填、新的身份三件套是否就位。
  - 对**现役命令文件**跑：**3 ok / 11 fail**（正确识别为切换前形态）。
  - 对草案跑：**12 ok / 2 fail**，且 2 个 FAIL **恰好是故意留的两处占位符**（step 7 的索引 marker、step 10 的 bundle sha）——证明占位符不会被静默放行。
- **草案** `…/s12g/serve-18188-command-fembed.DRAFT.sh`：由现役命令文件逐处替换生成，**每次替换都过了 token 级 diff 复核**（启动形态、库名、staging、index、marker、release/run id、模型 id、嵌入 bundle、服务 bundle 及其 sha、serving-pack）。**尚未安装**，两处占位符待 step 7/10 填。

**四、构建守护补齐**

嵌入段**没有检查点也没有重试**：任何一次传输错误都会让 8 小时白跑。原 2 分钟采样器只记"最后一行"，错误后面若还有输出就会被翻过去。已加一个**只读新增字节**的报警看门狗（45 秒一轮）：命中致命签名（`Traceback`/`TimeoutError`/`ConnectionError`/vector audit 等）就写 `/var/tmp/fembed-BUILD-ALERT`，命中可疑签名写报警日志。已确认在安静期**零误报**。另：原采样器带 `timeout 3900` 会自行退出，已重挂 `timeout 30000`。

**五、agent-80 交回：身份探针支持双形态（含两处交付阻塞）**

- 形态选择**问地址、不问配置**：先讲 OpenAI 兼容形态，**只有 404/405（该路由不存在）**才改讲 DashScope 原生形态；401/403/500/超时/维度变化一律**算作该路由自己的回答**，绝不换路由重试。理由写得好：管理台**不持有 bundle**，任何"声明"都会变成第二个权威，且与地址不符时会去校验**另一条**路由。
- 角色贯通到线上：索引臂 → `document`（不发 `text_type`）、参考臂 → `query`（发 `text_type="query"`）。**实测两角色相差 0.90083**，远低于两道 0.99 地坪 ⇒ **猜错角色会"判一个健康端点不合格"，而不是把错误藏起来**。
- 它还必须顺手修**连通性测试**（否则身份修复在页面上毫无体现：同一处也只会讲兼容形态，对原生前缀返回 404 → 直接跳过身份校验）。
- 新增测试 12 条；两个被改文件 41 → 51 passed；导入它们的另 8 个 admin 套件 178 passed；全量 25 failed / 1564 passed / 31 skipped / 105 errors —— 与既有的环境性红集**逐项对上**（switch 线自己记的是 "130 entries (25 failed, 105 errors)"）。另有一次多出一个未复现的 flake，如实记录。
- **两条交付阻塞项（已派它去修）**：① `resolve_embedding` 仍写死 `Qwen/Qwen3-Embedding-8B`，网关对**两条路由都**回 404 `Model not exist` ⇒ 页面连接卡不可能变绿；② 管理页把 `embedding.api_key` 写进 `SGLANG_API_KEY`，而 bundle 读 `CANONICAL_V2_EMBEDDING_API_KEY` ⇒ **页面填的 key 服务进程可能读不到**。这两条直接打击我们对甲方"**只填一个 key**"的承诺（`docs/plans/2026-09-21-customer-site-delivery-plan.md`、`deploy/docker/CONFIG-GUIDE.md`），所以列为本轮阻塞项，并要求它先钉死"这个固定值被**哪个进程**读、要不要重新封印"再动手。

## 第 22 轮 · 2026-09-22 · 判定"修复能不能在封印前合入"（结论：能，且信封不含代码树指纹）；同一 `src` 陷阱的**第三处**在封印器上被判决

**一、为什么必须先回答这个问题**

agent-81 的首启刷屏修复与 agent-80 的身份探针修复都在**别的分支**上，而正在跑的 8 小时构建 import 的是 switch-line 那棵树。我原以为"构建跑完再合入"是安全的，但有个未经证实的假设：**如果信封记录了构建时的代码树指纹，封印时会重新比对，那么构建之后再合入就会让封印失败**——那"等构建结束再合"就是错的，得改成重新跑一次构建。所以先把这个假设验掉。

**二、答案：信封里没有代码树指纹 ⇒ 构建后合入安全**

| 事实 | 证据 |
|---|---|
| `reader_contract_sha256` 由**封印器**写入（不是构建） | `build_serving_pack.py:464`：`"reader_contract_sha256": pack_loader.reader_contract_digest()` |
| 它的定义 = `sha256(python 版本 + pydantic 版本 + canonical_v2 包里每个 *.py)` | `serving_pack_loader.py:257-281`（`_PACKAGE_DIR.glob("*.py")`，整个包） |
| 信封与构建模块里**没有任何**代码树/代码身份字段 | 对 `complete_candidate_runner.py` 与 `knowledge_build_isolated.py` grep `code_tree\|code_identity\|source_tree\|tree_sha\|reader_contract` → 零命中 |
| 该指纹只决定"快路径还是重放"，不决定对错 | `_reader_contract_matches()`：三个条件全满足才跳过重放（收据已用 + 包记录了 reader + 与当前代码相同）；`verify_reconstruction=True` 时无条件重放（封印自己就是这样证明重建的） |

⇒ **合并窗口＝构建结束之后、封印（步 8）之前**。不必重跑构建。步 9 的 `mount_seconds` 是要盯的经验值（~120 s 一类＝指纹相符；~285 s＝不符）。

**三、判决：同一个 `src` 陷阱的第三处——封印器**

runbook 步 8 原文只要求"从 switch line、用部署解释器跑"。**这不够**。封印器的 `_bootstrap_src()`（`build_serving_pack.py:44-53`）是**先试着普通 import**、只有 `ModuleNotFoundError` 才回退到"自己所在那棵树"：

```python
try:
    import_module("src.data_agents.canonical_v2.serving_pack_loader")   # 主 venv 的 .pth 让这一句成功
except ModuleNotFoundError:
    agent_root = Path(__file__).resolve().parents[4] / "apps/miroflow-agent"   # 于是这条永远不走
```

而主 venv 的 `_editable_impl_miroflow_agent.pth` 指向**主仓检出**（`/home/longxiang/MiroThinker/apps/miroflow-agent`），**主仓当前在一条落后的分支上**。实测（本轮，两条并列）：

| 形态 | 封印器绑到的树 | 有 `reader_contract_digest` 吗 |
|---|---|---|
| 无 `PYTHONPATH` | `/home/longxiang/MiroThinker/apps/miroflow-agent/...`（**主仓**） | **没有** ⇒ `pack_loader.reader_contract_digest()` 会 `AttributeError` |
| `PYTHONPATH=$SWITCH_LINE/apps/miroflow-agent` | `<switch-line>/apps/miroflow-agent/...` ✅ | 有 ✅ |

⇒ **照步 8 原文跑会崩**（而且是在写 manifest 那一刻崩，不是启动时——白等 40 分钟的校验相位）。已修步 8：加 `PYTHONPATH` 钉法 + 一条**跑封印之前先证明绑对了树**的前置命令（打印 `__file__` 与 digest，并要求把该 digest 记下来，供步 9 的 `mount_seconds` 与后续比对）。同一段里写明：**服务侧命令必须用同一个钉法**，因为指纹覆盖整个包，封印与启动必须 import 同一棵树。

**三处同一陷阱的现状**：构建启动器 ✅（`PYTHONPATH` 已加，实测生效）、服务侧切换命令 ✅（草案里已含，校验器判它）、**封印器 ✅（本轮修）**。

**四、agent-81 的真包校验：反例为零（它自己承认的风险已关闭）**

它上一轮承认的残余风险是"类型化之后，任何一条校验不过的生产请求会让新包 fail-closed 拒绝启动"。现在的答案（真包 `relationships.json` 3,477,354,956 B）：

- **47,068/47,068 全部通过**，`failures=0`，耗时 **2.3 s**（49.5 µs/条，实测而非外推）；
- **往返逐字节全等**：`exclude_unset` 与不带两种 dump 各 **47,068/47,068 identical、0 mismatched** ⇒ `index_projection_request_sha256` 的复现是**必然**，不是"大概能对上"；
- 代价量化：启动只多 ~2.3 s，换来每次 dump 少 ~47k 行（≈7 MB）告警；
- **构建未受干扰**：全程"CPU 时间增量/墙钟增量"恒为 **1.000**（含读包那一格），`/proc/2077915/io` 在整个读包期间读数**一个字节没动**（它现在是纯 CPU 阶段），构建 RSS 钉住不变；唯一副作用是 3.5 GB 进了页缓存。
- 未闭合的仍如实列出：真包的端到端启动（禁区）、docker 日志里第三条 255 条 PE 的 warning 来源未定位、每次 dump 残留 11–15 条非 PE 条目是 loader 有意保留的 raw 子树。

**五、我自己的复核（不采信转述）**

- 在它的 worktree 上**自己跑**新测试：修后 `1 passed`；
- **自己造 RED**：把源文件切回修前版本（`ac4b404` 那版）再跑 → `1 failed`，失败信息正是 "the reconstruction mounted raw JSON where PathEligibilityRequest was declared" + 那条 `PydanticSerializationUnexpectedValue` 断言；
- 还原后复跑 → `1 passed`；`git status` 干净、HEAD 未变（还原命令第一次因 cwd 变化失效，随即用绝对路径还原并确认干净）。

⇒ 满足"**修复＝一条修前红、修后绿的复现测试**"的验收标准。

## 第 23 轮 · 2026-09-22 · 两个交付阻塞项已修（含承重声明复核）；**并坐实一个更严重的洞：走一键安装的甲方在 v2 上拿不到嵌入凭据**

**一、agent-80 第二轮：两个阻塞项都修了**

| 阻塞项 | 修法 | 关键判断 |
|---|---|---|
| 连接卡写死 `Qwen/Qwen3-Embedding-8B`（网关两条路由都回 404） | 模型身份改为**从已挂载包里的记录**解析（`_recorded_embedding_model`，fail-open），写死值只作"无包时"回落；**页面仍然不能改它**，只是换了来源 | 只动 admin-console ⇒ **不动** `reader_contract_sha256` |
| 管理页的 key 落进 `SGLANG_API_KEY`，而候选 bundle 读 `CANONICAL_V2_EMBEDDING_API_KEY` | 页面一个字段同时占**两个槽位**（记录行 + 候选 bundle 声明的 `api_key_source`），沿用既有"环境优先 / 收据只记名字"规则 | 动 `canonical_v2/managed_secrets.py` ⇒ **动指纹，必须在封印前合入** |

**修在写侧、不是读侧**，理由它写得很对：放宽读侧会让**第三方 bundle 拿到自建端点的 key** —— 正是 `knowledge_build_isolated` 存在要守的不变量。有一条测试专门钉住这个不对称。

**承重声明我自己复核过（不采信转述）**：

- 摘要范围：`git diff --name-only ac44b404..v2/admin-identity-native` 里落在 `canonical_v2/` 包路径下的**只有 `managed_secrets.py`** 一个（另一个 `canonical_v2/` 路径是 `apps/miroflow-agent/tests/...`，不在包内、不参与摘要）⇒ 与它的说法一致。
- `resolve_embedding` 的调用点**全在 `apps/admin-console/**`**（`canonical_v2_admin_config.py:476`、`canonical_v2_runtime_sources.py:513`）；canonical_v2 包里那个名字相近的 `resolve_embedding_base_url` 是**地址**解析、不是模型身份 ⇒ "服务进程不碰这个写死值"成立。
- 它主动纠正了一处自己的错误：凭据提交信息里引的 `c260d054…` 是 `ruff format` 重排之前的中间值，文档里已换成正确的一对（`4ab79cdf…` → `4e24e12c…`）。

**测试纪律**：先取 RED（agent 侧 4 failed/1 passed、console 侧 6 failed/75 passed），再 GREEN（新增 13 条；console 四个被改文件 81 passed、触及面 11 个文件 177 passed）；全量 console 套件 **25 failed / 1575 passed / 31 skipped / 105 errors**，且 25 个失败 id 与上一轮记录的既有环境性红集 **逐字节相同（diff 为空）**。

**实测（6 次真调用）**：页面写 → 启动投影 → 两个读者都对上（`['SGLANG_API_KEY','CANONICAL_V2_EMBEDDING_API_KEY']`，收据只记名字）；卡片实测 `ok true / 200 / 448 ms`、`provider=dashscope-native`、`role=document`、`cosine 0.998833`（阈值 0.99）。

**二、它没闭合的那一项，我自己复核后认为比它说的更严重**

它写的是："**docker/文件路线还半开着**：`deploy/docker/compose.yaml` 把 `secrets/.sglang_api_key` 当**文件**挂进去，而候选读者只认环境变量，所以现场把 key 放成文件**永远到不了候选槽位**。"

我把整条链读完了，它说轻了：

| 环节 | 事实 |
|---|---|
| 候选路由的凭据读取 | `knowledge_build_isolated._load_gateway_embedding_api_key()` = `os.environ.get(_GATEWAY_EMBEDDING_API_KEY_ENV, "").strip()` ⇒ **只认环境变量**（该函数的 docstring 甚至明写"两条 bundle 可以同一个线形状却**不共享槽位**：活线端点的 key 在 `load_local_api_key` 的槽位，第三方网关的在环境变量槽位"） |
| 一键安装器让甲方放什么 | `install-site.sh:222` 写 `${SECRETS_DIR}/.sglang_api_key`；`:412/451/465` 明确要求 4 个**文件**：`.deepseek_api_key` `.bocha_api_key` `.serper_api_key` `.sglang_api_key` |
| 容器里谁把文件变成环境变量 | `entrypoint.sh` 里 `SGLANG_API_KEY` / `CANONICAL_V2_EMBEDDING_API_KEY` **一个都没有**（grep 零命中）——文件路线靠 `load_local_api_key` 直接读文件，而那属于**v1 槽位** |

⇒ **结论：走一键安装（也就是甲方真正会用的那条路）的现场，切到 v2 之后候选嵌入路由拿不到任何凭据。** 而 F1 那个"向量道 fail-open"会让它**不报错地**降级——用户看到答案照出，只是语义检索那条道死了。这是"静默降质"里最难查的一种，且**正好落在我们要交付的形态上**。

**已有的一半**：agent-80 这轮补的是**页面路线**（管理页填 key → 两个槽位都写）。**缺的一半**是**部署路线**（一个挂载的 key 文件 → 两个环境变量名），两侧要对称。

**修法与验收计划（已定，等容器线腾出手就做）**：

1. 在 `deploy/docker/entrypoint.sh` 里按"一个文件喂两个名字"的对称规则出口候选槽位（未显式设置时才由文件推导；v1 槽位保持原样不退）；
2. **机制级验收（今天就能做，用 agent-82 正跑着的那个 v1.1 容器）**：只放文件、不设环境变量 → 容器里 `env` 必须能看到候选槽位；
3. **端到端验收（v2 重打镜像后的冷装演练）**：只给文件，v2 包挂上后向量道必须真能用；
4. 边界：不许把 key 明文写进日志/审计；不改"环境优先"的既有语义。

**为什么不在它的工作区直接改**：容器线正在跑那 4 项演练（同一个 slice 只能有一个写入者），改完也没法当场验；等它收工再动，顺带用它的容器验第 2 步。

## 第 24 轮 · 2026-09-22 · 容器线 4 项全部关掉（含一次**实测推翻我们自己写的"必须"**）；顺带发现 **v1.1 现货包在 sudo 下根本装不完**

**一、四项命题逐条结论（全部通过，且都是可观察证据）**

| 命题 | 结论 |
|---|---|
| ① `--force-recreate` 反向实验 | **通过，但实测推翻了原推断**：`restart` 就够，`--force-recreate` **不是必须**；真正咬人的是**属主**（见下） |
| ② 管理页手填 key 真提交 | **通过**（`agent-browser` 0.26.0 真登录 → 真填 → 真保存 → 真点测试；后端落盘 + 审计只有字段名与后 4 位；**"下次启动生效"也验了**：来源由 `legacy-file:.deepseek_api_key` 变成 `managed-file(env:DEEPSEEK_API_KEY)`） |
| ③ 真 root（sudo）安装 | **通过**（修完 3 个 root 专属缺陷之后）——**但现货包在 sudo 下装不完**，见第二节 |
| ④ 跨文件系统传送 | **通过**（`/var/tmp`(nvme) → `/home`(sda1) 真字节拷贝 3.4 GB；两个大归档 sha256 **MATCH**；`BUNDLE-MANIFEST.txt` 17 条 file 行 **17/17 OK**；**从传送后的副本**完成 `docker load`、解包、10 件校验、起服、验收） |

**①的反转值得单独记**：原文档写"换 key 只 `restart` 不够（bind 绑的是 inode），指南直接给 `--force-recreate`"。实测三路观测（宿主 inode/hash、容器内字节、页面连接测试）：

- 用文档原文命令换掉 key（确实换 inode）后**不重启** → 容器内仍是旧字节；
- `docker compose restart app`（281 s）后 → 容器**已改挂新文件**，表现为 `Permission denied`（新文件是 `root:root 0600`），连接测试 `ok:false / HTTP 401 / api_key_source=none` ⇒ **restart 后已按新文件工作**；
- `mv` 换 inode + `--force-recreate` → 同样 401（recreate 能做，但不是必要条件）；
- 复原：`chown 1004:1004` + **只 restart** → 容器 hash == 宿主 hash、`ok:true/200`。

⇒ **原文案的机制是错的，且漏掉了真因**：`sudo install -m 600` 让 key 文件变成 root 属主，uid 1004 的容器**读不到** ⇒ 现场表现为"换了 key 没生效"。已改 `CONFIG-GUIDE` §3/§6，并要求把"**换 key 后重跑安装器或 chown**"写进 `README-FIRST`（甲方最易踩这一条）。

**二、新缺陷 8 条（D1–D8），已修 5 条——其中 3 条让甲方根本装不上**

现货 v1.1 包在 sudo 下的真实失败链（这是"幸好还没上传"的那类发现）：

1. **exit 11** — ① 交付包**没有 `secrets/` 目录**，而文档第一条命令就写 `… secrets/.deepseek_api_key` ⇒ `No such file or directory`；② 固定的 `/tmp/mirothinker-checksums.out` 属主是别人，root 打不开，**报错却伪装成"校验失败"**；
2. 手工 `mkdir secrets` 后再跑 → **exit 13** — ③ 状态目录 `root:root 0700` ⇒ 容器入口 **exit 78**、`restarts=12` 崩循环；
3. 修好后：首启 **≈455 s**（冷数据面、无 receipt）→ `/api/health` 200；**幂等重跑 exit 0、25 ok / 0 warn / 0 FAIL、109 s、`mirothinker-verify` 全通**；此后三次重启稳定 **281 s**；属主终态全归 1004:1004（容器内 `key_readable=yes state_writable=yes`），`.env` 归操作者 ⇒ 非 sudo 的 `docker compose` 也能用；`--no-up` 新分支实测 exit 0 且不动运行中的容器。

| # | 缺陷 | 状态 |
|---|---|---|
| D3 | 真 root 安装**不归一属主**（状态目录/数据根/密钥/受管/日志）⇒ 容器 exit 78；密钥读不到 ⇒ 凭据静默"缺失" | 已修 |
| D7 | 文档"换 key 必须 `--force-recreate`"**与实测不符**，真因是属主 | 已修文档 |
| D1 | 交付包**没有 `secrets/` 目录**，而文档第一条命令就写它 | 已修（出包建目录 + README） |
| D4 | 固定 `/tmp` 输出文件 ⇒ root/非 root 混用 `exit 11`，报错伪装成校验失败 | 已修（mktemp + trap） |
| D2 | `.sha256` 写**打包机绝对路径** ⇒ 甲方 `sha256sum -c` 报"文件不存在"；**在打包机上则误校验另一个文件** | 已修 |
| D5 | `--no-up` 是空操作（用法行公开写着它） | 已修 |
| D8 | `/admin` 保存提示给的是**裸机**的 `systemctl --user restart …`（容器里没有） | 仅报告 |
| D6 | entrypoint 在 root 场景建议 `user: "0:0"`（把容器跑成 root，方向反了） | 仅报告 → **本轮已派修** |

全部都是**机制**修复（随 v2 重打自动带上），没有手改 v1.1 现货产物。

**三、并行推进**：已把上一轮我发现的**文件路线凭据洞**派给容器线（同一个工作区、同一个 running 容器可复核）：让"一个挂载的 key 文件喂两个环境变量名"，与已完成的页面路线对称；机制级验收用现成容器做，**端到端（v2 冷装时"只给文件 → 向量道可用"）明确留给 v2 验收**，不许假装验过。D6 同批修；D8 不在该批。

**四、它自己如实记录的**

`ab.sh` 早期把命令行也打进日志，导致 scratch 实例首启口令泄露到该目录日志 ⇒ **已就地脱敏，并已在浏览器里改密**（旧口令 401 / 新口令 200）。**未验**：本轮没跑 replay 门 7/7（验收对象是容器交付机制而非问答质量；容器内 `mirothinker-verify` 已通过）；"清除密钥"确认弹窗没点；`--fast` / `--accept-degraded-keys` 分支没跑；"跨机器"只做到**同机跨文件系统 + 传送后副本**，没有真·下载/上传链路。活线 18188（health 200）与 8 小时构建**全程未动**。

**五、给 v2 重打的验收建议（采纳）**：出包后跑"**新链路三连**"——跨 fs 传送 → `sha256sum -c *.sha256`（两个都应 OK）→ `sudo ./install-site.sh`，并把 `ok/warn/FAIL` 与 boot 秒数写进人类文档；`.sha256` 出包后统一自检格式（相对文件名、无打包机路径）；可选把 `--no-up`/`--dry-run` 纳入出包自检。

## 第 25 轮 · 2026-09-22 · 召回门 scratch 命令提前备好（从切换草案派生，两者不可能再分叉）

**动机**：runbook 步 11 要求门的启动命令"就是切换将要安装的那条命令"（同一个 launcher、同一个新包、同一个新索引根、同一个新嵌入 bundle），只换端口/状态路径/加门的 flag。这正是又一个"容易把树或包搞错"的地方——所以不等窗口，现在就派生好并过校验器。

**产物**：`…/s12g/serve-fembed-gate-18296-command.sh`，**从已复核的切换草案 `serve-18188-command-fembed.DRAFT.sh` 派生**。与草案的**全部**差异（token 级 diff 逐条复核，只有这四处）：

| 项 | 草案（切换用） | 门命令 |
|---|---|---|
| 端口 | 18188 | 18296 |
| `CANONICAL_V2_ACCESS_LOG_DB` | 活线状态目录 | `/var/tmp/fembed-296/logs/access-logs.sqlite3` |
| `CANONICAL_V2_CORRECTIONS_DB` | 活线状态目录 | `/var/tmp/fembed-296/corrections.sqlite3` |
| 门 flag | — | `CANONICAL_V2_TURN_DEBUG_DIR=/var/tmp/fembed-296/turn-debug`、`TURN_TRACE_DIR=/var/tmp/fembed-296/turn-trace` |

`CANONICAL_V2_MANUAL_RECALL_DIR` 有意不改（共享只读的手动召回目录，与既有门模板一致）。18296 端口当时空闲。

**校验器对两者都给 12 ok / 2 fail**，且 2 个 FAIL **各自只落在那两处故意留的占位符上**（step 7 的索引 marker、step 10 的 bundle sha）——从**切换命令**与**门命令**两个方向独立确认了同一件事。**两处占位符在窗口里一次性填两个文件**，所以门与切换命令的身份字段不可能分叉。

**一处自查**：第一次派生的 `sed` 用了行首锚点 `^CHAT_CONTEXTUAL_INTERPRETATION=on`，但那个变量在行中不在行首 ⇒ 两个门 flag **没插进去**。是**token 级 diff 把它抓出来的**（我要求每次替换都必须过 diff 复核，这次立刻兑现了价值）；改用带断言的插入后 diff 恰好只剩上面四处。

**未做**：命令文件**尚未安装**（切换前不动 `serve-18188-command.sh`）；两处占位符仍空；门本身要等新包存在才能跑。

## 第 26 轮 · 2026-09-22 · 文件路线在容器边界接通；它报的 R1 经我核实**比它说的更宽**（预置里有两个 v1 遗留值）

**一、投影规则与优先级（这是本轮最该记住的一条）**

> **一个 key 文件喂两个槽位；显式环境变量 > 管理页受管凭据 > key 文件。**

三档的顺序是有理由的，不是随手排的：**如果入口脚本抢先钉死候选槽位**，那么管理页换的 key 在候选槽位**反而失效**（服务侧"已存在即跳过"）—— 所以只在"前两档都没有"时才由文件推导。v1 槽位 `SGLANG_API_KEY` 保持"按文件直读"不变。

**二、容器边界验收（原始输出，只有名字与是否为空）**

```
[entrypoint]   环境槽位 SGLANG_API_KEY=空
[entrypoint]   环境槽位 OPENAI_API_KEY=空
[entrypoint]   环境槽位 API_KEY=空
[entrypoint]   环境槽位 CANONICAL_V2_EMBEDDING_API_KEY=已设置
[entrypoint]   key 文件 /opt/mirothinker/.sglang_api_key=已设置（v1 槽位按文件直读，不需要环境变量）
收据 exit=0

# 运行中的服务进程自己的环境（pid 26 = …serve_s12e_port）
  进程环境 CANONICAL_V2_EMBEDDING_API_KEY=已设置      ← 投影真的进到服务进程
```

收据机制本身值得记：`MIROTHINKER_ENTRYPOINT_ENV_RECEIPT=1` **由子进程打印、只有真正 export 的变量才出现**，打印后退出不启动服务 —— 所以"已设置"这句话不是断言而是可观察事实。RED 也是行为级的：改前同一 stub 子进程打印 `CANONICAL_V2_EMBEDDING_API_KEY=<空>`（文件在位、v1 槽位可读），改后同一命令打印已设置。新增 5 条测试，含"显式环境变量优先"与"三档全空 ⇒ exit 0 + 如实诊断（不崩）"。

**三、一件差点让证据落空的事（它自己发现的）**

仓库 `.gitignore:60` 有 `*.log`，全仓被跟踪的 `.log` 数为 **0** ⇒ **上一轮与这一轮的 raw 证据日志此前根本没进 git**，而文档指向的是未跟踪文件。已全部改为 `.txt` 并被跟踪（58 个证据文件在库）。**这属于"写着有证据、其实不在库里"的隐患**，值得单独记一笔。

**四、R1/R2：我核实后认为比它说的更宽**

它报的是"受管 `embedding_base_url` 覆盖 bundle 记录的网关地址，而预置值还是自建端点 `http://100.64.0.27:18005/v1`"。我去读了那份预置，`extraction_endpoints` 里有**两个** v1 时代的遗留值：

| 预置字段 | 值 | 投成的环境变量（`canonical_v2/managed_config.py:74-75`） |
|---|---|---|
| `embedding_base_url` | `http://100.64.0.27:18005/v1`（自建，甲方现场几乎肯定不可达） | `CANONICAL_V2_EMBEDDING_BASE_URL` |
| `embedding_model` | `Qwen/Qwen3-Embedding-8B`（旧 4096 维模型；网关对它回 404，且**与 1024 维索引不是同一向量空间**） | `CANONICAL_V2_EMBEDDING_MODEL` |

地址那条的影响已被它读代码确认（`knowledge_build_isolated.py:8328-8345`，两处适配器构造都走 `resolve_embedding_base_url`）；**模型那条的影响我要求它查清**（是否会进到候选适配器、还是只影响采集/旧向量化那条线）。**若不处理，v2 包原样带上这份预置，现场会"拿着网关的 key 去打自建地址"** —— 又是一类不报错的错配。

设计前提（F2 原话）：**冻身份，不冻地址**。所以地址本来就是留给操作者改的字段，bundle 也已记录网关地址为默认 ⇒ 我倾向让这两个键在交付预置里**缺席**（bundle 记录值生效，"只填 key"开箱即用；要自建仍可在管理页改）。已派它：先给带行号的事实结论 → 改预置（并确认改的是**源文件**、出包时会带上）→ 重写 `CONFIG-GUIDE §4` 那段自相矛盾的措辞 → 把其它 v1 遗留值**列出来由我判断**，不扩大改动面。

**五、没有退步（证据，不是断言）**

v1 槽位：改动前后同一条探针**逐字一致**（`ok:true / HTTP 200 / api_key_source=legacy-file:.sglang_api_key`）。"环境优先"：新增测试钉住走"已显式设置"分支且不出现文件分支日志（它诚实标注这是在**分支级别**钉的，没有打印值比对）。页面路线：仍是 `managed-file(env:DEEPSEEK_API_KEY)`、`ok:true/200`；并新增一档测试钉住"受管凭据存在时入口不抢候选槽位"。边界：活线 health=200、构建仍在跑、18297 未被触碰、本轮提交里真凭据命中数为 0（证据里的 `sk-fake-…` 全是临时假值）。

**六、端到端判据已写死，留给 v2**

`02-v2-handoff.md` 里五条，可直接照抄：① 只放 4 个 key 文件、不设环境变量跑 `install-site.sh` → exit 0；② 收据显示候选槽位已设置；③ 服务进程 `/proc/<pid>/environ` 里有该变量；④ **候选道真打一次 query embedding → HTTP 200 且维度 = bundle 的 dimension（1024）**；⑤ 该站点的有效端点必须是候选网关地址。

## 第 27 轮 · 2026-09-22 · 后段三条命令的前检：封印/转换完全对得上；**第 10 步的生成器有两处会静默产出错值**

**动机**：后段窗口（步 6–12）里"参数不对就白等 40 分钟"的地方，现在都能只读地检一遍。不等构建，先把命令与 CLI 对平。

**一、前检结果**

| 命令 | 结果 |
|---|---|
| 步 8 封印器 `build_serving_pack.py` | CLI 完全匹配：`--envelope --index-root --pack-dir --expected-release-id --generator-run-id [--pack-schema-version {canonical-v2-serving-pack-v1,canonical-v2-serving-pack-v2}] [--link]`。runbook 里"sealer must accept `--pack-schema-version`"这条前置**成立** ✅ |
| 步 7 转换器 `convert_index_to_v2.py` | 在 switch-line 里存在（2511 B），CLI = `--source-root --dest-root`，与 runbook 一致 ✅ |
| 步 10 bundle 生成器 `generate_run16_serving_bundle.py` | 存在，但**两处默认值是陷阱**，见下 ❌ |

**二、第 10 步的两处陷阱（都会静默产出错值，不报错）**

1. **`INDEX_ROOT` 常量是构建形，而 run16 bundle 实际记的是服务形。** 生成器常量写的是 `/var/tmp/mirothinker-data-v2/index-v3`，但我去读 run16 真正产出的 bundle：`index_root = /var/tmp/mirothinker-data-v2/index-v3-v2`，**与现役 serve 命令的 `--index-root` 一致**。也就是说那次实际跑的时候这个常量被改过，而**签入的副本保留的是默认值** ⇒ 照默认跑会记录错的索引根。
   我原本按"构建形"猜，是**数据纠正了我**——这正是"读产物而不是读脚本"的价值。已写明：必须设成 `$INDEX_V2`（`index-v4-v2`）。
2. **`embedding_model_id` 生成器根本不赋值。** 该字段是 schema 必填，值**从 SOURCE 继承** ⇒ 会留着 `Qwen/Qwen3-Embedding-8B`（旧 4096 维模型）。修法不是改常量，而是**往 `payload.update({...})` 那个 dict 里加一项**——runbook 原文写"edit ONLY the identities + embedding_model_id"，容易让人以为改常量就够。
   **严重度我量过**：今天**没有任何地方比对这个字段**（所有交叉校验用的是**清单的**或**适配器的** model id：`serving_pack_loader.py:756/927/957`、`index_projection_isolated.py:460/511/778` 等）⇒ 它是**卫生问题、不是启动拒绝**。但我不会把它说成无害：交付件里记着一个旧模型 id，是**后来的人会相信的那种错值**。

**三、已修**：runbook 第 10 步重写——完整编辑清单（含 `SOURCE` 要从 run15 换成 **run16**、`ENVELOPE` 用**本线**的、`PACK_DIR`/`PACK_GENERATOR_RUN_ID`、`INDEX_ROOT = $INDEX_V2`）+ 明确要求在 `payload.update` 里**加** `embedding_model_id` + 保留 `EXPECTED_MARKER_SHA256`；并加了一条**产出后读回确认两个陷阱字段**的命令（`index_root` 必须是 `index-v4-v2`、`embedding_model_id` 必须是 `qwen3.7-text-embedding-flash`），免得后面任何步骤依赖一个没验过的 bundle。

**四、本轮不改的东西**：不改生成器本身（它是 run15→run16 的历史脚本，改它等于改历史；fembed 走"复制一份再编辑"的既有做法），只把**编辑清单**与**读回验证**写死。

## 第 28 轮 · 2026-09-22 · 预置的 v1 遗留值修完（含一条**我得更正自己的判断**）；又列出 7 条遗留、其中 2 条已派修

**一、先更正我自己（上一轮我把话说过头了）**

我上一轮写"两个 v1 遗留值**都会盖住** bundle 的记录"。实测只对了一半：

| 字段 | 有运行期读者吗 | 后果 |
|---|---|---|
| `extraction_endpoints.embedding_base_url` → `CANONICAL_V2_EMBEDDING_BASE_URL` | **有**，且 `resolve_embedding_base_url(recorded)` = **`override or recorded`**（覆盖语义） | **会**顶掉候选 bundle 记录的网关地址 ⇒ **容器实测复现**：修复前 `endpoint_origin: managed-file(env:CANONICAL_V2_EMBEDDING_BASE_URL)`、`base_url=100.64.0.27` |
| `extraction_endpoints.embedding_model` → `CANONICAL_V2_EMBEDDING_MODEL` | **零个运行期读者**（镜像内全部命中 = 一处映射 + 一处测试的 scrub 列表） | **不会**进候选请求；只会让页面显示 v1 的 4096 维身份 |

模型那条的结论也有旁证：候选/自有适配器的模型一律来自 bundle（`model_id=document["model_id"]`）。**所以它是"页面误导"，不是"请求打错"。** 我把两者并列说成同等严重，是过头了。

**二、修法：两个键都**缺席**（不是填新值）**

理由（F2 的原话是"**冻身份，不冻地址**"）：bundle 已把网关地址记录为默认 ⇒ 缺席＝"默认用 bundle 记录的地址"，**"只填 key"开箱即用**；要换入口是操作者**在页面上显式写**的决定，不该由交付预置替他拍板 —— 而 v1.1 预置恰恰踩了这个坑。

出包路径也核对了：`build-site-bundle.sh:224` 是把 `site-config/managed-settings.json` 这份**源文件** place 成 `<包>/state/config-managed/settings.json`，测试里钉住了这一点（防"改了副本"）。

**判决性证据（本轮就做到，不必等 v2）**——用**镜像内的交付代码 + 服务自己的解释器**跑真投影 + 真 `resolve_embedding_base_url`，输入候选 bundle 的记录地址：

```
旧预置（已备份 .pre-r1-fix）  生效地址 = http://100.64.0.27:18005/v1          ← v1 预置覆盖（bug 复现）
旧预置 贡献的 embedding 字段  = ['extraction_endpoints.embedding_base_url', '…embedding_model']
新预置（本轮交付件）        生效地址 = https://maas.qianwenaiapi.com/api/v1  ← 网关地址，来自 bundle ✓
新预置 贡献的 embedding 字段  = ['（预置里没有 embedding 字段）']
```

运行期同一实例换预置 + restart（281 s）后：`endpoint_origin` 由 `managed-file(env:CANONICAL_V2_EMBEDDING_BASE_URL)` → **`release-bundle-default`**，连接测试仍 `ok:true / HTTP 200`（v1 槽位无回归）；管理面视图 `embedding_base_url → value=None/source=default/editable=True`、`embedding_model → value=None/source=default/editable=False`。新增 5 条测试（RED 3 failed/1 passed/1 skipped → GREEN 4 passed/1 skipped；那条 skip 是"v2 合并后才成立"的条件用例，理由写在 skip 里）。

**三、`CONFIG-GUIDE §4` 重写（R2）**

标题"唯一一处配置"→"还会用到的配置"；嵌入端点的措辞改为"**地址可改；身份（模型 + 维度）不可改**"——地址不填就用发布包记录的地址，要换入口（自建/网关/代理）在页面改地址 → 点测试 → 重启；模型 id 与维度是**冻结身份**，索引就是用这个身份建的，换了就不是同一个向量空间，必须我方重建索引并出新数据面包。并写明**交付预置为什么不预置嵌入地址/模型**。

**四、它列出的 7 条其它 v1 遗留值（只列不改），我已按优先级处理**

| # | 内容 | 我的处置 |
|---|---|---|
| **L1** | 预置里 `paths.serving_pack_dir = …/serving-pack-run16-v11`；`CANONICAL_V2_SERVING_PACK` **有读者**（pack loader、admin 状态/身份页） | **已派修**。这一条有两种后果：受管设置**赢** ⇒ v2 可能**加载 v1.1 的包**（阻塞级）；CLI **赢** ⇒ 只是页面显示错。**这个"若"必须变成带行号的事实**，并给一条能判红的检查 |
| **L2** | `install-site.sh:233` 探针写死 `"model":"Qwen/Qwen3-Embedding-8B"` ⇒ v2 站点拿旧模型 id 打网关 ⇒ 404/维度 0 ⇒ **`[warn] 嵌入端点探针未过`** | **已派修**。这是甲方**会直接看到并来问我们**的东西，方向还是"明明配好了却报黄灯"，最耗支持成本 ⇒ 按 `verify.sh` 的读法从随包 bundle 取 |
| L3 | `verify.sh` 只有**打印文字**写"维度 4096"（断言实际是 bundle 驱动的 ✓） | 未改（文案，非断言） |
| L4 | 包名写死在多处（`entrypoint.sh:23`、三个 build 脚本、install-site 等），已有 env 覆盖 + "只差一个 token"断言 | 保留（v2 换包名时要同步的一组点） |
| L5 | 文档里写死的数字/名字（`100.64.0.27:18005`、"4096"、v1 包名、commit）对 v1.1 正确、v2 要随包更新 | 只做**出包自检**（打包时报出不一致），**不改文档里成百处文字** |
| **L6** | admin-console 的 `resolve_embedding` 仍硬编码旧模型 id ⇒ v2 页面卡片仍显示 v1 身份 | **无需重复修**：`v2/admin-identity-native` 分支已改成"从已挂载包的记录解析"（有测试），保留原样避免冲突 |
| L7 | Dockerfile/entrypoint 冻结的代码副本与发布包之间没有包名/模型一致性自检 | 保留（只靠"读者摘要/解释器补丁"那套兜底） |

**五、未验（如实）**：真候选路由 + 真网关的端到端（本轮容器是 v1.1 发布包，镜像内 `dashscope` / `_GATEWAY_EMBEDDING_KEY_ENV` 均零命中）⇒ 留给 v2 冷装（判据在 `02-v2-handoff.md`）。边界未动：活线 health=200、构建仍在跑、18297 未碰、本轮提交真凭据命中数为 0。

## 第 29 轮 · 2026-09-22 · 召回门判定逻辑**免费**预标定：同配置两次运行判 REVIEW 而非 FAIL —— 噪声带与"唯一可信指标"都定下来了

**动机**：后段窗口里最大的"早上 6 点才发现"风险之一，是**判定逻辑本身**把噪声当失败（或者反过来、把真失败吞掉）。这件事不必等新包——**用两件已冻结的产物就能免费验**：`baseline.json` 与 `control.json` 是**同一配置的两次独立运行**，判它们**必须不是 FAIL**。

**做法**：`cd <recall worktree>/apps/admin-console && uv run python scripts/eval_recall_canonical_v2.py --diff baseline.json control.json`。（第一次我在主仓跑，主仓的 admin-console 里没有这个脚本——门属于 recall worktree 的工程，这在 runbook 里本就写明。）

**结果**：**VERDICT: REVIEW（exit 2）／0 fail-level／3 review-level** ⇒ 判定逻辑**不会对着噪声喊 FAIL** ✅

| 读数 | 两次运行 | 我的解读 |
|---|---|---|
| `cases` / `expected entities` / `answer entity hits` / `cases all-hit (answer)` | 37 / 37 / **31 对 31** / **20 对 20** | 答案层核心指标**完全一致** |
| `candidate-layer hits` | **22 对 29（+7）** | **候选层噪声带 ≈7** —— 所以"有标注实体的候选＋答案同时消失"这种 FAIL 判定，必须**明显越出这个带**才有意义 |
| `citation local / web` | 239/80 对 228/128 | 引用计数**摆动极大**，**不能**用它判成败 |
| `wall seconds` | 698.7 对 489.8 | 墙钟同样是噪声（那次 baseline 有 2 次 web 超时） |
| `vector median (all / shared / testset / probes)` | **61.0 / 61.0 / 61.0 / 72.0 —— 四个切片逐字相同** | **唯一零噪声的指标**；硬 FAIL 应当建立在它上面（规则：掉 >30% ⇒ FAIL） |

**3 个 REVIEW 项的形状也拿到了**（这正是"好切换"下该看到的）：全是 `rule1(concept) q15t1`（生成式模型生成 / 物理仿真引擎生成 / 基于规则生成），`ANSWER hit->miss`，并**自带成因标注 `[web timeouts=2]`** —— 是概念类**措辞**漂移，不是实体丢失。

**已写进 runbook 第 11 步**（作为"判 verdict 之前先读这段"的预标定）：REVIEW 是好切换的**预期形状**、别拿引用计数/墙钟判、候选层用 ±7 的噪声带来读、硬 FAIL 只认 `vector median`。这样窗口里不会把好消息当坏消息，也不会把噪声当 FAIL。

**方法上记一笔**：这一轮**没有发起任何新运行、没有消耗配额**——用的是已冻结的两件产物 + 一次只读的判定命令。凡是"判定逻辑可信吗"这类问题，都该先找有没有免费的自洽检查（同一配置的两次运行就是天然的自检对）。

## 第 30 轮 · 2026-09-22 · **v2 出包的集成缺口**：镜像装的是"构建时那棵树"的代码；合并集与顺序定死；镜像账本让 `mirothinker-verify` 会**

这一轮是"v2 该怎么打"的问题，属于典型的"不问就没人问"的类型。

**一、镜像装的是哪棵树的代码：答案就是"你在哪棵树里跑打包脚本"**

| 环节 | 事实 |
|---|---|
| `build-image.sh:22` | `REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"` ⇒ **脚本所在那棵树** |
| 同脚本 `:53-55` | 把 `$REPO_ROOT` 作为 docker **构建上下文** |
| `Dockerfile:83-86` | `WORKDIR /opt/mirothinker` + **`COPY . /opt/mirothinker/`** ⇒ 整个上下文进镜像 |

⇒ **从哪棵树打，镜像里就是哪棵树的代码。**

**二、缺口本身**：`delivery/docker`（交付工具线）**不包含** `ac44b404`（v2 原生路由）——它缺的正是那 6 个 v2 路由/车道文件：`embedding_lane_resilience.py`、`index_projection_isolated.py`、`knowledge_build_isolated.py`、`knowledge_read.py`、`knowledge_read_isolated.py`、`managed_config.py`。**若从它直接打 v2 镜像，就会把 v2 的数据面配上 v1.1 时代的服务代码。** 必须在**两线合并后**的树上打包。

**三、合并集与顺序（都按正确的比较框架算过）**

| 分支 | 相对**它的**基线改了 | 其中 `canonical_v2` 包内 `.py` | 必须在封印前？ |
|---|---|---|---|
| `v2/boot-log-noise`（agent-81） | 2 个文件（base `ac44b404`） | **1**（`serving_pack_loader.py`） | **是**（动 reader 摘要） |
| `v2/admin-identity-native`（agent-80） | 18 个文件（base `ac44b404`） | **1**（`managed_secrets.py`） | **是** |
| `delivery/docker`（agent-82） | 100 个文件（base `a0cd5c13`，与 switch-line 的 merge base） | **0** | **否**（摘要中立）——但**必须在打镜像前** |

**冲突风险：按构造成零。** switch-line 与 `delivery/docker` 自共同基线的改动文件**交集为 0**；两个 agent 分支相对各自基线 `ac44b404` **互不相交**，且它们在**共同继承**的 `.agents/runs/embedding-endpoint-configurable-and-lane-fail-open/*` 上**内容逐字相同**（`git diff` 为空）⇒ 不会出现 add/add 冲突。

**四、方法陷阱（我先踩了一次，记下来免得别人再踩）**

我第一次用 `git diff ac44b404..delivery/docker` 去数"它改了几个 canonical_v2 文件"，得到 **6** —— 那是**错的框架**：`ac44b404` **不是** `delivery/docker` 的祖先，那个 diff 是**两边的对称差**，列出的 6 个文件其实是 switch-line 有、而它没有的（也就是上表点名的 6 个）。用**正确的共同基线** `a0cd5c13` 再算，答案是 **0**。**做这种"要不要重封"的判断时，先确认两边共享哪个祖先**——框架错了，结论会正好反过来。

**五、镜像里的"冻结账本"会让一键验收报红（已派修）**

| 环节 | 事实 |
|---|---|
| `Dockerfile:143-146` | 把 `deploy/docker/ledger/s12c/qwen-embedding-bundle-v1.json` COPY 到冻结绝对路径 |
| 那份账本 | **v1 的**：`Qwen/Qwen3-Embedding-8B`、**4096**、`openai-compatible`、`base_url=http://100.64.0.27:18005/v1` |
| 谁读它 | `verify.sh:12` = 容器内 **`mirothinker-verify`**，也就是**我们交给甲方的一键验收** |
| 它断言什么 | 向 `{base_url}/embeddings` POST（兼容形状），要求 `status==200` **且** `dims == bundle.dimension`；不符则 `[FAIL]` + `SystemExit(1)` ⇒ `FAILED=1` ⇒ **验收判红** |
| v2 站点实际用的是 | 候选网关的**原生路由**：`qwen3.7-text-embedding-flash`、**1024 维**、`https://maas.qianwenaiapi.com/api/v1` |

⇒ v2 镜像原样重打：现场那个自建地址不可达 ⇒ `[FAIL] 嵌入端点不可达`；就算可达也是维度不符 ⇒ **FAILED=1**。**我们自己的验收会在一个装对了的站点上报红**，而甲方唯一的判断依据就是它——这比"假黄灯"严重（那是 warn，这是 fail）。已派修，要求：**镜像那条"问地址、只有 404/405 才改讲原生形状"的既有规则**（`canonical_v2_embedding_identity.py`），别自己发明第二套；期望身份**从站点真正在用的 bundle 取**，不再写死；并给一条**能判红**的检查（假 bundle 制造不一致 ⇒ 必须红）。

**六、范围外的判断（不改）**：`deploy/docker/ledger/s12a/recorded-decision-bundle-v1.json` 是决策账本，与嵌入身份无关，本轮不动；v1.1 镜像（已打好）继续带 v1 账本，两者不冲突——前提是**按发布打镜像**这个前提成立，已要求核实。
