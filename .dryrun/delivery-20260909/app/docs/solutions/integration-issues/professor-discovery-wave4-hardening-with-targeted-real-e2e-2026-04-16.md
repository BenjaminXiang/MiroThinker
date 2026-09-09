---
title: 教授 discovery Wave 4 硬化必须用 targeted real E2E 收口
date: 2026-04-16
category: docs/solutions/integration-issues
module: apps/miroflow-agent professor discovery
problem_type: integration_issue
component: professor_discovery
severity: high
status: historical_reference
superseded_by:
  - docs/solutions/workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md
applies_when:
  - 教授 discovery 残余问题已经从明显 identity 错误转成 fetch/runtime/并发尾项
  - 需要决定某个 discovery 修复是不是只在单测里成立，还是已经在真实 URL 上收口
  - 需要避免把慢尾 URL 误判成新挂起

tags: [professor-discovery, e2e, playwright, fetch-policy, fallback, cuhk]
---

# 教授 discovery Wave 4 硬化必须用 targeted real E2E 收口

> Historical reference only. This document keeps the detailed wave-4 discovery hardening evidence and forensic notes.
>
> The current resolution state is summarized in [`../workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md`](../workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md).

## 问题

当 direct-profile 主线已经收住后，教授 discovery 剩下的问题不再是 `工作履历/Teaching` 这类显性 identity 错误，而是更隐蔽的工程尾项：

- fetch-policy learned state 会不会污染下一轮
- seed fallback page 会不会无意义放大抓取面
- `reader_first` 会不会重复打 reader
- blocked `200` 页面会不会吞掉 direct attempt 痕迹
- shared Playwright browser 在 threaded pipeline 里会不会序列化或复用 stale browser

这类问题单靠单测不够，因为它们的真实价值取决于：**修完以后，真实 URL E2E 会不会更稳定，而且不引入回归。**

## 处理方式

这轮采用了两层收口法：

1. **先用失败测试把行为钉死**
   - non-blocked `HTTPError` 要走 fallback
   - `reader_first` 不得重复 reader
   - root 页已有候选时不得再调 seed fallback
   - CUHK repeated page 要提前停止
   - per-run discover 必须重置 learned fetch-policy state
   - blocked `200` 要保留 direct request error
   - stale browser state 要淘汰并重试一次

2. **再用 targeted real E2E 判断修复值不值**
   - `SUSTech root seed`: 验证 root 页面已有候选时不会被 fallback page 扩面带歪
   - `SZU hub seed`: 验证 hub recursion 在收窄 fallback 后仍然稳定
   - `CUHK teacher-search`: 验证慢尾 browser-first 场景在 thread-local/stale-browser 修复后仍能通过

## 代码落点

- [discovery.py](../../../apps/miroflow-agent/src/data_agents/professor/discovery.py)
- [roster.py](../../../apps/miroflow-agent/src/data_agents/professor/roster.py)
- [test_roster_validation.py](../../../apps/miroflow-agent/tests/data_agents/professor/test_roster_validation.py)

## 结果

单测回归：

- `87 passed`

真实 URL E2E：

- [wave4 targeted round3](../../../logs/data_agents/professor_url_md_e2e_wave4_discoveryfix_targeted_round3_20260416/url_e2e_summary.json)
  - `南方科技大学 https://www.sustech.edu.cn/zh/letter/`
  - `深圳大学 https://www.szu.edu.cn/szdw/jsjj.htm`
  - `香港中文大学（深圳）理工学院 https://sse.cuhk.edu.cn/teacher-search`
  - 结果：`gate_passed_urls = 3 / 3`
- [wave4 seed036](../../../logs/data_agents/professor_url_md_e2e_wave4_agentfix_seed036_20260416/url_e2e_summary.json)
  - `released = 29`, `ready = 23`, `gate_passed = true`
- [wave4 seed013](../../../logs/data_agents/professor_url_md_e2e_wave4_diag_seed013_20260416/url_e2e_summary.json)
  - `released = 3`, `ready = 3`, `gate_passed = true`

## 经验

1. `CUHK teacher-search` 这类 URL 是慢尾，不要在没有对比单-seed历史耗时前就把“空子目录”误判成新挂起。
2. 当问题已经进入 discovery/fetch/runtime 尾项阶段，**最有效的真实验证不是全量乱跑，而是带代表性的 targeted real E2E**。
3. 一旦 targeted batch 已经覆盖 root seed、hub seed、browser-first seed 三类关键路径，就可以把这轮 discovery 修复标记成已收口，而不是继续回到旧问题上空转。
