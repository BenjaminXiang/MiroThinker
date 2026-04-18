---
title: 官方挂出的 ORCID 应作为教授论文第二证据源
date: 2026-04-15
category: docs/solutions/best-practices
module: apps/miroflow-agent professor pipeline v3
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - 教授主页包含官方外链学术档案但 OpenAlex 同名消歧不稳定
  - 需要在不放宽质量门的前提下增强论文证据链
  - 计划后续接入 DBLP 或 CV PDF 作为官方第二证据源
tags: [professor-pipeline, orcid, second-evidence-source, official-links, homepage-crawler, paper-collector]
---

# 官方挂出的 ORCID 应作为教授论文第二证据源

## Context

教授域的主链已经可以靠：

- 官方主页 publication evidence
- OpenAlex / hybrid academic discovery
- 严格 Phase A gate

完成 PRD 验收。

但真实数据里仍然存在一个长期风险：有些教授主页明确挂了外部学术档案链接，主链却没有消费这条更强的身份锚点。这样会导致两类问题：

- OpenAlex 同名检索波动时，系统仍然只能回到更弱的裸名字搜索
- 主页已经提供了更强证据，但结构化数据里没有保存，后续增强无法复用

2026-04-15 的增强项证明，`ORCID` 是当前最适合先接入的第二证据源：

- 官方主页可直接挂出 ORCID 链接
- `https://pub.orcid.org/v3.0/<orcid>/works` 可直接读取公开 works JSON
- 身份由官方页锚定，不需要重新做人名搜索

## Current Implementation Boundary

在当前主线里，`ORCID` 的角色要收得很明确：它是一个**强可选锚点**，不是一个**必须存在的前提**。当前实现里对 `ORCID` 的使用边界是：

- `ORCID works API`：可以直接消费 `ORCID`，这是当前唯一真正按 `ORCID ID` 取论文的实现
- `Google Scholar / DBLP / CV PDF`：不能因为拿到了 `ORCID` 就假定能用同一个 ID 直接取数据；这些来源必须各自有官方锚定 URL
- `OpenAlex / hybrid`：当前仍然按姓名 + 机构保守发现，不把 `ORCID` 缺失视为失败，也不把 `ORCID` 强行扩散成所有来源的查询入口

因此，当前正确的来源优先级是：

1. 质量足够的官方 publication 页面
2. 官方锚定的 ORCID / Scholar / CV
3. verified OpenAlex / hybrid fallback

这条顺序解决的是质量问题，不是召回问题：官方链有证据时，外部 author search 不能反过来抢主链。

## Guidance

把“官方挂出的学术档案链接”拆成两个层次处理：

1. 在 homepage crawl 阶段先做结构化捕获。
   当前实现会把真实页面里的两类链接保存下来：
   - `scholarly_profile_urls`
   - `cv_urls`

2. 只有强身份锚点才进入 paper 主链。
   当前主链已经消费三类官方锚定来源：
   - `ORCID`
   - `Google Scholar profile`
   - `CV PDF`

   它们的进入条件都一样：
   - 链接必须先由官方教师详情页、官方递归到的个人主页/课题组页捕获
   - 然后才允许进入 paper 主链
   - 缺任何一种都不构成失败，只是少了一条可选强锚点

这条链的核心原则是：

- 不降低现有 quality gate 语义
- 不放宽同名模糊搜索
- 质量足够的官方 publication 证据优先于任何外部 author-search 结果
- 官方锚定的 ORCID / Scholar / CV 优先于 OpenAlex / hybrid author search

所以它的实际优先级是：

1. 质量足够的官方 publication 页面
2. officially-linked ORCID / Scholar / CV
3. verified OpenAlex / hybrid fallback
4. 否则失败或保持待增强

这条顺序的目的，是让“官方链已经给出的证据”先落成事实，再让外部 academic sources 做补充，而不是反过来让外部 author search 抢主链。

## Why This Matters

这条增强提升的是“质量上限”，不是“通过率假提升”。

