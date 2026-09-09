---
title: 教授 Serving 刷新不能直接使用 sample-limited E2E 产物
date: 2026-04-16
category: docs/solutions/workflow-issues
module: apps/miroflow-agent professor pipeline
problem_type: workflow_issue
component: professor_serving_refresh
severity: high
applies_when:
  - 用 `docs/教授 URL.md` 跑真实 E2E 后，准备用产物刷新共享 professor serving store
  - E2E 运行时启用了 `limit-per-url`
  - 教授 coverage 缺口表现为“部分老师历史上采到过，但当前共享库里不存在”
tags: [professor-pipeline, serving-store, e2e, coverage, sampling]
---

# 教授 Serving 刷新不能直接使用 sample-limited E2E 产物

## Context

这次从 workbook 缺口反查当前共享库时，发现：

- `丁文伯`
- `王学谦`

这类教授历史上曾出现在 release / search artifact 中，但当前 `released_objects.db` 里不存在。

继续核对后，问题并不只像“发布链把人丢了”，还暴露出另一层流程问题：

- 当前用于刷新 professor serving store 的 clean aggregated 产物，本身就来自 `URL.md` E2E 的 **per-URL capped** 结果
- 例如 `logs/data_agents/professor_url_md_e2e_prd_full_aggregated_20260414/current_enriched_v3.jsonl` 中，`清华大学深圳国际研究生院` 只保留了 `3` 位教授
- 因此像 `丁文伯`、`王学谦` 这种不在前 `3` 位的老师，根本没有机会进入后续 publish

## Problem

把“用于验收的 sample-limited E2E 产物”直接拿来做 serving refresh，会系统性造成 professor coverage 缺口。

这不是单个老师的偶发遗漏，而是流程层面的错位：

- `真实 E2E 验收` 的目标是验证主链是否可用
- `serving refresh` 的目标是尽量完整地把可发布教授写入共享库

两者不能复用同一份受采样上限约束的产物。

## Symptoms

- 历史上见过的教授在当前共享库消失
- 单个 seed URL 的共享库覆盖人数明显低于真实 roster
- workbook 或检索验收里出现：
  - `professor not found`
  - `serving store gap`
  - 同校老师只有极少数能命中

## What Didn't Work

- 只盯着 publish / dedupe 逻辑查“是不是 upsert 覆盖掉了人”
- 只看历史 artifact 是否存在对应教授

这两条只能解释“为什么以前有过”，解释不了“为什么当前 clean refresh 后没有”。  
真正的问题在于：**当前 refresh 输入本身就不完整。**

## Solution

明确拆开两类运行产物：

1. **验收型 E2E 产物**
   - 可以 `sample-size < 全量`
   - 可以 `limit-per-url = N`
   - 目标是用真实 URL 快速判断主链是否收口

2. **Serving 型全量产物**
   - 必须跑目标 seed 的 full harvest
   - 不能对单个 URL 做 sample-limited 截断
   - 目标是把尽可能完整的可发布教授对象写入共享库

这次还顺手补了一个脚本级改进：

- [run_professor_url_md_e2e.py](../../../apps/miroflow-agent/scripts/run_professor_url_md_e2e.py) 现在支持 `--limit-per-url 0`
- 语义是：**不设单 URL 教授数量上限**

这让“真实 E2E 验证”和“面向 serving 的全量 harvest”可以继续沿同一条真实数据主链运行，但不再共用错误的采样约束。

## Why This Works

根因不是“教授页面抓不到”，而是：

- professor discovery 已经能发现更多老师
- 但 sample-limited 产物在 refresh 之前就把他们裁掉了

一旦把 `serving refresh` 切回 full harvest 输入，像 `丁文伯 / 王学谦` 这类老师至少会重新进入“可发布候选集”，后续才有资格讨论 release / dedupe / cross-domain linking 的问题。

## Prevention

以后涉及 professor serving 刷新时，执行顺序必须固定：

1. 用 sample-limited 真实 E2E 判主链健康度
2. 用 full harvest 真实 E2E 生成 serving 输入
3. 再跑 publish 到共享库
4. 最后跑 workbook / retrieval coverage audit

不要再把：

- `Phase A` 抽样验收产物
- `共享 serving refresh` 输入

混为同一份文件。

## Related Issues

- [教授数据采集当前发现与操作经验汇总](./professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md)
- [实现测试集答案 Workbook 覆盖度验证](./testset-answer-workbook-coverage-validation-2026-04-16.md)
- [Workbook Coverage Gap Remediation Plan](../../plans/2026-04-16-005-workbook-coverage-gap-remediation-plan.md)
- [教授数据采集在深圳有限 seed 场景下优先采用学校级 Adapter](../best-practices/professor-school-adapter-architecture-for-limited-shenzhen-seeds-2026-04-16.md)
