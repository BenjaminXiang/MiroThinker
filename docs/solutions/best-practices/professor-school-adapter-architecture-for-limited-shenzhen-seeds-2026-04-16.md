---
title: 教授数据采集在深圳有限 seed 场景下优先采用学校级 Adapter
date: 2026-04-16
category: docs/solutions/best-practices
module: apps/miroflow-agent professor pipeline
problem_type: best_practice
component: professor_crawling_architecture
severity: high
applies_when:
  - 教授 seed URL 数量有限，且主要集中在固定学校/院系官网
  - 通用 heuristics 已经堆积出大量 host-specific 例外分支
  - 真实 E2E 通过率尚可，但速度和 identity 稳定性仍有长尾
tags: [professor-pipeline, adapter, roster, discovery, e2e, shenzhen]
---

# 教授数据采集在深圳有限 seed 场景下优先采用学校级 Adapter

## Context

当前教授域的真实数据范围并不是开放互联网全量抓取，而是围绕深圳重点高校与院系的有限 seed URL：

- `docs/教授 URL.md` 当前共有 `41` 条 seed
- 学校集合稳定，主要集中在：
  - 清华大学深圳国际研究生院
  - 北京大学深圳研究生院
  - 南方科技大学
  - 深圳大学
  - 深圳理工大学
  - 哈尔滨工业大学（深圳）
  - 香港中文大学（深圳）
  - 中山大学（深圳）
  - 深圳技术大学

这意味着问题结构和站点集合都比“通用网页抽取”更可控。

## Guidance

在这种场景下，优先采用：

- **统一主 pipeline**
- **学校级 adapter**
- **必要时院系级 override**

而不是继续把更多 host-specific heuristics 堆进通用 discovery / roster / profile 逻辑里。

推荐结构：

1. 保留统一主链：
   - `seed -> roster discovery -> teacher detail page -> official personal homepage / lab page -> publication/CV/scholar signals -> paper/company/patent linking -> quality gate`
2. 将强站点耦合逻辑下沉到显式 adapter：
   - `roster/list page parsing`
   - `profile detail page detection`
   - `publication/homepage extraction`
3. 用 `host/cms -> adapter` 注册表来分发：
   - 例如 `*.sysu.edu.cn`、`*.cuhk.edu.cn`、`*.sztu.edu.cn`
4. 只在主 pipeline 中保留：
   - 通用 orchestration
   - fallback 顺序
   - 质量门与 cross-domain linking

这里最关键的一点是：

- **高校官网 URL 只是 discovery seed，不是最终画像页**
- 真正要抽取的主体是 seed 递归发现出的：
  - 官方教师详情页
  - 官方个人主页
  - 官方课题组主页
  - 官方挂出的 `CV / ORCID / Scholar / publication` 页面

如果采集停在 seed 页或院系列表页，系统会稳定丢掉：

- 教师自己维护的最新论文列表
- 更详细的个人介绍
- 更强的官方身份锚点
- 官方挂出的第二证据源链接

## Why This Matters

### 1. 当前代码其实已经出现“隐式 adapter”，只是没被显式建模

`roster.py` 里已经有大量 host-specific 逻辑，例如：

- `cuhk.edu.cn teacher-search`
- `sysu.edu.cn`
- `szu.edu.cn`
- `pkusz.edu.cn`
- `sustech.edu.cn`
- `sztu.edu.cn`
- `suat-sz.edu.cn`

这些规则已经证明：

- 站点结构差异足够大
- 单靠通用 heuristics 不够稳
- 系统已经在事实层面走向 adapter，只是结构上还没有承认它

### 2. 真实 E2E 的主问题已经从“主线身份误判”转成“稳定性和结构显式化”

最新已确认的真实 E2E 结论是：

- direct-profile guardrail 已稳定通过
- 主线 `工作履历 / Teaching / 专任教师` 这类误识别已经被收口
- `Wave 4` 的首轮扩样又额外证明：并发真实 E2E 会直接暴露 shared Playwright lifecycle 这类工程问题

