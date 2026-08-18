# 第一轮修复 · 执行日志（只追加）

> 记录「实际发生了什么」：每个阶段/切片完成后追加一条（做了什么 → 发现 → 怎么验证 → 影响哪些问题）。
> 修什么、怎么算修好见 [轮计划](./2026-08-17-systematic-fix-round-1.md)；本文件是「修到哪了」的唯一人看来源。

---

## 2026-08-18 · Phase 1 子 change 起草（待审，未动生产代码）

**做了什么**：经用户授权（builder 不自建 change，本次明确授权起草），完成 Phase 1 子 change `add-turn-trace-observability` 五件套：proposal + spec delta（canonical-v2-chat）+ design + tasks（13 项）+ acceptance，并按 RED 先行建立 `.agents/runs/add-turn-trace-observability/verification-contract.md`（含故障注入验收场景）。`openspec validate` 通过。

**勘察结论**（design.md 的地基）：现有 `AccessLogStore` 只记输出级（query/answer/citations/latency），全栈仅约 7 处 logger 调用——逐阶段归因确实不可能；web 双通道适配器（`_DualWebLaneAdapter`）逐 provider 静默吞异常、零缓存零重试零熔断，keepwarm 空闲期每 300 秒烧 2 次真实搜索。1.1 的 trace 扩展点（服务层 `_answer_locked` + serving 各 lane/gate）与 1.3 的韧性改造点都已落到具体函数。

**发现**：Serper 的「not enough credits」进程级粘性禁用将被熔断器的可恢复 OPEN 状态取代（design 已写明）；降级话术（通道不可用≠世界没有）明确留给 Phase 2.2，本轮只做韧性+可见。

**验证**：`openspec validate add-turn-trace-observability` → valid；未动任何生产代码。

**影响**：P1（观测）+ web 通道韧性；Phase 2–8 全部阶段的归因地基。

---

## 2026-08-18 · Phase 1 开工 + 任务 1.1.1 完成（RED→GREEN）

**做了什么**：用户授权完全自主决策（目标执行期间不看任何文档，含人看文档；阶段间不再停等 Accept，本条目即授权记录）。随即按 verification-contract 开工 1.1.1：先写 11 个 RED 单测（模块不存在，collection error 为 RED 证据），再实现 `backend/services/canonical_v2_turn_trace.py`——`TurnTrace` 记录（全阶段字段）+ `TurnTraceCollector`（线程安全、单次 finalize）+ `TurnTraceJournalStore`（JSONL 按日文件、保留期清理、写失败 fail-open 且计数、`TURN_TRACE_DIR` 可配）。风格对齐隔壁 `canonical_v2_access_log`（frozen slots dataclass）。

**发现**：无阻塞。实现与 design.md 唯一偏差：模型用 dataclass 而非 Pydantic（跟随本地惯例），design.md 已同步。

**验证**：`uv run pytest tests/test_canonical_v2_turn_trace_store.py` → RED（1 collection error）→ 修复一个 date-timedelta 类型错 → **11/11 通过**。纯新增文件，未触碰任何现有行为。

**影响**：P1（观测）地基落地；1.1.2（服务层挂点）/1.1.3（serving 上报）待做。

**状态**：1.1.1 完成。

---

## 2026-08-18 · 任务 1.1.2 完成（服务层 turn 边界挂点，RED→GREEN）

**做了什么**：`CanonicalV2ChatAdapter` 挂上 turn-trace：每轮在 `_answer_locked` 构造 collector（会话快照：轮序/活动锚点/已展示数/软主题；计划后回填 domains；证据集后按 lane 累计候选数；成功/澄清/异常三条出口都写 journal）。生产装配在 `canonical_v2_admin.py` 聚合构造处注入 `TurnTraceJournalStore()`。

