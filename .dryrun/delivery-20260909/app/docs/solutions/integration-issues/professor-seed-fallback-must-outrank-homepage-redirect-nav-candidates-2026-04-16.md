---
title: Professor Seed Fallback Must Outrank Homepage Redirect Nav Candidates
date: 2026-04-16
category: docs/solutions/integration-issues
module: apps/miroflow-agent professor discovery
problem_type: integration_issue
component: seed_fallback_priority
severity: high
tags: [professor-pipeline, discovery, seed-fallback, sysu, e2e]
---

# Professor Seed Fallback Must Outrank Homepage Redirect Nav Candidates

## Problem

`http://sa.sysu.edu.cn/zh-hans/teacher/faculty` 在真实环境里不是直接报错，而是会被重定向到学院首页。
当前 discovery 的 fallback 规则只在两种情况下触发：

1. 抓取失败
2. 当前页完全没有候选链接

这会导致一个坏场景：

- seed 页本身没有教授条目
- 但首页里有大量栏目导航链接
- discovery 先追栏目页，配置好的 faculty fallback 反而被饿死

结果就是 `0 unique professors`，看起来像 roster 抽取失败，实际上是 fallback 优先级错误。

## Fix

在 discovery 里加一条更窄的规则：

- 仅对“配置了 seed fallback 的 URL”生效
- 仅对“当前抓到的是首页重定向页”生效
- 这时优先排 seed fallback 页面，并跳过首页里的栏目候选

识别首页重定向页的信号：

- 请求路径本来像 roster seed（如 `teacher/faculty`）
- HTML 的 canonical path 却落到首页路径（如 `/zh-hans`）
- 页面 title 显示 `首页` / `home`

## Verification

单测：

- `test_discover_professor_seeds_prioritizes_configured_seed_fallback_when_primary_page_is_homepage_redirect`

真实 E2E：

- 修前：[wave5 SYSU faculty family baseline](../../../logs/data_agents/professor_url_md_e2e_wave5_sysu_faculty_family_20260416/url_e2e_summary.json)
  - `sa = 0 released / gate_passed=false`
- 修后：[wave5 SYSU faculty family round2](../../../logs/data_agents/professor_url_md_e2e_wave5_sysu_faculty_family_round2_20260416/url_e2e_summary.json)
  - `sa = 3 released / gate_passed=true`

## Rule

对配置了 seed fallback 的学校，**不要把“首页里有候选链接”当成 fallback 不需要触发的充分条件**。如果当前页本质上是首页重定向，配置的 fallback faculty page 必须优先级更高。
