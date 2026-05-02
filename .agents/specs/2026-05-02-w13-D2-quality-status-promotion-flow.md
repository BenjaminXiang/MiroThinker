---
title: "W13-D2: quality_status promotion 流程（option C 混合）"
date: 2026-05-02
owner: claude
status: ready-for-codex
revision: 2
revised_reason: "user 决策（2026-05-02）：选 C 混合（高置信 auto / 中置信 pipeline_issue / 低置信保留 needs_review）"
audience: codex（实施）；claude review
wave: Wave 13 follow-up
related_specs:
  - .agents/specs/2026-05-02-w13-6-quality-status-alembic-v019.md
  - .agents/specs/2026-05-02-w12-7-summary-quality-gate.md
  - .agents/specs/2026-05-02-w13-12-paper-patent-identity-status.md
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

## 5. 决策（user 已选 C 2026-05-02）

混合规则 — 每域三档：

### professor
| 档 | 条件 | quality_status |
|---|---|---|
| high | identity_status='confirmed' AND length(profile_summary) ≥ 150 | 'ready' |
| medium | identity_status='confirmed' AND length(profile_summary) < 150 | 'needs_review' + pipeline_issue('professor_summary_too_short') |
| low | identity_status != 'confirmed' | 'needs_review' (无 issue；name-identity gate 已 catch) |

### company
| 档 | 条件 | quality_status |
|---|---|---|
| high | profile_summary IS NOT NULL AND technology_route_summary IS NOT NULL AND length(profile_summary) ≥ 100 | 'ready' |
| medium | 仅 1 个 summary 非空 | 'needs_review' + pipeline_issue('company_partial_narrative') |
| low | 双 summary 都缺 | 'needs_review' + pipeline_issue('company_no_narrative') |

### paper
| 档 | 条件 | quality_status |
|---|---|---|
| high | summary_zh IS NOT NULL AND length ≥ 150 AND identity_status='confirmed' (DOI/arXiv 验证) | 'ready' |
| medium | abstract_clean 非空 BUT (summary_zh 缺 OR identity_status='unverified') | 'needs_review' + pipeline_issue('paper_partial_metadata') |
| low | abstract_clean 也缺 | 'needs_review' (无 issue；source enrich 时再 catch) |

### patent
W13-3 writer 已用规则计算 → 1931 'ready'；W13-12 V020 land 后 + identity_status='confirmed' 时仍 'ready'。本 spec 不动 patent。

## 6. Done criteria

1. ✅ `run_quality_promote.py` dry-run 报告：professor/company/paper 各 N 候选
2. ✅ promotion_rules.py 单测覆盖三档分支
3. ✅ 实跑后各域 'ready' 比例：
   - professor: ≥ 80%（依赖 W11-7 后 summary 已 ≥ 150 比例）
   - company: ≥ 95%（98.93% 双 summary 已具备）
   - paper: ~30%（依赖 V1 summary_zh 47% × identity_status='confirmed' 子集；待 W13-12 land 后实测）
4. ✅ W12-7 reassess 重跑：≥ 5 prof 从 ready → partial（W11-7 残留短摘要）
5. ✅ pipeline_issue 写入：partial / no_narrative / paper_partial_metadata
6. ✅ ruff + 既有 quality / professor 测试不退化

## 7. 顺序依赖

依赖：
- W13-6 V019 已 land ✅（quality_status 列）
- W13-12 V020 paper/patent identity_status — paper promote 需要

可并行：
- W13-11 / W13-13 / W13-7 / W13-9（不冲突文件）

## 8. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| 三档规则 | 已锁见 §5 |
| 中档是否同时写 needs_review？| 是 + pipeline_issue trace |
| reassess 重跑时机 | promote 落地后立即 |
| chat retrieval filter | 由 W13-13 spec 处理（默认 ready 过滤；env 关闭兜底）|
