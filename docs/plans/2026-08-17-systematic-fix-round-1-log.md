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

**状态**：继续 1.1.2。

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