这说明当前系统不再适合继续拿“已修掉的身份误判症状”作为 adapter 的主要动机。
现在更稳定的动机是：

- 显式管理 host-specific 规则，而不是继续在通用 discovery / roster / profile 里堆隐式分支
- 提高吞吐稳定性，减少无效 fallback 和绕路抓取
- 更可靠地从高校官网 seed 递归到官方个人主页、课题组页和 publication/CV 页面
- 让后续学校接入成本和调试成本下降

### 3. Adapter 能同时改善效率和正确性

学校级 adapter 的收益不是单一维度：

- **效率**：直接知道列表页、详情页、分页和噪声栏目，减少 fallback 和无效抓取
- **正确性**：减少把 `Teaching / 工作履历 / 师资力量 / 专任教师` 之类栏目词当人，并能更稳地沿官方介绍页递归到个人主页
- **可维护性**：把现有散落在 `roster.py`、`discovery.py` 的 host 特判收束到可测试模块

## When to Apply

优先采用学校级 adapter 的条件：

- seed URL 集合有限且稳定
- 目标站点来自少量高校站群
- 学校间 CMS 差异明显
- 真实 E2E 已经显示：
  - 大多数 URL 可过
  - 但长尾 host 速度慢、噪声多、identity 偶发误判

不适合直接上学校级 adapter 的场景：

- 目标站点高度开放、来源无限扩张
- 还在探索性抓取阶段，学校集合和页面结构都不稳定

## Examples

### Bad

继续在通用逻辑里加更多条件：

- `if hostname.endswith("sysu.edu.cn")`
- `if hostname.endswith("cuhk.edu.cn") and "teacher-search" in path`
- `if hostname.endswith("sztu.edu.cn") and path.endswith("/szdw.htm")`

结果：

- `roster.py` 逐渐变成隐式 registry
- discovery 与 extraction 耦合越来越深
- 每个新学校都需要在多个模块同时加条件

### Better

显式注册：

- `SysuProfessorAdapter`
- `CuhkShenzhenProfessorAdapter`
- `SztuProfessorAdapter`
- `SustechProfessorAdapter`

统一由 registry 决定：

- 谁处理这个 host
- 是否覆盖 roster 提取
- 是否覆盖 profile detail 提取
- 是否覆盖 publication 解析

### Best

只对收益最高的层先 adapter 化：

1. `roster discovery`
2. `profile page identity extraction`
3. `homepage/publication extraction`

不要一开始就把 paper/company/patent linking 也拆成学校级逻辑。

同时保持一个约束：

- 只要个人主页、课题组主页、CV、Scholar、ORCID 是从官方教师页沿链接递归发现出来的，就应当视为“官方链延伸页”纳入采集主链
- 外部搜索单独发现的同类页面，只能作为辅助证据，不应反过来覆盖官方身份锚点

## Recommendation

在当前深圳高校教授数据采集场景中，**学校级 adapter 应该成为主方向**。

第一刀不需要推翻现有 pipeline，而应该：

1. 先把 `roster.py` 中已有的 host-specific 规则显式化为 adapter registry
2. 让 `discovery.py` 和 `roster.py` 从“散落 heuristics”过渡到“通用主链 + 学校适配器”
3. 继续用真实 `URL.md` E2E 判断：
   - 吞吐是否改善
   - identity 长尾是否收敛
   - 新学校接入成本是否下降
   - 官方教师页到个人主页的递归链是否更稳定

## Related Issues

- [教授数据采集当前发现与操作经验汇总](../workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md)
- [教授 Pipeline 当前已收住与剩余旁路问题清单](../workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md)
- [Professor Pipeline Residual Hardening Plan](../../plans/2026-04-16-003-professor-pipeline-residual-hardening-plan.md)
- [实现测试集答案 Workbook 覆盖度验证](../workflow-issues/testset-answer-workbook-coverage-validation-2026-04-16.md)
