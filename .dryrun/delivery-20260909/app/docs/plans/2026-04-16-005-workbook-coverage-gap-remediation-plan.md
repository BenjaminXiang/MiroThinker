---
title: Workbook Coverage Gap Remediation Plan
date: 2026-04-16
owner: codex
status: completed
---

# Workbook Coverage Gap Remediation Plan

## Completion Note

截至 `2026-04-16`，本计划已经通过真实 shared-store audit 收口。最终结果为 `16 pass + 1 out_of_scope`，报告见 `logs/data_agents/workbook_coverage_final_post_review_20260416/workbook_coverage_report.json`。

当前结论：
- `W0/W1/W2/W4/W5/W6` 已完成并在真实数据上闭环
- `W3 professor-to-patent` 未单独扩成新的通用主链，但当前 workbook 范围已由 `q17` 的 patent exact backfill 与 shared-store 发布闭环满足，因此不再构成当前计划的阻断项
- 后续如要继续扩教授-专利通用主链，应另起专项计划，而不是继续占用这份 workbook remediation plan


## Goal

把 [测试集答案.xlsx](../../docs/测试集答案.xlsx) 暴露出的缺口，收敛成一条**可逐项验收**的修复主线。

验收原则不是“模型能否生成像样答案”，而是：

- 当前 serving store 是否包含支撑回答所需的实体与关联
- 当前 retrieval / publish / cross-domain linking 是否能稳定命中这些实体
- 修复后是否能用**真实数据 E2E**重复证明问题已经收住

## Why This Plan Exists

[实现测试集答案 Workbook 覆盖度验证](../solutions/workflow-issues/testset-answer-workbook-coverage-validation-2026-04-16.md) 已经证明：

- 教授主链本身已基本可用，但 serving store 与历史有效 artifact 仍有断层
- `教授 ↔ 企业`、`教授 ↔ 专利`、精确论文/专利号命中、特定公司覆盖仍明显不足
- workbook 后半段行业研究类问题，部分已经超出当前知识模型范围

因此不能把 workbook 缺口当成一个“大而空”的目标，而必须拆成：

1. **当前模型可修复的覆盖缺口**
2. **需要扩模型的知识层缺口**

## Scope

本轮纳入范围：

- workbook 关键实体在 serving store 中的稳定可得性
- `教授 ↔ 论文 / 企业 / 专利` 的跨域关联增强
- `paper` / `patent` 的精确 ID 命中能力
- workbook 指名公司集合的定向覆盖补齐
- 以 workbook 题组为准的真实数据验收脚本

本轮暂不直接承诺：

- 行业研究类问题一次性全部自动化解决
- 大规模开放互联网公司发现
- 通用市场研报生成

这些内容会进入本计划的后半阶段，以“知识建模扩展”方式推进，而不是混在前半段的实体/关联修复里。

## Acceptance Standard

只有同时满足以下条件，才算某个 workbook 缺口真正修掉：

1. 真实数据链路产物进入当前 serving store
2. 对应 workbook 题组的关键实体/关联命中检查通过
3. 有对应的 JSON/Markdown 验证报告落盘
4. 如果涉及教授采集主链，必须附带真实 `docs/教授 URL.md` E2E 证据

## Workstreams

### W0. Workbook Coverage Harness

目标：

- 把 workbook 题组从“手工核查”变成机器可复跑的 coverage harness

交付：

- `run_workbook_coverage_audit.py` 之类的验证脚本
- 题组到实体/关系/命中规则的配置层
- JSON/Markdown 报告

最小能力：

- professor / company / paper / patent 四域存在性检查
- 精确名称 / 精确编号 / 关键词 fallback 分开统计
- 题组级 `pass / partial / fail`

真实验收：

- 以当前 [logs/data_agents/released_objects.db](../../logs/data_agents/released_objects.db) 为输入跑出基线报告
- 后续每次修复后复跑，观察题组状态变化

### W1. Professor Serving Continuity Repair

目标：

- 修掉“历史 artifact 里有教授，但当前 serving store 没有”的断层

优先对象：

- `丁文伯`
- `王学谦`

根因假设：

- professor artifact 已生成但未稳定发布
- 发布去重 / release 条件 / shared store 刷新过程把目标对象丢掉
- 或者当前 serving refresh 输入本身来自 sample-limited E2E 产物，导致目标教授在发布前就被截断

交付：

- 可复现的 professor artifact -> publish -> serving store 验证链
- 定向修复发布断层
- 把“验收型 sample-limited E2E”与“serving 型 full harvest”分离
- 针对目标教授的存在性回归

真实验收：

- 目标教授在 serving store 中可命中
- 对应真实 professor E2E 产物与共享库对象可追溯对齐
- full-harvest 输入中能看到这些目标教授，不再被 `limit-per-url` 截断

### W2. Professor-to-Company Link Hardening

目标：

- 把 workbook 关心的“参与创立 / 任职 / 关联企业”从稀疏字段提升为可验证关系

优先题组：

- 问题 1：`丁文伯 -> 深圳无界智航科技有限公司`
- 问题 7：企业家教育经历筛选的前置基础

交付：

- `company_roles` 关系语义细化：
  - `founder`
  - `executive`
  - `advisor`
  - `committee_or_association`
