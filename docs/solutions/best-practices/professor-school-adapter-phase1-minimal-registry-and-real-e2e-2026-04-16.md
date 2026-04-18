---
title: Professor School Adapter Phase 1 Should Start With Minimal Registry And Real E2E
date: 2026-04-16
category: docs/solutions/best-practices
module: apps/miroflow-agent professor pipeline
problem_type: best_practice
component: school_adapter_phase1
severity: medium
status: historical_reference
superseded_by:
  - docs/solutions/best-practices/professor-school-adapter-architecture-for-limited-shenzhen-seeds-2026-04-16.md
  - docs/solutions/workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md
tags: [professor-pipeline, school-adapter, roster, e2e, sysu, cuhk]
---

# Professor School Adapter Phase 1 Should Start With Minimal Registry And Real E2E

> Historical reference only. This document records the phase-1 adapter rollout shape and real E2E evidence.
>
> For the current architecture direction, read [`professor-school-adapter-architecture-for-limited-shenzhen-seeds-2026-04-16.md`](./professor-school-adapter-architecture-for-limited-shenzhen-seeds-2026-04-16.md).
> For the current closed/open status, read [`../workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md`](../workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md).

## Rule

学校级 adapter 的第一刀不要重写主链，也不要把现有 selector 大搬家。先做：

1. 独立 `school_adapters.py`，只承载 `matcher / extractor / bypass`
2. 在 `roster.py::extract_roster_entries()` 顶层做 `first-match-wins` dispatch
3. adapter 内优先复用现有 host-specific helper
4. 只要 adapter 没产出候选，就立刻回退原 generic 流程

## Why

这样做有两个好处：

- 可以把 `CUHK teacher-search`、`SYSU faculty/staff` 这类已知 host family 显式化，但不引入大范围行为漂移
- 真实 E2E 一旦发现回归，可以退回到“registry + dispatch 已保留，但 extractor 继续依赖原 helper”的最小安全面

## What Worked

这轮 phase 1 的实际落点是：

- `apps/miroflow-agent/src/data_agents/professor/school_adapters.py`
- `apps/miroflow-agent/src/data_agents/professor/roster.py`

落地方式：

- `school_adapters.py` 只定义 `SchoolRosterAdapter`、`find_matching_school_adapter()`、`school_adapter_bypass_enabled()`
- `roster.py` 里把 `CUHK teacher-search` 和 `SYSU faculty/staff` 先包装进最小 adapter
- `extract_roster_entries()` 在 `hit directory` 之后、generic path 之前优先尝试 adapter

## What Not To Do

不要把这些职责一起混进去：

- `discovery.py` 的分页与 crawl policy
- `playwright` 生命周期管理
- `quality_gate` 语义
- `publication / paper` 逻辑

Phase 1 的目标是把 host family 边界显式化，不是顺手重构半条 pipeline。

## Verification

代码回归：

- `12 passed`：adapter + CUHK/SYSU targeted tests
- `140 passed`：broader professor targeted suite

真实 E2E：

- [direct label round2](../../../logs/data_agents/professor_url_md_e2e_direct_label_postfix_round2_20260416/url_e2e_summary.json)
- [SYSU materials round4](../../../logs/data_agents/professor_url_md_e2e_sysu_materials_round4_20260416/url_e2e_summary.json)
- [wave5 matrix A](../../../logs/data_agents/professor_url_md_e2e_wave5_matrix_a_20260416/url_e2e_summary.json)
- [wave5 matrix B round2](../../../logs/data_agents/professor_url_md_e2e_wave5_matrix_b_round2_20260416/url_e2e_summary.json)

当前最重要的结果不是“adapter 写出来了”，而是：在 phase 1 adapter 已接入的情况下，`CUHK / SYSU / SZTU` 这组真实 batch 已经 fresh 收口为 `6 / 6 gate_passed`。
