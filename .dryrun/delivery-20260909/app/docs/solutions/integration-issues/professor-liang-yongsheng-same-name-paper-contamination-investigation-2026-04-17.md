---
title: Professor Liang Yongsheng Same-Name Paper Contamination Investigation
date: 2026-04-17
category: docs/solutions/integration-issues
module: apps/miroflow-agent professor paper-linking release
problem_type: integration_issue
component: openalex_same_name_contamination
severity: high
tags: [professor-pipeline, paper-linking, openalex, same-name, release-gate, sztu]
---

# Professor Liang Yongsheng Same-Name Paper Contamination Investigation

## Scope

这份调查只回答 3 个问题：

1. `梁永生` 这条 released professor 数据里为什么会出现中医、创伤、矿业方向和论文。
2. 这些错误信息是官网抽取出来的，还是论文关联链路带进去的。
3. 当前主线代码是否还会把这类同名污染继续放进 `ready`。

不在本次结论里的问题：

- `梁永生` 是否存在多校同时任职。
- 如何完整建模多校同时任职。
- 当前 `direct-profile` URL 为什么会被解析成 `诚聘英才`。

后两项被记录为后续问题，但不是这次污染的直接根因。

## Confirmed Facts

### 1. 错误方向不是来自官网页面正文

真实官网页：`https://ai.sztu.edu.cn/info/1332/6055.htm`

页面 HTML / 可见文本里未命中以下词：

- `临床`
- `中医`
- `矿`
- `计算机网络`
- `信号处理`
- `副校长`

这说明 released 数据里的“中医综合疗法”“矿物加工”“找矿方向”等内容，不是 homepage crawler 直接从官网正文抽出来的。

### 2. 污染已经出现在上游 `paper_staging.jsonl`

批次产物：
- [paper_staging.jsonl](../../../logs/data_agents/professor_url_md_batch_c/033_深圳技术大学_人工智能学院/paper_staging.jsonl)
- [enriched_v3.jsonl](../../../logs/data_agents/professor_url_md_batch_c/033_深圳技术大学_人工智能学院/enriched_v3.jsonl)

在 `paper_staging.jsonl` 里，`anchoring_professor_id = PROF-42AFBC4C6403` 已经被挂上了明显错误的 OpenAlex 论文，例如：

- `中医综合疗法联合西医治疗溃疡性结肠炎患者对血清IL-23、25-（OH）D及YKL-40水平的影响`
- `重症创伤患者血浆白蛋白、前白蛋白水平与 C 反应蛋白水平变化相关性`
- `河北“金三角”地区金矿地质特征及找矿方向`
- `某铜、铅、锌多金属矿选矿试验研究`

说明污染发生在 `paper link / paper staging` 之前，而不是 release 最后一跳才写坏。

### 3. 直接调用 OpenAlex 会返回一个混杂作者结果

当前代码下，直接调用：

- `discover_professor_paper_candidates_from_openalex(professor_name='梁永生', institution='深圳技术大学', institution_id='I4210152380')`

得到：

- `author_id = https://openalex.org/A5004001809`
- `school_matched = False`
- `candidate_count = 1`
- `paper_count = 22`
- 论文列表同时包含网络、中医、矿业、行政管理等多个明显不一致方向。

这说明：

- OpenAlex 侧确实存在一个“同名聚合后非常脏”的作者结果。
- 这个结果本身并没有通过学校匹配。

### 4. 当前 `_discover_best_hybrid_result()` 已经拒绝这类结果

在当前代码下，本地复现：

- `_discover_best_hybrid_result(name='梁永生', institution='深圳技术大学', homepage_url='https://ai.sztu.edu.cn/info/1332/6055.htm')`

返回 `None`。

原因是：

- 当前 `paper_collector._should_reject_weak_discovery_result()` 在 institution registry id 存在时，会拒绝 `school_matched = False` 的外部结果。

因此，这个 **确切的 OpenAlex 脏作者结果**，按当前代码不会再被 hybrid 结果直接接收。

## Root Cause

这条 released 脏数据的根因已经可以明确拆成两层。

### Root Cause A: 外部学术源存在“同名混作者”结果

`梁永生` 对应的 OpenAlex 作者结果 `A5004001809` 同时包含多个显然不同学科方向的论文。

这不是官网抽取误差，而是外部学术源作者消歧失败带来的污染输入。

### Root Cause B: 旧批次产物把不可信外部论文继续传递到了 enriched / release

历史批次：
- [enriched_v3.jsonl](../../../logs/data_agents/professor_url_md_batch_c/033_深圳技术大学_人工智能学院/enriched_v3.jsonl)
- [quality_report.json](../../../logs/data_agents/professor_url_md_batch_c/033_深圳技术大学_人工智能学院/quality_report.json)

