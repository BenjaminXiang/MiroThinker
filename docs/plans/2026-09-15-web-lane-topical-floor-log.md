# Web 轨主题相关性地板（topical floor）— 执行日志

- 分支：`fix/web-lane-topical-floor`（worktree `.worktrees/web-lane-topical-floor`，基线 `10dd2bd1`）
- 关联问题：用户查询「详细介绍一下 国先中心（深圳）」的「查看检索过程」中出现 3 条网页，其中
  「多彩深圳——减肥达人训练营深圳国贸营地简介」（sohu.com）明显不相关；用户要求：召回噪音可接受，
  但必须有一层「非常快速、非常轻量」的机制把明显与 query 无关的网页滤掉。
- 契约（agent 侧）：`openspec/changes/web-lane-topical-floor/`（proposal/design/tasks/acceptance）；
  证据：`.agents/runs/web-lane-topical-floor/{red-case.md,verification-contract.md,verification.md}`。

## 一、做了什么

1. **复现 RED（不改代码）**：从活线 18188 的 turn-debug 转储
   `turn-debug-bKkX9SSixSj6-03.json` 取到该回合的逐字事实（query、锚点
   `深圳国际先进技术应用推进中心`、web lane wall 4.159s），并用「查看检索过程」里 3 条网页的
   标题/URL（正文摘要按页面性质重建，标注为重建）在本地跑通 `_apply_web_subject_consistency`
   与 tier 判定。
2. **归因**：该页 tier=5（wrong-organization 通道），由 `_apply_web_subject_consistency` 的
   **H2 补位**分支放入——kept 只有 1 条（sz.gov.cn 那条经 **H3 双引擎同源 ⇒ tier 0** 无条件保留），
   低于 `_WEB_SUBJECT_CONSISTENCY_FLOOR=3`，`backfill_room=2`，pool=[T5, T5] 两条垃圾全部补进
   admitted 集合，且 `record_gate_drop` 全程无记录（即当日 trace 上"看不出被过滤过"）。
3. **新增一层 web 轨专用地板** `_apply_web_topical_floor`（`knowledge_serving_isolated.py`）：
   主体身份豁免（复用 subject gate 同一口径：全名形式 + 拼音品牌域名 + soft subject）之外，
   要求结果与 query 有**核心词元**重叠；核心词元 = 去掉问句框架词与位置词后的 CJK 字符 bigram /
   拉丁整词；否则丢弃。纯确定性、不调模型、不走网络。
4. **接线**：主通路在 subject gate 之后、枚举补强（榜单/名单）合并之前各调用一次（补强结果同样过地板）；
   `record_lane_counts("web", …)` 保持在地板之后统计；丢弃计数走
   `record_gate_drop("web_topical_floor", n)`。
5. **开关**：`CANONICAL_V2_WEB_TOPICAL_FLOOR=0/false/off/no` 关闭（默认开启，按调用时读取）。

## 二、发现（超出原设计的事实）

- **找不到"空车道"是允许的**：`WebLane.__call__` 在结果集为空时直接
  `raise ConnectionError("Bocha and Serper Web search are unavailable")`，即空车道会被当作
  **检索不可用**（降级），而不是"没有相关结果"。`_WEB_SUBJECT_CONSISTENCY_FLOOR` 本来就为此存在。
  原设计只写了"否则丢弃"，与其冲突：若某 query 的全部网页都无核心词元重叠，地板会把车道打成
  provider 故障。**处理**：地板若将丢弃全部结果，则保留该批次的第 1 条（流水线里即 subject gate
  排序最高者）并记 warning，其余仍丢弃——宁可少丢不可错丢。已在 design.md 单列"与冻结设计的偏差"，
  待主会话拍板（若要严格空车道 + 前端提示，则需另立改动）。
- **补位通道是噪音主入口**：H2 补位池（T4/T5）会把 gate 自己判为"错误机构"的页面当 filler；
  H3 只看双引擎同源、不看相关性。本次改动不动 gate 语义，只在其后加一层地板。
- **微基准**：64 条结果 200 次重复，中位 **0.875 ms**（p95 0.895 ms、max 0.979 ms），预算 5 ms。
  为守住这个预算，把 `_web_identity_domain_matches` 里的拼音换算拆成
  `_web_identity_domain_labels`（语义不变），在每次车道调用里只算一次。

## 三、怎么验证

- **新增测试** 16 个（`tests/canonical_v2/test_web_lane_topical_floor.py`）：真实 RED 案例（先过
  subject gate 再过地板，逐字断言两条垃圾被丢）、仅位置词重叠不构成匹配、枚举样本保留、身份豁免
  （全名 / 拼音品牌域名 / soft subject）、fail-open（无核心词元、空文本）、kill switch 逐字旧行为、
  确定性、丢弃计数、空车道保护、64 条 ≤5ms 预算。
- **既有套件**：见 `verification.md` 分层记录。
- **scratch E2E**：18295（run15 packing + scratch index/bundle/marker 重定向），用户案例 + 探针 +
  枚举回归 + `replay_fix_round1.py` 7 会话，见 `verification.md`。

## 四、影响哪些问题

- 用户报告「网络 3 条里有明显不相关页」：本片直接处理（web 轨层）。
- 未动其它域车道、未动 subject gate、未动装载/缓存（并行改动 `serving-index-process-scope` 互不重叠）。
- 待拍板：空车道保护策略、以及"主题地板是否也要覆盖 refined 之后的页面抓取文本"（当前只在
  gate 后、抓取前看 title+snippet，属设计的物理位置）。
