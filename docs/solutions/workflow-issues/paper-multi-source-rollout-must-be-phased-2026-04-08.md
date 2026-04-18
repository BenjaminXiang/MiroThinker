---
title: 论文多源采集必须先锁定 Phase A，再进入 ORCID / DOI 增强
date: 2026-04-08
category: docs/solutions/workflow-issues
module: apps/miroflow-agent professor paper collection
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - 审查论文多源采集设计稿与当前代码是否一致
  - 准备把 OpenAlex、ORCID、Crossref、Semantic Scholar、DBLP 一次性接入教授论文链路
  - Phase A 的 institution registry、OpenAlex 主路径或 E2E 还没有稳定通过
  - 计划新增 paper contract 字段或新的 identity/quality 语义
tags: [paper-collection, multi-source, phase-a, openalex, institution-registry, orcid, doi-enrichment, e2e]
---

# 论文多源采集必须先锁定 Phase A，再进入 ORCID / DOI 增强

## Context

这轮迭代重新对照了 [`docs/Paper-Collection-Multi-Source-Design.md`](../../Paper-Collection-Multi-Source-Design.md) 和当前仓库实现，结论不是“设计方向错了”，而是“实现前置条件还没锁死，直接上完整多源融合会把风险叠到主链路上”。

当前代码已经有一版可运行的骨架：

- 教授主页阶段会补部分 `name_en`
- 论文采集优先走 `OpenAlex -> Semantic Scholar -> Crossref` 的 hybrid fallback
- 教授质量门已经开始把“有无论文信号”纳入发布判断

但当前仓库还没有三个承重件：

- **9 校 OpenAlex institution registry** 还没真正落地，`institution_id` 精确过滤前提不成立
- **Paper contract / release contract** 还不能稳定承载设计稿里要新增的 `funder`、`license`、`tldr` 等增强字段
- **identity uncertainty -> quality / release 语义** 还没有明确契约，设计稿里的 `low_confidence` 无法直接映射到现有教授发布语义

这意味着如果在 Phase A 还没稳定之前就推进 ORCID anchoring、DOI enrichment、DBLP 补全和 contract 扩展，结果通常不是“更快完成”，而是把主路径、数据契约和验收口径一起变成移动靶。

## Guidance

论文多源采集的实施顺序要固定成两段：

第一段先只做 **Phase A**，目标是“稳定产出 paper-backed professor”，而不是一次性做完所有学术增强。

- 先锁 9 校 institution registry，并把它接到 OpenAlex author discovery 主路径
- 保留当前可运行的 hybrid fallback，但定位成主路径兜底，不宣称已经完成 multi-source fusion
- 强化 `name_en` / query candidate 生成，让 OpenAlex 主路径命中率先稳定下来
- Phase A 期间不要扩共享 Paper contract，也不要引入新的教授 `quality_status` 语义
- Phase A 的验收以真实 E2E 和人工抽样精度为 gate，不以“代码里已经有 source client”作为完成标志

第二段才进入 **Phase B / P3**，也就是增强层：

- ORCID anchoring
- Crossref / Semantic Scholar 的 DOI 级补全
- DBLP 作为 CS 条件源补全
- 真实 collector 层 multi-source merge
- Paper contract 扩展，以及 identity uncertainty 的 release 语义设计

推进规则要更硬一点：

- **P0-2 + P1 没跑通 E2E，不进 P3**
- **institution registry 还没验真，不写死 guessed institution ID**
- **contract 还没扩，不收集只能在 collector 内部丢失的增强字段**

环境侧也有一条要固定下来：

- 如果 institution ID、ORCID 或外部 academic source 的关键标识在当前 sandbox / network 条件下无法验证，就把它当作“待验证依赖”，通过批准过的浏览或提权命令获取真实值；不要为了推进进度硬编码猜测结果

## Why This Matters

这条分阶段规则本质上是在保护三件事：

- **主链路稳定性**：先证明 OpenAlex 主路径真的能稳定把教授和论文连起来，再叠更复杂的消歧和补全
- **数据契约一致性**：contract 还没扩时就采增强字段，只会制造“采到了但发布层丢掉”的假完成
- **验收口径可信度**：如果一边改 source、一边改 schema、一边改 quality 语义，E2E 失败时几乎无法快速定位问题到底在采集、融合还是发布

这轮评审里已经出现了这个信号：旧设计稿把 ORCID、institution registry、DOI enrichment、DBLP、contract 扩展和验证协议一次性打包，导致吞吐估算、前提依赖和成功标准都不够自洽。把范围切成 Phase A / Phase B 后，实施顺序和回滚边界才变得清晰。

## When to Apply

- 设计稿同时引入多个外部数据源、identity 规则和 schema 变更时
- 当前代码只有 hybrid fallback，但还没有真实 collector 层 merge 时
- 一个迭代想同时改 discovery、enrichment、release contract 和 quality gate 时
- E2E 还没有证明“至少能稳定产出带论文数据的 `ready` 教授”时

## Examples

这轮迭代里，当前仓库和设计稿之间最关键的 before / after 是：

- **Before**：把 ORCID、DOI enrichment、DBLP、contract 扩展都视为当前实现的一部分，按“完整 multi-source”叙述推进
- **After**：明确当前状态只是 “OpenAlex primary + hybrid fallback 的 Phase A 骨架”，先补 registry、主路径和 E2E，再进增强阶段

对应到当前代码，已经存在的能力与尚未具备的能力应当明确区分：

- 已存在：[`paper/hybrid.py`](../../../apps/miroflow-agent/src/data_agents/paper/hybrid.py)、[`paper/openalex.py`](../../../apps/miroflow-agent/src/data_agents/paper/openalex.py)、[`paper/crossref.py`](../../../apps/miroflow-agent/src/data_agents/paper/crossref.py)、[`paper/semantic_scholar.py`](../../../apps/miroflow-agent/src/data_agents/paper/semantic_scholar.py)
- 未存在：新的 institution registry、ORCID client、DOI enrichment collector、collector 层 multi-source merge、可承载增强字段的扩展 contract

文档层也做了同样收口：

- [`docs/Paper-Collection-Multi-Source-Design.md`](../../Paper-Collection-Multi-Source-Design.md) 被重写成可执行的 Phase A / Phase B 版本
- [`docs/plans/2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md`](../../plans/2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md) 把 `P0-2 -> P1 -> E2E -> P3` 的顺序明确写死

如果这条规则没有被文档化，后续最容易重复发生的事是：看到仓库里已经有 OpenAlex/Crossref/S2 三个 client，就误判“多源采集已经完成”，然后直接把 P3 的复杂度叠回一个尚未稳定的主路径上。

## Related

- [教授论文缺口审查与修复计划](../data-quality/professor-paper-gap-root-cause-and-remediation-plan-2026-04-07.md) — 解释为什么 `ready` 必须和论文信号绑定
- [教授 URL 全量收口](./professor-url-md-ready-paper-closure-2026-04-08.md) — 真实 E2E 要如何验证“教授 + 论文”链路已经打通
- [Paper Collection 多源设计](../../Paper-Collection-Multi-Source-Design.md) — 本轮已改写为可执行的分阶段设计稿
- [Paper Collection 多源优先级计划](../../plans/2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md) — 具体执行顺序与 gate