**发现**：
1. **S11A 冻结边界**：http-adapter 契约测试逐字校验适配器构造参数与 `answer` 参数元组——构造器加参会被打回。改用**构造后注入** `attach_turn_trace()`，冻结签名零改动（该套件 128/128 保持全绿）。
2. `RetrievalTrace` 已带 lane/candidate_count/status，服务层就能记 lane 候选总数；更深的 retained/filtered 拆分和 web provider 明细归 1.1.3。
3. `test_canonical_v2_consumer_migration.py` 有 2 个**既有失败**（`create_canonical_v2_candidate_app` keyword-only seam 检查、typed public copy），stash 对照确认与本切片无关，未修（非本轮范围，记录在案）。

**验证**：新增 `tests/test_canonical_v2_turn_trace_hook.py` 4 用例（成功含全阶段断言/第二轮锚点快照/异常轮写 error trace 且重抛/无 store 纯 no-op）RED→GREEN；连同 store 套件与 http-adapter/carryover/referent 回归共 **167 通过 + 2 既有失败**。

**影响**：P1。turn 一进一出即有 trace（journal 默认 `var/turn-trace/`，`TURN_TRACE_DIR` 可配）。

---

## 2026-08-18 · 任务 1.1.3–1.1.4 完成 + 1.2 重放验证通过（trace 可归因）

**做了什么**：
1. **1.1.3 serving 层上报**：新建 `turn_trace_context.py`（Protocol + ContextVar 跨层通道，executor 线程显式传引用）；`_DualWebLaneAdapter` 上报逐 provider 尝试/错误/超时、全通道皆败时置 `web-lane-unavailable` 降级 token、web lane 真实 in/retained/filtered（来自门控拆分）；`_apply_web_subject_consistency` 上报门控丢弃计数。collector 改原始参数签名 + finalize 后容忍。测试：agent 侧 5 新增 + serving 回归 250 全绿；admin 侧 148 全绿。
2. **1.1.4 读工具**：`scripts/read_turn_trace.py`（--session/--degradation/--status/--date/--all/--expand，逐行流式）+ 4 单测。
3. **fix 分支 serve 拉起**（1.2 前置，过程曲折）：发现并处理三件事——① 18188 旧实例由 **systemd user 单元** `canonical-v2-backend.service` 自动复活（已临时 `systemctl --user stop`，恢复方式见下）；② s12g 钉死命令里的 serving-bundle sha 与 bundle 实际声明**差一个字符**（e1 vs c1，抄录错误一路传播）——用 bundle 实际声明值即可通过；③ pack 模式下 runner 用**镜像实现**组装适配器，绕过我挂的 admin 组装函数——改为挂到唯一收敛点 `create_canonical_v2_candidate_app`（backend/main.py），所有组装路径全覆盖。
4. **1.2 重放验证**：七会话重放对 trace 版 serve 全量执行。

**1.2 结果**（证据 `.agents/runs/add-turn-trace-observability/trace-baseline/`）：
- **结果与基线逐组一致**（稳定性线零漂移）：G1/G3/G5 稳定 RED 保持，G2/G6 PASS 保持；方差线在包络内（G4 今天 FAIL=正是用户实录的 P5 缺陷形态、通道本身健康；G7 今天 3/3 全过）——**trace 没有改变任何行为**（验收线 C1）。
- **四个失败全部仅凭 journal 归因**（无需看代码）：G1/G3 = 锚点绑定阶段（新闻标题「河套…香港中联办」成为会话锚点和答题主语，web-only 42/42 无门控丢弃）→ Phase 3 靶点；G4 = 数据阶段（锚点正确=优必选，但 `relationship` lane (0,0)，专利关系数据缺失）→ Phase 4 靶点；G5 = 扩展基准选择阶段（锚点=优必选但答题主语=微众银行，web 0 条）→ Phase 3 靶点。
- 健康路径：G6 澄清轮 trace 为 `degradation=clarification, status=ok`，断言 PASS。

