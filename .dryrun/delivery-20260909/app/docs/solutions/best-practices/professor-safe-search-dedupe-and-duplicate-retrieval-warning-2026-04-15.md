---
title: 教授共享检索库应先安全合并同人重复对象，再把剩余歧义显式告警
date: 2026-04-15
category: docs/solutions/best-practices
module: apps/miroflow-agent professor publish and retrieval eval
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - 真实共享检索库里出现同校同名教授重复对象
  - 需要提升教授搜索结果质量，但不能冒险误合并同名不同人
  - 想让真实 E2E 自动暴露剩余同名歧义样本
tags: [professor-pipeline, search-quality, dedupe, retrieval-eval, phase-a-gate, real-data]
---

# 教授共享检索库应先安全合并同人重复对象，再把剩余歧义显式告警

## Context

2026-04-15 的真实共享库检查发现，教授域虽然已经通过 PRD 主门禁，但发布后的检索库里仍存在 `同校同名` 重复对象：

- `尤政院士 | 清华大学深圳国际研究生院`
- `樊建平 | 深圳理工大学`
- `刘清侠 | 深圳技术大学`

这里不能简单按 `name + institution` 全量合并。真实 payload 对比显示：

- `尤政院士` 两条对象的 `homepage` 和 `official evidence URLs` 完全一致，属于确定性重复。
- `樊建平` 与 `刘清侠` 虽然官方 profile URL 不同、院系不同，但真实页面和汇总摘要又显示它们极可能是同一人跨院系任职。

所以这类问题不能只靠“全量 name+institution 合并”，也不能永远停在 warning。需要分层处理：

- 先合并确定性重复
- 再合并高置信同人重复
- 最后只把剩余真正不确定的歧义留给 warning

## Guidance

教授共享检索库的去重策略应分三层：

1. 发布侧只合并 `强锚点一致` 的确定性重复对象。
   当前实现位于 [run_professor_publish_to_search.py](../../../apps/miroflow-agent/scripts/run_professor_publish_to_search.py)。
   仅当同校同名记录满足下面任一强锚点重合时才进入同一聚类：
   - 非根路径的 `homepage`
   - `official_site` evidence URL
   - email

2. 对强锚点不同、但高度像同一人的对象，再做第二层安全合并。
   当前实现仍位于 [run_professor_publish_to_search.py](../../../apps/miroflow-agent/scripts/run_professor_publish_to_search.py)。
   仅当同校同名记录同时满足下面条件时才会继续合并：
   - `title` 一致且不是泛化 title（如单独的“教授”）
   - summary 高相似，或共享强身份锚点
   - 个人邮箱不构成强冲突

   当前共享的强身份锚点包括：
   - `加拿大工程院院士`
   - `国家科技进步二等奖`
   - `中国青年科技奖`
   - `国务院特殊津贴`
   - 以及同类高区分度头衔/奖项

   邮箱也做了强弱区分：
   - `fanjianping@...` 这类个人邮箱算强锚点
   - `public/info/admin/contact/...copyright` 这类公共或脏邮箱不再阻断同人合并

3. 评测侧显式统计 `Top-5 duplicate target`，但只作为剩余歧义的 warning。
   当前实现位于 [run_professor_retrieval_top5_eval.py](../../../apps/miroflow-agent/scripts/run_professor_retrieval_top5_eval.py) 和 [run_professor_phase_a_gate.py](../../../apps/miroflow-agent/scripts/run_professor_phase_a_gate.py)。
   `retrieval_top5_report.json` 现在会为每条 query 记录：
   - `expected_target_match_count`
   - `duplicate_expected_target_in_topk`

   聚合后的 `retrieval_eval.json` 会再给出：
   - `top5_duplicate_target_query_count`
   - `top5_duplicate_target_rate`

   Phase A gate 不会因为这类歧义直接阻断，但会产生 warning：
   - `retrieval_duplicate_targets=<count>`

这条线的原则是：

- 对确定性重复，要自动清掉，避免脏搜索结果污染体验。
- 对高置信同人重复，也要自动清掉，避免重复目标对象继续污染检索。
- 对证据仍不够强的同名对象，不做冒险合并，而是让真实 E2E 持续报出来。

## Why This Matters

如果直接按 `name + institution` 强行合并，短期看重复少了，但会引入更危险的问题：把同名不同人、或者同人不同正式任职页面，错误折叠成一个对象。

这轮真实数据已经证明，更稳的做法是：

- 自动修掉 `尤政院士` 这类确定性副本
- 自动修掉 `樊建平 / 刘清侠` 这类高置信同人重复
- 只把真正剩余的不确定歧义留给 retrieval warning

这样质量改进是“可解释且可追踪”的，不会把错误藏进搜索库里。

