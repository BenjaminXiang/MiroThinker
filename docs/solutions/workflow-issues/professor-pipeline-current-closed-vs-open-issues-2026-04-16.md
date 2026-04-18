---
title: 教授 Pipeline 当前已收住与剩余旁路问题清单
date: 2026-04-16
category: docs/solutions/workflow-issues
module: apps/miroflow-agent professor pipeline v3
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - 用真实 URL E2E 判断教授域当前主线问题
  - 需要区分已收住的问题与下一波 school-adapter 优先级
  - 需要避免把已修掉的 gemma4/direct-profile 问题反复算作 blocker
tags: [professor-pipeline, e2e, gemma4, direct-profile, identity, quality-gate, school-adapter]
---

# 教授 Pipeline 当前已收住与剩余旁路问题清单

## 结论

到 2026-04-16 UTC，本轮 discovery / direct-profile / seed-parser / generic-roster 这条主线已经再次收口。

最新真实证据：

- direct-profile 个人页 seed 修复后通过：
  [direct label round2](../../../logs/data_agents/professor_url_md_e2e_direct_label_postfix_round2_20260416/url_e2e_summary.json)
  - `李立浧 https://www.sigs.tsinghua.edu.cn/llyys/main.htm`
  - `gate_passed_urls = 1 / 1`
- `materials.sysu.edu.cn/faculty/staff` 修复后通过：
  [SYSU materials round4](../../../logs/data_agents/professor_url_md_e2e_sysu_materials_round4_20260416/url_e2e_summary.json)
  - `name = 陈文多`
  - `gate_passed_urls = 1 / 1`
- 更宽 host family 扩样：
  [wave5 matrix A](../../../logs/data_agents/professor_url_md_e2e_wave5_matrix_a_20260416/url_e2e_summary.json)
  - `清华 / 南科大 / 北大深研院 / 深大 / 深理工 / 哈工深 = 6 / 6 gate_passed`
- wave5 第一阶段 adapter 目标批次也已 fresh 通过：
  [wave5 matrix B round2](../../../logs/data_agents/professor_url_md_e2e_wave5_matrix_b_round2_20260416/url_e2e_summary.json)
  - `香港中文大学（深圳）/ 中山大学（深圳）/ 深圳技术大学 = 6 / 6 gate_passed`

这意味着当前已经收住的症状包括：

- `gemma4 401 / http->https` 误判为主线 blocker
- `工作履历 / Teaching / Presentation` 被当成人名
- `姓名 + 直达个人页 URL` seed 在主 pipeline 里丢失 institution 上下文
- `faculty/staff` 这类通用 roster 页被误判成 direct-profile
- `教师队伍 / 教授 / 校内链接` 这类非人名导航词被当成教授对象放进 release

## 已收住

### 1. Gemma4 调用链

`gemma4` 的 `http -> https`、stale `API_KEY` 覆盖、shared env loader 已经收住，不再是当前 blocker。

### 2. direct-profile 主线

以下真实问题都已经通过真实 E2E 收口：

- detail-profile 无 label 误走 roster recursion
- root-homepage 无 label 被当目录页
- page title / inline seed label 被栏目词覆盖
- L1 失败对象仍带着 `ready` 进入后续结果

历史主证据仍有效：

- [direct-profile round4](../../../logs/data_agents/professor_url_md_e2e_direct_identityfix_round4_20260416/url_e2e_summary.json)
- [URL.md sample 20-22 round2](../../../logs/data_agents/professor_url_md_e2e_urlmd_sample20_22_round2_20260416/url_e2e_summary.json)
- [wave4 targeted round3](../../../logs/data_agents/professor_url_md_e2e_wave4_discoveryfix_targeted_round3_20260416/url_e2e_summary.json)

### 3. direct-profile seed parser institution 继承

`parse_roster_seed_markdown()` 现在会在缺少 heading/context 时，按 host 自动补学校上下文。这样 `姓名 + URL` 形式的真实个人页 seed 不会在主 pipeline 里丢失 institution。

真实证据：

- [direct label round2](../../../logs/data_agents/professor_url_md_e2e_direct_label_postfix_round2_20260416/url_e2e_summary.json)

### 4. generic faculty/staff roster 不再误当个人页

`http://materials.sysu.edu.cn/faculty/staff` 现在不再沿错误的 `direct_profile_url` 路径短路，而是回到正常的 roster discovery，再沿真实教师候选进入后续链路。

真实证据：

- 修前错误样本：
  [wave5 matrix B baseline](../../../logs/data_agents/professor_url_md_e2e_wave5_matrix_b_20260416/url_e2e_summary.json)
  - 曾出现 `name = 教师队伍`
- 修后收口样本：
  [SYSU materials round4](../../../logs/data_agents/professor_url_md_e2e_sysu_materials_round4_20260416/url_e2e_summary.json)
  - `name = 陈文多`
  - `gate_passed = true`

### 5. generic non-person names 会在质量门被拦掉

`教师队伍 / 教授 / 校内链接` 这类导航词或裸 title 现在会被 `name_not_person` 拦住，不再靠 `needs_enrichment` 软着陆进 release。

## 当前剩余的不是 blocker，而是下一波结构优化

当前剩余重点已经不是 wave4 bugfix，而是 school-adapter phase 1 完成后的下一波 family 扩展：

1. `school_adapters.py + roster dispatch` 已经落地，并且 phase 1 的真实验证已闭环，不再只是设计图。
2. `CUHK teacher-search + SYSU faculty/staff` 的第一阶段样本已经全部 fresh 收绿，包括 `materials / saa / sa` 这几个更宽 SYSU family 点。
3. 当前下一步如果继续，不是回头补 phase 1，而是决定 `SZTU / SUAT-SZ` 是否单独开 phase 2，或者转去更深的论文/企业/专利关联增强。

## 验证快照

本轮 fresh 回归：

- `12 passed`：`test_school_adapters.py + CUHK/SYSU targeted roster tests`
- `141 passed`：`test_roster_validation.py + test_name_selection.py + test_quality_gate.py + test_school_adapters.py`

本轮 fresh 真实 E2E：

- [direct label round2](../../../logs/data_agents/professor_url_md_e2e_direct_label_postfix_round2_20260416/url_e2e_summary.json)
- [SYSU materials round4](../../../logs/data_agents/professor_url_md_e2e_sysu_materials_round4_20260416/url_e2e_summary.json)
- [wave5 matrix A](../../../logs/data_agents/professor_url_md_e2e_wave5_matrix_a_20260416/url_e2e_summary.json)
- [wave5 matrix B round2](../../../logs/data_agents/professor_url_md_e2e_wave5_matrix_b_round2_20260416/url_e2e_summary.json)
- [wave5 SYSU faculty family round2](../../../logs/data_agents/professor_url_md_e2e_wave5_sysu_faculty_family_round2_20260416/url_e2e_summary.json)

## Related Issues

- [教授数据采集当前发现与操作经验汇总](./professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md)
- [Professor Pipeline Residual Hardening Plan](../../plans/2026-04-16-003-professor-pipeline-residual-hardening-plan.md)
- [Professor School-Adapter Architecture Plan](../../plans/2026-04-16-004-professor-school-adapter-architecture-plan.md)
