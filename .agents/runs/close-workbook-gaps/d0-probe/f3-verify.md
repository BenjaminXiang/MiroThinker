# F3 验证 — web subject-consistency 门回填修复新旧对照（2026-09-11）

> 变更（close-workbook-gaps B2/F3）：`_apply_web_subject_consistency` 回填分支
> （`knowledge_serving_isolated.py:906-918`）——`kept<floor(=3)` 时**保留全部全名命中
> （T2/T3）**，只把 T4/T5 的回填截到 floor 剩余空间。kept≥floor 分支不动。
> 依据：全名命中正是 kept 分支信任的同一信号，精度不降；「lane 不空转」不变式保留
> （kept+related 不足 floor 时 T4/T5 仍按原顺序回填）。

## 1. 生产重放新旧对照

方法同 D0.5（`collect_d05_gate_replay.py`，本次起 survivor/dropped 划分直接调用生产
`_apply_web_subject_consistency`，六锚点先按旧码钉死：merged 74/84、retained 7/3、
drops 67/81——见 `d05-gate-replay.before-f3.json`）。

| 轮次 | 指标 | 旧（trace/旧码重放） | 新（F3 重放） |
|---|---|---|---|
| g2-t2（绑定 12 家，qualifier=深圳） | merged | 74 | 74 |
| | retained | 7（kept=4≥floor 分支） | **7（分支不动，逐条同一）** |
| | dropped | 67（A 8 / C 1 / D 58） | 67（同上） |
| g5-t2（绑定 4 家，qualifier=None） | merged | 84 | 84 |
| | retained | 3（回填截断） | **12（T2 全保，+9）** |
| | dropped | 81（B+ 9 / A 4 / C 1 / D 67） | 72（A 4 / C 1 / D 67） |

g5-t2 新保留的 9 条（旧 B+ 类，全名命中展示集成员的注册/官网页）：
顺易捷×6（启信宝经营信息、天眼查、官网首页、百度百科、供应产品×2）、驭鹰者新闻页×1、
嘉立创百度百科×1——加上旧有的 3 条（驭鹰者×2、嘉立创×1），12 条 T2 全保。
排列稳健性：g5-t2 survivor 集合在全部 24 个视图排列下唯一（旧码下有 2 个变体）。

## 2. 精度面复核（放行的是否都在题）

- 放行的 9 条全部经 `_web_result_relevance_tier` 判为 T2（title+snippet 全名命中绑定成员），
  无一条 T4/T5 混入（T4 别名碰撞风险——g2-t2 的"锐曼智能装备"≠"锐曼智能技术"实例——
  仍被 floor 截断规则拦住：related 满 floor 时 T4/T5 窗口为零）。
- g2-t2 的 7 条 survivor 前后逐条同一（kept≥floor 分支代码零改动）。

## 3. 单测

- `test_gate_backfill_keeps_every_full_name_hit_above_floor`（新）：kept=0、related=4>floor
  → 4 条 T2/T3 全保、T4/T5 零窗口；旧码 RED（截断到 3），新码 GREEN。
- `test_gate_backfill_still_backfills_suspect_channels_when_related_is_short`（新）：
  kept=1、related=1 → T4 恰回填 1 条到 floor=3，其余丢弃（lane 不空转不变式）。
- 既有门测试 6 个（kept≥floor 分支、tier 序回填、soft subject、无绑定直通、双通道
  corroboration、adapter 级）全部不动通过。
- 簇验证：`-k "gate_ or subject_consistency"` → 8 passed。

## 4. 产物

- 前快照 `d05-gate-replay.before-f3.json`（旧码）、后快照 `d05-gate-replay.json`（F3 码）。
- 本文件。