在这批产物里：

- 错误论文已经进入 `paper_staging`
- 错误研究方向、`paper_count=22`、错误 `top_papers` 已经进入 `enriched_v3`
- 该批 `quality_report` 仍然显示 `ready=3`

说明历史主线里至少存在过以下缺口：

1. 不可信 external paper set 被接收进入 paper staging
2. paper-derived 字段被继续写入 enriched profile
3. release / quality gate 没有把“不可信 paper signal”再次拦掉

## What This Does And Does Not Prove

### 已证明

- 污染不是来自官网正文。
- 污染来自 same-name external paper discovery。
- 当前 OpenAlex 对 `梁永生` 的作者结果确实是脏的。
- 当前代码对这一个 `school_matched=false` 的结果，已经会在 hybrid 选择阶段拒绝。

### 未证明

- `梁永生` 是否同时在多个学校任职，以及这些学校应不应该被当成允许的 paper affiliation。
- 当前所有同名教授污染都已被解决。
- 当前 release 路径即使拿到旧/脏 enriched 文件，也一定不会再次对外暴露错误论文字段。

## Multi-Affiliation Implication

用户补充说明：`梁永生` 可能确实存在多个学校同时任职。

这条信息改变的是**允许通过的证据类型**，不是“裸名字外部论文可以放宽”。

保守规则应当是：

- 多校同时任职必须由官方锚点支持
  - 官方详情页
  - 官方个人主页 / 课题组页
  - 官方挂出的 CV / publication page
  - 官方锚定的 Scholar / ORCID / DBLP
- 不能因为“这个名字在外部学术源上还能找到别的学校/别的领域论文”，就直接接受。

也就是说：

- `multi-affiliation` 允许跨当前 seed 学校去接受论文
- 但前提必须是 `officially anchored`
- 不能靠 bare OpenAlex same-name author result 自行放宽

## Current-Code Reality Check

我用当前代码做了一次真实 direct-profile E2E：

- [url_e2e_summary.json](../../../logs/data_agents/professor_url_md_e2e_liang_yongsheng_20260417/url_e2e_summary.json)

结果：

- 不再出现 `paper_count=22`
- 不再出现中医/矿业 `top_papers`
- 当前结果为 `quality_status = needs_enrichment`
- `paper_count = null`
- `top_papers_len = 0`

这说明：

- 这条“中医/矿业论文污染”在当前代码下 **没有直接复现**
- 但当前 run 暴露了另一个独立问题：这个 URL 被解析成了 `name = 诚聘英才`，且 `identity_passed = true`

因此当前状态应分开看：

1. **旧污染根因**：same-name external paper acceptance + release trust gap
2. **当前新问题**：direct-profile URL 的 name resolution / identity gate 仍有漏洞

不要把这两个问题混成一个结论。

## Mainline Design Implication

针对这类问题，主线代码应该做两层防线。

### 第一层：硬约束

对于 `openalex / semantic_scholar / crossref` 这类 external paper set：

- 有学校 registry id 时，默认要求 `school_matched=true`
- 如果需要接受跨学校论文，必须有 official anchor 指向第二任职机构或个人学术主页
- 不能因为“候选只有一个 exact-name author”就放过

### 第二层：主题一致性裁判

即使学校约束通过，仍然需要防“同名人被错误聚合到一个作者实体”这种情况。

对可疑 external paper set，应增加 topic consistency check：

- 输入：官方页里的 title / department / official research directions / official bio signals
- 输入：外部候选论文标题、venue、摘要摘要
- 输出：`consistent / suspicious / reject`

这里可以引入 LLM，但位置应当是：

- **external paper set acceptance** 的第二层裁判
- 而不是发布后再让 LLM 给脏数据写 summary

## Recommended Next Changes

1. 把 `paper trust metadata` 变成 release 前强校验项
   - 外部 paper signal 若无 trust marker，不得驱动 `ready`
2. 对 external paper set 加 `topic consistency` 校验
   - 优先规则/轻量启发式，必要时再让 LLM 介入
3. 对 multi-affiliation 只接受 official-anchored second affiliation
4. 对 release 增加兜底
   - 即使旧 enriched 文件混进来，也不能把不可信 external papers 直接展示给 web console

## Summary

这次 `梁永生` 的问题，不是官网抽错，而是 **same-name external paper contamination**。

当前代码已经能拒绝这一个明确的 `school_matched=false` OpenAlex 结果，但系统仍缺一层更稳的“paper trust + topic consistency”发布前防线。用户补充的“多校同时任职”不应导致裸名字外部论文放宽，而应推动主线改成：**只有官方锚定的多任职证据，才允许跨学校接受论文；其余外部论文候选还要再过主题一致性裁判。**
