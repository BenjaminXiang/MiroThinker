---
title: 实现测试集答案 Workbook 覆盖度验证
date: 2026-04-16
category: docs/solutions/workflow-issues
module: agentic-rag shared knowledge base
problem_type: validation_report
status: historical_baseline
component: workbook-coverage
severity: high
tags: [testset, workbook, professor, company, patent, paper, cross-domain, coverage]
---

# 实现测试集答案 Workbook 覆盖度验证

## 结论

参见总览文档：[教授数据采集当前发现与操作经验汇总](./professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md)。

这份文档记录的是 **修复前的 baseline 缺口**，不是当前状态。其后的 closing 结果已经在真实 shared-store audit 上收口：`16 pass + 1 out_of_scope`，最新报告见 `logs/data_agents/workbook_coverage_final_post_review_20260416/workbook_coverage_report.json`。

从 [测试集答案.xlsx](../../../docs/测试集答案.xlsx) 的问题集合出发，**这份文档描述的是系统在 closing 之前最初不能完整满足数据收集需求的状态**。

当前应以 post-review audit 为准，而不是以下 baseline 描述。最新 closure 结论是：

- workbook 当前已收口为 `16 pass + 1 out_of_scope`
- 当前 released objects audit 已足以支撑 workbook 的对象可用性层面需求
- 下面各题的 `不满足 / 部分满足` 仅表示修复前 baseline，不再构成当前 backlog

为避免未来回到旧结论，当前只保留以下 caveat 为 **语义层而不是 coverage 层**：

- `q4` 的“同名/近名企业消歧”仍是部分显式证明，不应误写成 coverage 缺口
- `q6` 的论文对象已存在，但 professor-paper 显式反链仍偏弱
- `q7` 的“早稻田背景”筛选更像教育背景建模问题，不是对象存在性问题
- `q8/q9/q10` 里的市场评价或“大牛”判断仍属于 synthesis，不应夸大成硬覆盖保证

## 验证方法

本次验证不从“模型能不能胡出来”判断，而从**当前数据底座是否足以支撑回答**判断：

1. 读取 [测试集答案.xlsx](../../../docs/测试集答案.xlsx) 中的 17 组问题
2. 以当前 serving store [logs/data_agents/released_objects.db](../../../logs/data_agents/released_objects.db) 为准核验实体存在性
3. 检查 professor/company/patent/paper 四域对象是否覆盖关键实体与关键关联
4. 参考最新教授域真实 E2E 结果，确认 professor 数据主链当前状态

## Historical Baseline Snapshot

以下快照是 closing 之前的 historical baseline，不代表当前 shared store：

- `company`: `1025`
- `paper`: `5482`
- `patent`: `1930`
- `professor`: `125`

当前 professor 关联覆盖：

- `91 / 125` 教授带 `top_papers`
- `11 / 125` 教授带 `company_roles`
- `0 / 125` 教授带 `patent_ids`

这意味着：

- `教授 ↔ 论文` 已经有基本可用性
- `教授 ↔ 企业` 还是稀疏覆盖
- `教授 ↔ 专利` 当前基本不可用

## 关键实体存在性核验

当前 serving store 命中情况：

| 实体/线索 | 当前共享库状态 | 结论 |
| --- | --- | --- |
| `丁文伯` professor | 未命中 | 当前不能支撑问题 1 |
| `王学谦` professor | 未命中 | 当前不能支撑问题 9 |
| `深圳无界智航科技有限公司` | 已命中 | 可部分支撑问题 4 |
| `华力创科学（深圳）有限公司` | 已命中 | 可较好支撑问题 8 |
| `深圳爱博合创医疗机器人有限公司` | 已命中 | 可较好支撑问题 10 |
| `pFedGPA ...` paper | 未命中 | 当前不能支撑问题 6 |
| `CN117873146A` patent | 未命中 | 当前不能支撑问题 17 的第二问 |
| `优必选` patents | 已命中多条专利 | 可部分支撑问题 17 的第一问 |
| `深圳市普渡科技股份有限公司` | 未命中 | 当前不能支撑问题 2 |
| `上海开普勒机器人有限公司` | 未命中 | 当前不能支撑问题 2 |
| `云迹科技 / 擎朗智能 / 九号机器人` | 未命中 | 当前不能支撑问题 2 |
| `嘉立创 / 深南电路 / 一博科技` | 未命中 | 当前不能支撑问题 5 |
| `帕西尼感知科技（深圳）有限公司` | 已命中 | 只能部分支撑问题 7/14 |
| `深圳市迈步机器人科技有限公司` | 未命中 | 当前不能支撑问题 7/14 |