## When to Apply

- 重刷教授共享检索库时
- 修改 professor 发布逻辑时
- 调整 retrieval eval / Phase A gate 时
- 真实 E2E 显示 Top-5 命中没问题，但用户体验仍被重复对象影响时

## Examples

这轮真实 before/after 结果已经验证了这套策略。

首先，当前共享库基线里有 3 组同校同名重复：

- `尤政院士|清华大学深圳国际研究生院`
- `樊建平|深圳理工大学`
- `刘清侠|深圳技术大学`

基线检查结果：

- [retrieval_eval.json](../../../logs/data_agents/professor_retrieval_eval_duplicate_baseline_20260415/retrieval_eval.json)
  - `top5_duplicate_target_query_count = 3`
  - `top5_duplicate_target_rate = 0.75`

第一轮安全去重后：

- [publish_report.json](../../../logs/data_agents/professor_search_refresh_dedupe_20260415/publish_report.json)
- 本地发布库 [released_objects.sqlite3](../../../logs/data_agents/professor_search_refresh_dedupe_20260415/released_objects.sqlite3)

重复簇降为 2 组，只剩：

- `樊建平|深圳理工大学`
- `刘清侠|深圳技术大学`

对应 after 检索评测：

- [retrieval_eval.json](../../../logs/data_agents/professor_retrieval_eval_duplicate_after_20260415/retrieval_eval.json)
  - `top5_duplicate_target_query_count = 2`
  - `top5_duplicate_target_rate = 0.5`

第二轮同人合并后：

- [publish_report.json](../../../logs/data_agents/professor_search_refresh_sameperson_dedupe_round2_20260415/publish_report.json)
- 本地发布库 [released_objects.sqlite3](../../../logs/data_agents/professor_search_refresh_sameperson_dedupe_round2_20260415/released_objects.sqlite3)

此时本地 professor 域已经是：

- `professor_count = 116`
- `duplicate_name_institution_count = 0`

重复敏感 query 的真实 after 结果是：

- [retrieval_eval.json](../../../logs/data_agents/professor_retrieval_eval_duplicate_sameperson_round2_20260415/retrieval_eval.json)
  - `top5_exact_target_rate = 1.0`
  - `top5_duplicate_target_query_count = 0`
  - `top5_duplicate_target_rate = 0.0`

再用 PRD 最终那套 58 条真实 professor query set 复跑：

- [retrieval_eval.json](../../../logs/data_agents/professor_phase_a_retrieval_eval_prd_full_sameperson_round2_20260415/retrieval_eval.json)
  - `top5_exact_target_rate = 1.0`
  - `top5_duplicate_target_query_count = 0`
  - `top5_duplicate_target_rate = 0.0`

最终严格 gate 仍通过，而且 duplicate warning 已经消失：

- [phase_a_gate_report.json](../../../logs/data_agents/professor_phase_a_gate_prd_full_sameperson_round2_20260415/phase_a_gate_report.json)
  - `go_for_phase_b = true`
  - `warnings = []`

共享 `released_objects.db` 也已同步刷新到同一状态：

- [publish_report.json](../../../logs/data_agents/professor_search_refresh_shared_sameperson_round2_20260415/publish_report.json)
- 真实共享库重复簇检查结果：`duplicate_name_institution_count = 0`
- [retrieval_eval.json](../../../logs/data_agents/professor_retrieval_eval_duplicate_shared_sameperson_round2_20260415/retrieval_eval.json)
  - `top5_duplicate_target_query_count = 0`
  - `top5_duplicate_target_rate = 0.0`

再进一步把 PRD query set 压成弱查询 `姓名 + 教授` 后做 stress run：

- [retrieval_eval.json](../../../logs/data_agents/professor_phase_a_retrieval_eval_prd_weakname_20260415/retrieval_eval.json)
  - `query_count = 57`
  - `top5_exact_target_rate = 1.0`
  - `top5_duplicate_target_query_count = 0`
  - `top5_duplicate_target_rate = 0.0`

这说明当前实现已经进入更完整的正确状态：

- 确定性脏重复会被自动清掉
- 高置信同人重复也会被自动清掉
- PRD 主门禁不会被误伤
- 当前这批真实共享库里，`Top-5 duplicate target` 已经被压到 `0`
- 即使降成弱查询，真实检索仍保持 `Top-1 / Top-5 exact = 1.0`

## Related

- [教授 PRD 收口必须以真实数据的 Phase A 严格门禁为准](./professor-prd-real-data-phase-a-gate-2026-04-14.md)
- [官方挂出的 ORCID 应作为教授论文第二证据源](./official-linked-orcid-second-evidence-source-2026-04-15.md)
