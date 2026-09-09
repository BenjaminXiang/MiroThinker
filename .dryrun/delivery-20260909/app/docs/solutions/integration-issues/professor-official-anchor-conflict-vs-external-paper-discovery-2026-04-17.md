---
title: Professor Official Anchor Conflict vs External Paper Discovery
date: 2026-04-17
category: docs/solutions/integration-issues
module: professor-data-pipeline
problem_type: identity_anchor_conflict
status: active
severity: critical
tags: [professor, paper, openalex, official-site, disambiguation, ready-gate]
---

# Professor Official Anchor Conflict vs External Paper Discovery

## Problem Statement

当前 professor 主线存在一类高风险问题：

- 高校官网教师页已经给出了可用的身份与主题锚点
- 但后续外部论文发现、站点内递归抓取、以及摘要生成没有把这些锚点当成硬约束
- 最终把明显不一致的论文、研究方向、英文名、教育背景、奖项合并到同一个老师对象里
- 对象仍可能被发布成 `ready`

这不是单个学校的模板问题，而是主线的“证据优先级 + 冲突处理”设计问题。

## Why This Is Critical

一旦 professor-paper 关系错了，后续所有能力都会被污染：

- 教师画像
- 检索排序
- workbook 风格问答
- professor-company / professor-patent 推理
- web 控制台展示

这类错误不是“字段不完整”，而是“事实错误”。

## Confirmed Cases

### Case A: 梁永生

已在下列文档中完成调查：

- `docs/solutions/integration-issues/professor-liang-yongsheng-same-name-paper-contamination-investigation-2026-04-17.md`

结论：

- 上游 `paper_staging.jsonl` 被同名外部学术结果污染
- OpenAlex 结果本身 `school_matched=false`
- 当前新代码对这个确切路径已经比旧链更保守，但主线还没有形成统一的“官方锚点一致性 gate”

### Case B: 周垚

真实样本：`南方科技大学 / https://www.sustech.edu.cn/zh/faculties/zhouyao.html`

当前污染结果表现为：

- 官网锚点：
  - `研究助理教授`
  - `zhouy2021@sustech.edu.cn`
  - 官网页正文包含：`华中科技大学管理学博士、经济学学士、学生发展、高等教育院校影响力、教师发展`
- 最终合并结果却出现：
  - `name_en = Joseph Sifakis`
  - `Model checking / The algorithmic analysis of hybrid systems / BIP / Petri网`
  - `h_index = 57`
  - `citation_count = 14746`
  - `paper_count = 316`
  - `official_paper_count = 7913`
  - `publication_evidence_urls = scientific-achievements.html / colleges/index.html`

这说明 `周垚` 不是单一污染源，而是三类问题叠加：

1. 官网锚点没有约束外部论文结果
2. 泛学校站点页被误当成个人 publication evidence
3. 被污染结果仍然能流入 summary / ready

## Confirmed Evidence

### 周垚官网正文本身是有效锚点

已确认 `https://www.sustech.edu.cn/zh/faculties/zhouyao.html` 正文包含：

- `周垚`
- `研究助理教授`
- `zhouy2021@sustech.edu.cn`
- `华中科技大学管理学博士、经济学学士`
- `学生发展、高等教育院校影响力、教师发展`
- `第三届和第四届中国教育财政学术年会“青年优秀论文奖”`

因此，对这条样本来说，官网不是问题来源；官网应被视为主锚点。

### 周垚外部论文明显不一致

`paper_staging.jsonl` 中已确认出现大量形式化验证方向论文：

- `Model checking`
- `The algorithmic analysis of hybrid systems`
- `Specification and verification of concurrent systems in CESAR`
- `Symbolic Model Checking for Real-Time Systems`
- `On the synthesis of discrete controllers for timed systems`

这些论文与官网页正文中的高等教育/学生发展主题明显不一致。

### 周垚的“official publication evidence”也被泛页面污染

当前结果里：

- `publication_evidence_urls` 包含 `https://www.sustech.edu.cn/zh/scientific-achievements.html`
- `publication_evidence_urls` 包含 `https://www.sustech.edu.cn/zh/colleges/index.html`
- `official_paper_count = 7913`
- `official_top_papers` 甚至包含非论文文本：
  - `President IEEE Photonics Society, IEEE Fellow, OSA Fellow, SPIE Fellow`
  - `Raul Mario Ures De La Madrid`

这表明当前递归抓取把“学校级成果页 / 院系列表页”错误提升成了教师个人成果证据。

## Root Cause Class

这两个案例属于同一条主线问题：

