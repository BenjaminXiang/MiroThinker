---
title: 教授 Pipeline 中 Playwright Browser 必须按线程隔离
date: 2026-04-16
category: docs/solutions/integration-issues
module: apps/miroflow-agent professor discovery
problem_type: integration_issue
component: playwright_lifecycle
severity: high
applies_when:
  - professor pipeline 使用 ThreadPoolExecutor 抽取 profile
  - discovery.py 里用 playwright.sync_api 作为 browser fallback
  - 需要并发运行真实 URL E2E 或批量教授抓取
tags: [professor-pipeline, playwright, threadpool, e2e, browser-fallback]
---

# 教授 Pipeline 中 Playwright Browser 必须按线程隔离

## Problem

教授 pipeline 的 Stage 1/2 会通过线程池并发抽取 profile，而 `discovery.py` 里的 browser fallback 使用的是 `playwright.sync_api`。

如果把 Playwright runtime/browser 存成**单个全局共享对象**，不同线程会复用同一个 sync API runtime，最终在真实批次里触发：

- `greenlet.error: Cannot switch to a different thread`

这类错误不会稳定出现在单测或串行小样本里，但会在并发真实 E2E 中直接打出来。

## Root Cause

`playwright.sync_api` 的 runtime 和 browser 不是线程安全的“可任意跨线程复用对象”。

之前的实现把：

- `_SHARED_PLAYWRIGHT`
- `_SHARED_BROWSER`

放在模块级全局里，由 `_get_shared_playwright_browser()` 返回同一个 browser 给所有线程。只要 browser 在 A 线程初始化、在 B 线程使用，就会撞上 greenlet/thread 约束。

真正的冲突结构是：

1. `pipeline.py` 用 `ThreadPoolExecutor` 并发跑 profile extraction
2. `fetch_html_with_fallback()` 在 anti-scraping 路径上进入 `_render_html_with_playwright()`
3. `_render_html_with_playwright()` 调用全局共享 browser
4. 不同线程碰同一个 sync API runtime，触发 thread switch error

## Fix

不要共享单个全局 Playwright browser。

改成：

- 用线程 ID 作为 key，维护 thread-scoped `(playwright, browser)` registry
- `_get_shared_playwright_browser()` 只返回“当前线程自己的 browser”
- `_shutdown_shared_playwright_browser()` 在退出时统一关闭 registry 里的所有 browser/runtime

这样做之后：

- 同一线程内仍然可以复用 browser，避免每次 fallback 都重新启动浏览器
- 不同线程之间不会再交叉复用同一个 sync API runtime
- 生命周期边界也从“隐式全局单例”变成了“可解释的 thread-scoped 共享”

## Verification

### Test

新增回归测试：

- `apps/miroflow-agent/tests/data_agents/professor/test_roster_validation.py`
  - `test_shared_playwright_browser_is_thread_scoped`

它验证：

- 两个并发线程拿到的 browser 必须不同
- shutdown 时要能清掉多个线程各自的 runtime

### Real E2E

真实并发重放验证：

1. direct-profile guardrail
- `logs/data_agents/professor_url_md_e2e_wave4_guardrail_round3_20260416/url_e2e_summary.json`
- `2/2 gate_passed`
- `陈伟津`、`Jianwei Huang` 都重新通过

2. 更重要的证据
- 修复前，并发拉起两条真实 E2E 会直接打出 `greenlet.error: Cannot switch to a different thread`
- 修复后，用同样的并发姿势重放，不再出现这类 Playwright 线程异常

## Rule

**只要 `playwright.sync_api` 和线程池同时存在，就不要把 browser/runtime 做成单个进程级共享对象；至少要做到 thread-scoped。**