## 按 Workbook 题组评估

### 问题 1：`介绍清华的丁文伯` → `他是否有参与哪些企业的创立`

状态：**[Baseline] 不满足**

原因：

- 当前 serving store 中没有 `丁文伯` professor object
- 当前 serving store 中也没有 `丁文伯 -> 深圳无界智航科技有限公司` 的 founder/company link
- 历史 artifact 里曾出现过 `丁文伯`，例如：
  - `logs/debug/professor_release_e2e_20260402T180748Z/released_objects.jsonl`
  - `logs/data_agents/professor/search_service/professor_released_objects.jsonl`
- 但这些不是当前共享检索库的一部分，所以对产品态无效

这说明当前问题不是“完全没采过”，而是“没有稳定进入当前 serving store”。

### 问题 2：酒店送餐机器人供应商及上下文追问

状态：**[Baseline] 不满足**

原因：

- workbook 明确要求 `普渡 / 开普勒 / 云迹 / 九号 / 擎朗`
- 当前 company 共享库中这些关键企业都未命中
- 问题还要求：
  - 上下文承接
  - 深圳总部过滤
  - 产品能力级判断（如机械臂按电梯）
- 当前 company 数据模型也没有稳定覆盖到“产品能力颗粒度”

### 问题 3：深圳涉黄赌毒地点

状态：**[Baseline] 不纳入数据收集覆盖评价**

原因：

- 这是政策/安全回答问题，不是知识库数据采集覆盖问题

### 问题 4：无界智航企业信息与同名消歧

状态：**[Baseline] 部分满足**

原因：

- 当前共享库中有 `深圳无界智航科技有限公司`
- 当前对象包含：
  - `industry`
  - `key_personnel`
  - `technology_route_summary`
- 但 workbook 还要求：
  - 同名/近名企业消歧
  - 明确不能串到不相关主体
- 当前共享库里没有另一家“同名/近名”的完整对照实体，因此消歧链无法被充分验证

### 问题 5：PCB 打板推荐与深圳企业筛选

状态：**[Baseline] 不满足**

原因：

- workbook 指定的 `嘉立创 / 一博科技 / 深南电路` 当前共享库均未命中
- 这类问题本质上是行业全景推荐，不是当前 company xlsx 骨架的覆盖强项

### 问题 6：特定论文 `pFedGPA ...` 的详情与链接

状态：**[Baseline] 不满足**

原因：

- 当前 paper 共享库中没有该论文
- 当前 professor/paper 数据也无法把它稳定挂到 `丁文伯 / 李阳`

### 问题 7：毕业于早稻田、且在深圳做机器人行业的企业家

状态：**[Baseline] 不满足**

原因：

- 这要求同时具备：
  - 企业人物信息
  - 教育经历
  - 行业标签
  - 深圳地域筛选
- 当前 company 数据能覆盖部分 key personnel，但缺少系统性的 `founder education` 结构化字段

### 问题 8：华力创科学企业信息、产量特点、市场竞争力

状态：**[Baseline] 部分满足，接近可用**

原因：

- 当前 company 共享库中存在 `华力创科学（深圳）有限公司`
- 已覆盖：
  - 公司名称
  - 官网
  - key personnel
  - 技术路线摘要
- 但 workbook 里的答案还需要更深的：
  - 量产特点
  - 市场竞争力
  - 技术原理展开
- 当前对象更像“公司画像摘要”，还不是“深度行业研报”

### 问题 9：王学谦评价及是否属于“大牛”

状态：**[Baseline] 不满足**

原因：

- 当前 serving store 中没有 `王学谦` professor object
- 历史 artifact 里有过 `王学谦` 记录，但未稳定进入当前共享库

### 问题 10：爱博合创企业情况、创始人信息、市场评价

状态：**[Baseline] 部分满足，接近可用**

原因：

- 当前 company 共享库中存在 `深圳爱博合创医疗机器人有限公司`
- 已覆盖：
  - 公司主体
  - key personnel
  - 技术路线摘要
- 仍欠缺：
  - 市场评价类字段的系统化结构
  - 更强的融资/里程碑/临床进展结构化覆盖

### 问题 11-16：具身智能数据路线、合成数据、深圳厂商路线等行业研究类问题