**运维备忘**：fix 分支 serve 现于 18188 运行（TURN_TRACE_DIR=/var/tmp/turn-trace-fixline，journal 按日落盘）；systemd 单元已停——恢复旧实例用 `systemctl --user start canonical-v2-backend`，或后续把单元改指 fix 线代码（R1 时一并处理）。**注意：s12g/serve-18188-command.sh 里钉的 bundle sha 是错的（e1 应为 c1），该服务若原样重启会起不来——需修命令文件或换修复线入口。**

**验证**：单测 5+250+148+4 全绿；重放 report.json + 13 份 SSE + journal 存档；归因文档 attribution.md。

**影响**：P1 观测落地完成（1.1/1.2 全勾）；Phase 2–8 的验收从此有 trace 佐证。G4/G7 方差提醒：P5/P8 的重放断言需保留重复防线。

---

## 2026-08-18 · 任务 1.3 完成 + Phase 1 全部收口 —— ✅

**做了什么**（RED→GREEN，9 个新单测先失败后通过）：
1. **web 通道韧性**（`web_lane_resilience.py` + 适配器改造）：单次重试+250ms 退避（仅传输/超时类；auth/配额类不重试）、SQLite 结果缓存（provider+view+UTC 日键，日界即 TTL）、逐 provider 熔断器（连败 3 次开、60s 探测恢复）、配额水位（默认 4000/日，`WEB_LANE_DAILY_QUOTA` 可配）。
2. **两处行为契约更新**（均有测试跟随更新+理由注释）：Serper「积分不足」进程级粘性禁用**移除**（熔断器接管，可探测恢复）；keepwarm 从独立传输改为**走 lane 同一传输**并受水位+熔断门控（旧设计在烧配额预热 lane 根本不用的连接）。
3. **Bocha 提供方语义修正**：传输/HTTP/API 错误**改为抛出**（原来静默吞成空结果，错误不可见）；成功但零结果仍返回空列表（事实≠失败）。composite 兜底不受影响。
4. **两个生产级 bug 修复**（故障注入揭出的）：① lane 派发线程不传播 contextvar（Python 3.12 ThreadPoolExecutor 也不传播）→ `knowledge_read` 派发处逐 lane 复制 context 快照；② slotted dataclass 的 `vars()` 序列化崩溃 + journal fail-open 未兜 TypeError（曾把 turn 打成 internal_error）→ 显式字段序列化 + fail-open 收紧为全异常。
5. **RED-4 故障注入验收**：废掉 Bocha key 重启 serve → G2 重放 **ALL PASS**（serper+缓存供血，lane 存活）；72 条 web 明细入 trace（bocha auth 错误不重试、熔断 closed→open×34、serper 36 条正常大量 cache=1、门控丢弃 37 条可见）；通道存活时**无误报降级**。

**验证**：agent 侧 269 全过（serving 251 + 韧性 9 + 上报 5 + runtime）；admin 侧 163 全过（store/hook 15 + adapter 套件 148）；重放 1.2 证据 + 故障注入证据均入库。

**影响**：P2/P4/P5 的「通道波动」因素被压缩（重试+缓存+熔断）；keepwarm 配额燃烧受控；Phase 2 起的验收有完整 trace 佐证。生产 serve 已恢复真实 key 运行（18188）。

---

## 2026-08-18 · Phase 2 完成（绝不拒答契约 + 降级语义）—— ✅

**做了什么**（RED 7 先行→全绿；提交 6d3865f + 收口）：
1. **兜底文案重写**（2.1.1）：弃「暂未能确认…换个角度」拒答形态，改契约形式——首句点名主体 + 已确认声明 + 指名覆盖缺口 + 可行动下一步。
2. **外甩护栏**（2.1.2）：答案含国知局/PatSnap/Incopat 类外部数据库推荐且本轮零专利证据 → 改写为「本地库暂未建立专利关联（数据覆盖缺口）」+ 保留已确认内容；有真实专利依据时**不动**（有据推荐合法）。
3. **通道故障语义**（2.2.1）：web lane 全废的轮次上，「未找到该机构」类否定性世界断言 → 改写为「网络检索暂不可用」+ 保留本地/缓存证据；健康答案零误伤。
4. **提示词契约**（2.2.2）：合成提示的降级策略③不再教 LLM 说「公开信息中未找到该主体」（世界断言源头），改为「当前检索与本地库尚未覆盖（覆盖范围所限）」；新增外甩禁令与通道状态表述规则。

