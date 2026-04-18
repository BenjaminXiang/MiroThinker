---
title: Professor Seed Context And Generic Faculty Direct-Profile Misclassification
date: 2026-04-16
category: docs/solutions/integration-issues
module: apps/miroflow-agent professor pipeline
problem_type: integration_issue
component: discovery_and_seed_parser
severity: high
tags: [professor, seed-parser, discovery, direct-profile, sysu, real-e2e]
---

# Professor Seed Context And Generic Faculty Direct-Profile Misclassification

## Problem

这一轮真实 E2E 暴露了两个连续问题：

1. `姓名 + URL` 形式的直达个人页 seed，在 `run_professor_url_md_e2e.py` 外层会按 host 推断学校，但主 pipeline 的 `parse_roster_seed_markdown()` 不会，因此 institution 会在真正执行链里丢失。
2. `http://materials.sysu.edu.cn/faculty/staff` 这类 generic faculty roster 页，会因为 URL 中含有 `faculty/` 被错误判成 `direct_profile_url`，从而直接绕过 roster discovery。

## Why It Happened

- seed parser 之前只信 heading / inline context，不会在缺少上下文时按 host 补学校。
- `_looks_like_direct_profile_url()` 之前对 `teacher/ faculty/ people/` 这类路径过于乐观，只要 path 命中就直接返回 `True`，没有区分 `faculty/staff` 这种通用 roster 叶子页。
- 一旦误判成 direct-profile，后续 profile 提取就在错误页面上抽标题或链接词，先后出现了 `教师队伍`、`教授`、`校内链接` 这类假对象。

## Fix

### 1. Seed parser 补 host-based institution inference

在 [parser.py](../../../apps/miroflow-agent/src/data_agents/professor/parser.py) 中，当 markdown 行本身没有学校上下文时，按 host 自动补学校：

- `sigs.tsinghua.edu.cn -> 清华大学深圳国际研究生院`
- `cuhk.edu.cn -> 香港中文大学（深圳）`
- `sysu.edu.cn -> 中山大学（深圳）`
- 等

### 2. direct-profile URL heuristics 收紧

在 [discovery.py](../../../apps/miroflow-agent/src/data_agents/professor/discovery.py) 中：

- `faculty/staff`、`faculty/index`、`people/list` 这类通用叶子不再因为路径前缀被判成 direct-profile
- 仍保留 `teacher/162`、`people/jianwei-huang` 这类明显人物详情页命中
- `main.htm` 这类带明确 seed label 的个人页，改走 `labeled direct-profile` 辅助判定，而不是靠宽松 fallback

### 3. non-person names 继续在 gate 上硬拦

在 [name_selection.py](../../../apps/miroflow-agent/src/data_agents/professor/name_selection.py) 中补了更硬的 exact non-person titles：

- `教师队伍`
- `教授`
- 以及其他裸职称

## Verification

单测：

- `94 passed`：`test_roster_validation.py`
- `136 passed`：`test_roster_validation.py + test_name_selection.py + test_quality_gate.py`

真实 E2E：

- 修前失败：
  [direct label postfix baseline](../../../logs/data_agents/professor_url_md_e2e_direct_label_postfix_20260416/url_e2e_summary.json)
  - `李立浧 main.htm` 因 institution 丢失失败
- 修后通过：
  [direct label round2](../../../logs/data_agents/professor_url_md_e2e_direct_label_postfix_round2_20260416/url_e2e_summary.json)
  - `gate_passed = true`
- 修前失败：
  [SYSU materials round3](../../../logs/data_agents/professor_url_md_e2e_sysu_materials_round3_20260416/url_e2e_summary.json)
  - 出现假对象 `校内链接`
- 修后通过：
  [SYSU materials round4](../../../logs/data_agents/professor_url_md_e2e_sysu_materials_round4_20260416/url_e2e_summary.json)
  - 回到真实教师 `陈文多`
  - `gate_passed = true`

## Takeaway

`姓名 + 直达个人页 URL` 与 `faculty/staff` 这两类 seed 不能靠同一套宽松 URL heuristics 处理。

- 前者需要 `seed label + host context` 才安全
- 后者必须先走 roster discovery，再让真实教师候选进入后续链路

否则系统会在错误页面上生成“看起来结构化、实际上是导航词”的假教授对象。