如果直接放宽裸名字搜索，短期看起来会多出一些 paper_count，但会把同名误配重新带回来。官方挂出的 ORCID 不一样，它的身份链是：

`official profile -> ORCID -> works`

这条链对教授数据质量有两个直接好处：

- 当 OpenAlex 不稳定时，系统仍然有一条可信的论文证据路径
- 即使当前不需要 ORCID 兜底，链接也会沉淀在结构化字段里，后续 DBLP / CV PDF / retrieval explainability 都能复用

## When to Apply

- 主页含 `orcid.org/...` 外链时
- 页面还有 `Google Scholar / DBLP / CV.pdf` 等强学术档案链接时
- 需要增强 hard cases 的 paper-backed 能力，但不能放松质量门时
- 计划继续做官方第二证据源扩展时

## Examples

这轮的真实验证已经证明三种重要情况：

1. `段成国`：ORCID 真正进入了 paper 主链，而且只在官方 publication 抽取质量不足时接管主链。
   新的 targeted real E2E 产物在 [enriched_v3.jsonl](../../../logs/data_agents/professor_url_md_e2e_orcid_official_priority_round2_20260417/001_段成国/enriched_v3.jsonl)。
   当前记录里：
   - `scholarly_profile_urls = ["https://orcid.org/0000-0003-0527-5866"]`
   - `paper_count = 63`
   - `top_papers[*].source = "official_linked_orcid"`
   - 弱碎片 official-site titles 不再抢主链

2. `李海洲`：高质量官方 publication 仍然保留在主链上，不会被 ORCID/外部 author search 反向覆盖。
   新的 targeted real E2E 产物在 [enriched_v3.jsonl](../../../logs/data_agents/professor_url_md_e2e_orcid_official_priority_round2_20260417/002_李海洲/enriched_v3.jsonl)。
   当前记录里：
   - `paper_count = 5`
   - `top_papers[*].source = "official_site"`

3. `李海文`：ORCID 已被捕获，但不会错误覆盖更强的 OpenAlex 结果。
   产物在 [enriched_v3.jsonl](../../../logs/data_agents/professor_url_md_e2e_target_035_orcid_enhance_20260415/035_中山大学_深圳__先进能源学院/enriched_v3.jsonl)。
   当前记录里：
   - `scholarly_profile_urls = ["https://orcid.org/0000-0001-7223-1754"]`
   - `paper_count = 18`
   - `top_papers[*].source = "openalex"`

4. `黄建伟`：官方主页上的 `CV.pdf` 与 Scholar 外链已能稳定结构化捕获。
   实际验证产物在 [020_huangjianwei_links.json](../../../logs/data_agents/professor_homepage_link_capture_validate_20260415/020_huangjianwei_links.json)。
   当前结果：
   - `scholarly_profile_urls = ["http://scholar.google.com/citations?user=QQq52JcAAAAJ"]`
   - `cv_urls = ["https://jianwei.cuhk.edu.cn/Files/CV.pdf"]`

回归测试也覆盖了新行为：

```bash
PYTHONPATH=apps/miroflow-agent ./.venv/bin/python -m pytest -q -o addopts='' \
  apps/miroflow-agent/tests/data_agents/paper/test_orcid.py \
  apps/miroflow-agent/tests/data_agents/professor/test_homepage_crawler.py \
  apps/miroflow-agent/tests/data_agents/professor/test_paper_collector.py \
  apps/miroflow-agent/tests/data_agents/professor/test_pipeline_v3.py \
  apps/miroflow-agent/tests/data_agents/professor/test_models_v2.py
```

这轮结果是 `86 passed in 2.36s`。

## Related

- [教授 PRD 收口必须以真实数据的 Phase A 严格门禁为准](./professor-prd-real-data-phase-a-gate-2026-04-14.md)
- [学科感知的 professor quality gate](./discipline-aware-professor-quality-gate-2026-04-14.md)
- [官方 publication 证据必须进入教授论文 gate](../integration-issues/official-publication-evidence-fallback-2026-04-14.md)
