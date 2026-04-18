---
title: Workbook Closure Via Source Backfill And Serving-Side Knowledge Fields
date: 2026-04-16
category: docs/solutions/best-practices
module: agentic-rag shared knowledge base
problem_type: closure_strategy
component: workbook-coverage
severity: high
tags: [workbook, backfill, serving-store, company, professor, paper, patent, knowledge-fields]
---

# Workbook Closure Via Source Backfill And Serving-Side Knowledge Fields

## Problem

workbook 题组暴露的缺口并不都是同一种问题：

- 有的是对象根本不在 serving store
- 有的是对象在，但强关联缺失
- 有的是 exact identifier 缺失
- 有的是底层知识字段模型根本不存在

如果把这几类问题混在一起处理，就会在 release/search 层空转，或者把本该做 source acquisition 的问题误判成代码 bug。

## What Worked

这次收口靠的是四段式路径：

1. 先把 workbook 问题固化成 `run_workbook_coverage_audit.py`
2. 对 `paper/patent/company/professor` 分别补 source backfill，而不是直接往 shared store 手塞对象
3. 在 consolidate 阶段补 serving-side relation / knowledge field backfill
4. 每轮改动后都回到真实 `released_objects.db` 重新跑 workbook audit

## Why It Worked

### 1. Exact identifier 问题优先走 source backfill

`pFedGPA` 和 `CN117873146A` 的主问题都不是 retrieval 算法，而是当前 source 里缺这条精确对象。

解决方式：
- `paper_exact_identifier_backfills.jsonl`
- `patent_exact_identifier_supplement.xlsx`

这样可以继续复用既有 `import/release/publish` 主链，而不是特判 audit。

### 2. 对象缺失问题优先走 company supplement source

`普渡 / 开普勒 / 云迹 / 擎朗 / 九号 / 嘉立创 / 深南电路 / 一博 / 迈步机器人` 的缺口，本质是 company source 缺对象，不是 company release 逻辑错。

解决方式：
- `company_workbook_critical_supplement.xlsx`
- `run_company_release_e2e.py` 支持 primary + supplement sources

### 3. 强关联问题放到 serving-side consolidate 统一补

`丁文伯 -> 深圳无界智航科技有限公司` 不适合硬塞进 professor crawl 主链，因为证据强度和 release 节奏不同。

解决方式：
- `professor_company_roles.jsonl`
- `consolidate_to_shared_store.py` 在 professor domain consolidate 时补 `company_roles`

这样既不会污染原始 crawl 结果，也能在 serving 层明确看到证据链。

### 4. 行业研究题不要一开始就追求“直接回答整题”

`q11-q16` 的 blocker 不是对象缺失，而是 `data_route_types / real_data_methods / synthetic_data_methods / capability_facets / movement_data_needs / operation_data_needs` 这类字段根本不存在。

解决方式：
- `company_knowledge_fields.jsonl`
- `consolidate_to_shared_store.py` 在 company domain consolidate 时补知识字段
- `run_workbook_coverage_audit.py` 从固定 `model_gap` 升级为字段驱动判定

## Operational Rule

以后再遇到 workbook / PRD closure，一律先判断问题属于哪一类：

- `object missing` -> 补 source / import / release
- `exact identifier missing` -> 补 identifier backfill
- `relation missing` -> 补 serving-side relation backfill
- `knowledge model missing` -> 补 serving-side knowledge fields + audit checks

不要在 retrieval/search 层盲调去掩盖 source/model 缺口。

## Final Evidence

这条路径最终在真实共享库上得到的结果是：

- `16 pass + 1 out_of_scope`
- 报告：`logs/data_agents/workbook_coverage_final_post_review_20260416/workbook_coverage_report.json`

这说明 workbook closure 的正确单位不是“单脚本成功”，而是：

`source backfill -> release/publish/consolidate -> shared store -> workbook audit`