**official anchor exists, but the pipeline does not enforce official-anchor consistency on later evidence.**

具体体现在：

1. `homepage_crawler` 允许过宽的 follow link / publication page 进入递归抓取
2. `official_publication_signals` 会接受泛站点页信号，只要被递归到了
3. `paper_collector` 对外部 academic discovery 的接受条件仍偏弱，缺少“与官网主题一致”这一层
4. `quality_gate` 目前没有把“官网锚点与外部论文强冲突”视为硬阻断
5. summary 生成会把已经被污染的字段进一步写实化，放大错误

## What Must Be True After Fix

修复后必须满足：

1. 官网教师页是硬锚点，不是普通 evidence
2. 站点级科研成果页、学院列表页、学校总成果页，不能自动成为单个教师的 publication evidence
3. 外部 academic source 只有在与官网锚点一致时，才能进入 verified relation / ready profile
4. 一旦出现“官网锚点 vs 外部论文主题明显冲突”，对象必须降级，不能继续 `ready`
5. summary 不得放大未验证或与官网冲突的信息

## Main Design Decision

对当前 STEM 主线，采用以下优先级：

1. `官网教师页正文`
2. `官网教师页明确锚定的个人主页 / 课题组页 / publication 子页 / CV`
3. `官网锚定的外部学术档案（ORCID / Scholar / DBLP 等）`
4. `裸外部 academic discovery`

其中：

- 1 和 2 可以直接参与事实构建
- 3 需要身份一致性校验
- 4 只能作为候选，且必须过一致性校验；若与 1 冲突，直接拒绝

## Immediate Repair Direction

主线修复应覆盖四个面：

1. 收紧站内递归抓取：不再把泛站点页误当教师 publication page
2. 引入 official-anchor consistency verifier：外部论文结果必须与官网锚点一致
3. 把冲突接入 quality gate：冲突即不得 `ready`
4. 用 targeted real E2E 验证：`周垚` 与 `梁永生` 必须都翻绿，且不能靠放松门槛

## Latest Verified State (Round 9, 2026-04-17 UTC)

基于同一批 4 条真实官方教师页样本重新跑 `run_professor_url_md_e2e.py` 后，当前状态已经收敛：

- `周垚`：`ready=1`，`paper_count=1`，只保留与官网锚点一致的教育方向论文，不再出现 `Joseph Sifakis / Model checking / BIP / Petri网`
- `梁永生`：`ready=1`，不再扩散出站内非人物 seed，也不再混入中医/矿物加工方向
- `吴亚北`：`ready=1`，真实 `paper_staging.jsonl` / `enriched_v3.jsonl` 中标题里的 MathML/HTML 残片已清理，`WSe2/CrI3`、`MoSi2N4`、`C3N` 等公式标题正常
- `吴日`：已从 `needs_enrichment` 翻为 `ready`。真实根因不是官网信息稀疏，而是 crawler 之前把 `homepage=https://faculty.sustech.edu.cn/wuri` 这种坏 personal homepage 放在 `profile_url=https://www.sustech.edu.cn/zh/faculties/riwu.html` 官方详情页前面，导致主锚点吃错页。主线修复后，官方详情页始终优先，`paper_count=20`、`top_papers_len=5`、`gate_passed=true`
- `吴日` 的 `official_top_papers` 里此前会误混“Angew. Chem ... 等期刊审稿人”这种非论文行；round9 已确认被过滤掉

对应真实验证目录：

- `logs/data_agents/professor_url_md_e2e_official_anchor_targeted_round9_20260417/`

### Additional Root Cause Learned

除了同名外部论文污染，`crawl seed precedence` 本身也是 official-anchor-first 主线的一部分。只要 `profile_url` 已经是 roster/discovery 得到的官方教师详情页，它就必须是递归抓取的主锚点；personal homepage 只能作为后续候选，不能反过来抢占主入口。否则即使官网正文很丰富，也会因为先吃到坏页/空页而把对象错误降成 `needs_enrichment`。

`paper title pollution` 也是这条主线的一部分。即使 professor-paper relation 判断正确，如果标题里仍残留 MathML / HTML entity / 被摊平的公式 token，web 控制台与 workbook 问答仍会展示低质量结果。

因此本轮主线修复除了 official-anchor-first disambiguation，还补进了统一 `clean_paper_title()`：

- external paper ingestion 时清洗
- official publication fallback 转 `RawPaperRecord` 时清洗
- paper release 入库前再次兜底清洗

当前已确认 abstract 中仍可能保留 `<sub>/<sup>`，但 `title` 字段在真实 round7 产物里已经是干净的。