- 定向 cross-domain linker 增强
- 目标教授与目标企业的真实命中验证

真实验收：

- 目标教授对象包含正确结构化 company link
- 目标企业对象或回查链能反向证明该关联

### W3. Professor-to-Patent Link Mainline

目标：

- 建立可用的 `教授 ↔ 专利` 主链

优先对象：

- workbook 中能通过教授/企业链回查到的专利样本
- 已有企业专利较强的公司，例如 `优必选`

交付：

- professor 对象新增或稳定填充 `patent_ids`
- 从 paper/company/cross-domain 证据链构建 patent link
- patent number 精确命中回归

真实验收：

- 至少一批真实教授对象出现有效 `patent_ids`
- workbook 相关题组从 `fail` 变成 `partial` 或 `pass`

### W4. Exact Paper / Patent Identifier Coverage

目标：

- 修掉 workbook 中“特定论文 / 特定专利号命不中”的硬缺口

优先对象：

- `pFedGPA ...`
- `CN117873146A`

交付：

- `paper` 精确标题 / DOI / arXiv / 别名命中增强
- `patent` 精确编号命中增强
- 对应 release / retrieval 回归

真实验收：

- serving store 可精确命中指定论文和专利号
- workbook 问题 6、17 的关键实体检查通过

### W5. Workbook-Critical Company Coverage Expansion

目标：

- 把 workbook 反复点名、但当前共享库不存在的公司纳入定向采集范围

第一批名单：

- `深圳市普渡科技股份有限公司`
- `上海开普勒机器人有限公司`
- `云迹科技`
- `擎朗智能`
- `九号机器人`
- `嘉立创`
- `深南电路`
- `一博科技`
- `深圳市迈步机器人科技有限公司`

交付：

- 定向 company seed / refresh 流程
- 公司对象存在性回归
- 与 professor / patent / product fields 的最小连通性增强

真实验收：

- 上述目标企业在 serving store 中命中
- workbook 问题 2、5、7、14 的状态明显改善

### W6. Knowledge-Model Expansion for Research-Type Questions

目标：

- 正视 workbook `11-16` 题组超出当前模型边界的问题，并把它们收敛成显式知识建模任务

需要新增的最小模型层：

- `industry taxonomy`
- `company capability facets`
- `data-route taxonomy`
- `founder education / background`

策略：

- 不先追求“直接回答整道题”
- 先让底层结构字段进入 serving store
- 再用 coverage harness 验证这些题组从 `fail` 提升到 `partial`

真实验收：

- 新字段在目标公司样本上出现
- workbook 11-16 至少有一部分从纯失败变成部分可支撑

## Priority Order

当前优先级不是按题号，而是按**可验证性 + 对主线增益**排序：

1. `W0` coverage harness
2. `W1` professor serving continuity
3. `W2` professor-to-company
4. `W4` exact paper / patent identifier coverage
5. `W3` professor-to-patent
6. `W5` workbook-critical company expansion
7. `W6` knowledge-model expansion

原因：

- 先把“怎么判断修好”固化
- 再优先修最影响跨域问答的对象缺失与强关联缺失
- 最后处理需要扩模型的行业研究题

## TDD and Verification Posture

实现顺序必须保持：

1. 先补失败测试或基线验证脚本
2. 再做最小实现
3. 再跑真实数据 E2E / coverage audit
4. 只有真实报告翻绿，才进入下一批问题

禁止用 smoke test 代替 workbook coverage 验证。

## Risks

### 风险 1：把“缺实体”误判成“检索问题”

Mitigation:

- coverage harness 先区分：
  - serving store 不存在
  - serving store 存在但 retrieval 命不中

### 风险 2：把“历史 artifact 里有”误判成“产品可用”

Mitigation:

- 一律以当前 `released_objects.db` 和共享发布结果为准

### 风险 3：行业研究题拖垮前半段交付

Mitigation:

- 把 `W6` 明确拆成模型扩展工作流，不与实体/关联修复串在一起

## Real E2E Milestones

### M1. Workbook Baseline

- 跑出第一版 coverage audit 报告
- 固定当前各题组 `pass / partial / fail`

### M2. Professor Presence Recovery

- `丁文伯`、`王学谦` 进入 serving store
- 对应题组状态提升

### M3. Cross-Domain Link Upgrade

- 至少一个目标教授具备可验证 `company_roles`
- 至少一个目标教授具备可验证 `patent_ids`

### M4. Exact Identifier Recovery

- `pFedGPA ...`、`CN117873146A` 可精确命中

### M5. Company Expansion

- workbook 重点公司样本进入 serving store

### M6. Research-Question Partial Closure

- 11-16 题组至少一部分变为 `partial`

## Related Docs

- [实现测试集答案 Workbook 覆盖度验证](../solutions/workflow-issues/testset-answer-workbook-coverage-validation-2026-04-16.md)
- [教授数据采集在深圳有限 seed 场景下优先采用学校级 Adapter](../solutions/best-practices/professor-school-adapter-architecture-for-limited-shenzhen-seeds-2026-04-16.md)
- [Professor School-Adapter Architecture Plan](./2026-04-16-004-professor-school-adapter-architecture-plan.md)
