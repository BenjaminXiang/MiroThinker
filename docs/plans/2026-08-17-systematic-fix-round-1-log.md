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

**状态**：1.3（web 通道韧性）未开始——下一步。

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
