---
title: "W13-D2: quality_status promotion 流程（让 reassess 有候选）"
date: 2026-05-02
owner: claude
status: blocked-on-user-decision
audience: user（决策）；codex（实施）；claude review
wave: Wave 13 follow-up
related_specs:
  - .agents/specs/2026-05-02-w13-6-quality-status-alembic-v019.md
  - .agents/specs/2026-05-02-w12-7-summary-quality-gate.md
---

# W13-D2: quality_status promotion 流程

## 1. 现状（W13-6 V019 land 后）

- V019 已加 4 域 quality_status TEXT NOT NULL DEFAULT 'needs_review'
- W12-7 reassess 假设 promote 到 'ready' 后再筛 < 150 chars demote 到 'partial'
- 但**没人 promote** → 实测 reassess --dry-run 候选 0
- patent 是例外：W13-3 writer 直接 INSERT 时按 (title + applicants[0] + filing_date) 计算 → 1931 全部 'ready'

professor / company / paper 仍全部 'needs_review'。

## 2. 决策需要的输入（user）

**问题：哪些条件下 prof / company / paper 自动 promote 'ready'？**

候选规则：

| 域 | 推荐 promote 条件 |
|---|---|
| professor | identity_status='confirmed' AND profile_summary 长度 ≥ 150 AND name-identity gate 通过 |
| company | profile_summary IS NOT NULL AND technology_route_summary IS NOT NULL（98.93% 已满足）|
| paper | summary_zh IS NOT NULL OR abstract_clean IS NOT NULL（55.2% / 47.4%）|
| patent | W13-3 writer 已设；维持 |

但需要 user 决策：
- 阈值是否过宽 / 过严？
- 是否需要 human review approval（pipeline_issue 走 W11/Round 8c 那套）？

## 3. 选项

### 选项 A：自动按规则 promote
- 写一个 `run_quality_promote.py` 脚本：按上表规则批 UPDATE
- 落地后 prof / company / paper 大量 → 'ready'
- 之后 W12-7 reassess 才能找到 demote 候选

### 选项 B：human review 通过才 promote
- 不写自动 promote
- 在 admin /browse 加按钮"标记 ready"
- 默认全部 needs_review；review 后逐条变 ready
- 风险：1024 公司 / 7297 paper 手动 review 不可行

### 选项 C：混合（推荐）
- 高置信规则自动 promote（含 evidence + 多字段非空）
- 中置信进 pipeline_issue 队列
- 低置信保留 needs_review

## 4. Affected paths（选项 A / C）

```
新增：
  apps/miroflow-agent/scripts/run_quality_promote.py
    扫描 needs_review；按域规则匹配 → UPDATE quality_status='ready'
    支持 --dry-run / --domain / --limit
    每条变化写 pipeline_issue（type='auto_promote'）
  apps/miroflow-agent/src/data_agents/quality/promotion_rules.py
    各域规则 fn；可单测覆盖

修改：
  apps/miroflow-agent/scripts/run_quality_gate_reassess.py
    （V019 之后）应该可以正常跑；W13-D2 land 后 reassess 才能找到候选
```

## 5. 决策表（user 填）

| 项 | A（auto） | B（review） | C（混合）| 决策 |
|---|---|---|---|---|
| professor 默认 | auto-promote 含 identity_status='confirmed' | review only | auto if confirmed AND summary | __ |
| company 默认 | auto if narrative 完整 | review only | auto if 双 summary | __ |
| paper 默认 | auto if summary_zh 非空 | review only | auto if summary_zh 非空 | __ |

## 6. Done criteria（依决策）

If A or C：
1. ✅ promote 脚本 dry-run 报告：professor/company/paper 各 N 候选
2. ✅ 实跑后各域 'ready' 比例符合预期
3. ✅ W12-7 reassess 重跑：≥ 5 prof 从 ready → partial（W11-7 残留短摘要）
4. ✅ pipeline_issue 写入历史 trace

If B：
1. ✅ admin /browse 按钮 "approve ready" 实装
2. ✅ /api/review/{domain}/{id}/promote API
3. ✅ 单测覆盖

## 7. Open questions

- 不动作的话：reassess 永远 0 候选；W12-7 spec §3 描述的 mental model 永远不兑现
- chat retrieval 路径是否按 quality_status='ready' 过滤？当前 retrieval.py 不过滤；W13-13 才会改

---

**Action required**: user 在 §5 决策表填 A/B/C，并明确各域规则参数。Claude 收到后立刻起 follow-up impl spec。