**验证**：
- 单测：新护栏 7/7 RED→GREEN；旧拒答文案 4 测试按新契约更新（附理由）；admin 163/163、serving 237 全绿。
- **V1 双通道全废**：web-only 主体（国先中心）答案＝「当前本地库暂未建立关联（数据覆盖缺口）」+ 行业背景——主体点名、零否定断言、trace 降级 token 正确；本地富主体（优必选）照常完整作答（护栏正确不介入）。
- **V2 七会话重放**：**G4 专利转 PASS（外甩消失——P5 话术形态修复）**；G3/G5 保持 RED（Phase 3 靶点，预期内）；G6/G7 PASS。

**发现（重要，Phase 3 输入）**：V2 中 G2 转 FAIL / G1 转 PASS——均为 P1 家族**锚点漂移**的方差窗口：G2 追问轮答案漂到了「中国科学院深圳先进技术研究院」（错误实体，逐字引用在案），与话术无关。G1 单轮通过不改变其 RED 定性（无重复防线，按方差记录）。

**运维**：fix 线 serve 启动脚本固化为 `.agents/runs/serve-fixline-18188.sh`（内含修正后的正确 bundle sha c1…，永久消除 s12g 命令文件的 e1 抄录雷）；健康实例 18188 运行中。

**影响**：P2 拒答形态、P5 外甩话术修复；「通道不可用≠世界没有」落地（护栏+提示词双保险）；P4 的「这一机构名称」类措辞由主体点名改写间接压制。

---

## 2026-08-18 · 用户新需求入册：迭代式 web 研究 + 过程反馈（扩展 Phase 5）

**需求原文要义**（会话记录）：web search 不应只做一轮——先 search 再 fetch，基于 fetch 结果调整方向再 search/fetch，迭代逼近准确详实；过程中耗时可给初步反馈。web 作为兜底，用户问题总应拿到一些信息；没把握就模糊处理并引导用户说清问题；展现上归因到问题侧、包装出信息量与把握度。

**裁定**（当日，双向钢人论证后）：
- **采纳**迭代研究循环（Phase 5 扩展：轮次≤3、墙钟≤40s、配额感知；零件全在现有栈中）+ 过程反馈（SSE 阶段发现流式，/chat 渲染归 P9/P7）；
- **采纳分查询类的呈现策略**：实体/背景类按用户意图充分包装（web 有货，包装有事实支撑）；结构化枚举类保持覆盖诚实（中文开放 web 对专利/论文清单兜不住，硬包装=空转）；
- **修正归因策略**为按成因分流（真歧义→引导用户[Phase 3 闸门可检测]；数据缺口→如实说；通道故障→说暂不可用）。理由：统一「问题在您」话术在多轮使用中会被识破，且对清楚的问题（G4 专利）是错误归因，识破的代价是产品整体信誉；同时会污染改进信号。

**影响**：Epic change-log 已记录 Phase 5 范围扩展；阶段顺序不变，Phase 3 照常下一个（它是「问题是否真歧义」的检测器，条件归因的前提）。

**状态**：继续 Phase 3。

---

## 2026-08-18 · 裁定修订：弱 web 证据场景选 B（观感优先，带归因标注）

用户在旗舰边界案例（优必选专利、本地零证据、web 仅营销页「数百件专利」）上明确选 **B**：从容语气呈现 + 「据公开报道」归因标注 + 主体实质内容 + 「我可以再细化」式深度引导。落地策略：**web 有任何可用信号→B 形态；web 全废/零命中→故障/覆盖表述（不可包装）**。两条硬线保留：不编造具体事实（数字保持来源精度）、不甩外部数据库。已在合成提示词降级阶梯加入 ②b 层实现（serving 回归 237 全绿）；Epic change-log 已记修订。