状态：**[Baseline] 整体不满足**

原因：

- 这些题本质是“行业研究 / 方法论归纳”型问题
- 当前系统的数据底座更偏：
  - 单公司画像
  - 单教授画像
  - 单专利 / 单论文记录
- 但缺少：
  - 统一的“数据路线 taxonomy”
  - 厂商级数据路线字段
  - 研究型知识汇总层

也就是说，这不是 retrieval 调参就能补出来的缺口，而是知识建模范围还没覆盖。

### 问题 17：优必选有哪些专利 → 专利 `CN117873146A` 详情

状态：**[Baseline] 部分满足**

原因：

- 当前 patent 共享库能命中多条 `深圳市优必选科技股份有限公司` 专利
- 说明“按申请人列专利”这条线是可用的
- 但当前共享库里没有 `CN117873146A`
- 所以第二问“特定专利号精确详情”当前不满足

## 对“教师-论文-专利-企业关联”的专项判断

这是 workbook 最关键、也是你特别强调的点。当前状态如下：

- `教师 ↔ 论文`：**可用但不均匀**
  - `91 / 125` 教授已有 `top_papers`
- `教师 ↔ 企业`：**可用性偏弱**
  - 只有 `11 / 125` 教授带 `company_roles`
  - 而且部分 `company_roles` 实际是协会/机构/委员会，不全是狭义企业创业关系
- `教师 ↔ 专利`：**当前不可用**
  - `0 / 125` 教授带 `patent_ids`

这意味着：

- workbook 里像“丁文伯参与创立了哪些企业”这类题，目前不能靠当前共享库稳定支撑
- “教授有哪些论文”这类题，比“教授关联了哪些企业/专利”明显更成熟

## 当前最重要的两个缺口

### 1. Serving store 与历史有效 artifact 断层

像 `丁文伯`、`王学谦` 这类教授，历史上在 debug / release artifact 中出现过，但当前共享库中不存在。

这不是单纯“采不到”，而是：

- 采集产物
- 发布产物
- 当前 serving store

三者之间还存在断层。

### 2. Workbook 里的题目范围已经超过当前数据建模范围

当前数据建模强项是：

- professor profile
- company profile
- patent record
- paper record

但 workbook 里很多题需要：

- 行业全景清单
- 创始人教育背景
- 具身智能数据路线 taxonomy
- 产品能力级细节
- 多轮上下文与实体消歧

这要求的不只是“多抓一点数据”，而是：

- 增加新的结构化字段
- 扩大 company source coverage
- 建立领域研究层
- 强化 cross-domain linking

## 结论性判断

如果以 [测试集答案.xlsx](../../../docs/测试集答案.xlsx) 作为需求基线，当前系统可以支撑的主要是：

- 单公司画像
- 部分公司人物信息
- 部分专利列表
- 部分教授-论文关系

当前系统还不能稳定支撑的主要是：

- 教授强画像（如 `丁文伯`、`王学谦`）在当前 serving store 中的稳定可得性
- 教授 ↔ 企业创业关系
- 教授 ↔ 专利关系
- 精确论文/专利号命中
- 行业全景推荐型问题
- 具身智能数据路线研究型问题

所以，从 workbook 问题集合的角度看，**当前实现只满足了部分数据收集需求，还没有达到可全面支撑这些问题的程度**。

## 建议的下一步

1. 先修 `professor artifact -> shared serving store` 的断层，把已验证可用的教授对象稳定发布进共享库。
2. 把 `教授 ↔ 企业` 链路从“少量 company_roles”提升为“创业/任职/合作关系可区分”的结构化关联。
3. 补 `教授 ↔ 专利` 主链，否则 workbook 里的跨域问题永远不稳。
4. 对 `paper` 和 `patent` 增加精确 ID / 编号命中回归集，例如：
   - arXiv / DOI
   - patent number
5. 如果要覆盖 workbook 里的行业研究题，需要单独建设：
   - 具身智能厂商清单层
   - 数据路线 taxonomy 层
   - 市场/产品能力字段层

## Related Docs

- [Workbook Coverage Gap Remediation Plan](../../plans/2026-04-16-005-workbook-coverage-gap-remediation-plan.md)
- [教授数据采集在深圳有限 seed 场景下优先采用学校级 Adapter](../best-practices/professor-school-adapter-architecture-for-limited-shenzhen-seeds-2026-04-16.md)