---

## 2026-08-18 · 审阅关卡调整（用户规则，非代码）

**做了什么**：无代码。用户明确：后续所有 OpenSpec 文件不需要用户审阅（用户不看 openspec/）；用户只看本套人看文档（docs/plans/）。文件级审阅关卡取消，agent 侧靠 OpenSpec 纪律自治（validate + tasks + acceptance 证据）；阶段级 Accept 保持——以我提交的验收证据报告为准，不要求读文件。规则已写入 AGENTS.md §3。

**影响**：Phase 1 起实现不再有「等审」环节；进度报告的落点是人看日志与状态板。

---

## 2026-08-18 · 文档体系与仓库整理（非代码，无行为影响）

**做了什么**
- 分支收敛：远端 23 → 4 条。19 条历史分支逐条读提交与代码分诊后，确认无一需要合入，全部转为 `archive/<原分支名>` tag（本地+远端）。Phase 4/8 可能回取的内容（关系族规划、深大抓取器、论文检索门工具）已列回取指引，见轮计划 §七。
- 人看文档体系重构：新建本日志；总目录（index.md）改为纯人看的问题状态板（去掉所有 agent 侧引用）；AGENTS.md §15.0 升级为「索引 / 计划 / 日志 / 分析 / 调研」五类文档规则。

**为什么**：此前体系只有计划、没有记录——执行事实塞在冻结计划的表格行里，完整叙事散落在 agent 工件（`.agents/runs/`）中，从文档看不出 Phase 0 已完成。

---

## 2026-08-17（晚）· Phase 0 冻结基线 —— ✅ 已完成

**做了什么**
1. 七会话重放工具（`apps/admin-console/scripts/replay_fix_round1.py`）：把当天用户实测的 7 组对话固化为可重复执行的回归套件，逐组自动断言，其中 2 组各重复跑 3 次以暴露随机波动。此后每次热更新前必跑。
2. 对当时的线上服务跑完整基线取证（13 轮 SSE + 断言报告存档）。
3. 冻结轮计划（问题账本、逐组验收线、十阶段、发布节奏 R1/R2/R3）与 agent 侧 Epic。

**基线结果（修复前的体检报告）**

| 会话 | 结果 | 对应问题 |
|---|---|---|
| G1 国先中心→追问 | ❌ 稳定复现（2 项断言失败：河套开头、主体不在首句） | P1 |
| G2 裸名首答 | ✅ 当晚 3 连通过；下午实录拒答 → 定性为**通道波动** | P2 / P3 |
| G3 人称追问论文 | ❌ 稳定复现（3 项断言失败） | P4 |
| G4 优必选专利 | ✅ 当晚通过；下午实录外甩国知局 → 同为波动 | P5 |
| G5 类似公司扩展 | ❌ 稳定复现（以微众银行为基准） | P6 |
| G6 新会话指代开场 | ✅ 正确澄清 | **P7 定案依据** |
| G7 具身智能清单 | ❌ 3 次中 1 次缺优必选 | P8 方差定量化 |

**关键发现**
- **P7 定案**：真新会话的澄清闸门工作正常；用户遇到的「新会话不澄清」实为浏览器标签页沿用旧会话 cookie。属产品契约缺陷（会话范围与用户心智不符），不再按检索缺陷修。
- **P9 新发现**：用户实际使用的 `/chat` 是后端静态页（走流式接口），源码中的 React 前端走同步接口——两套前端并存，历史上有行为分叉。
- P2 / P4 类波动型缺陷：以用户逐字实录为准入证据，重放断言保留防复发。
- 稳定可复现的 RED 共 4 组（G1 / G3 / G5 / G7），修复目标明确。

**验证**：重放报告与 13 份 SSE 全部存档；G6 PASS 即 P7 定案证据。

**结论**：Phase 0 完成（重放工具 / 基线取证 / 双文档 / Epic 四项交付齐）。**Phase 1（可观测性 + web 通道韧性）未开始。**
