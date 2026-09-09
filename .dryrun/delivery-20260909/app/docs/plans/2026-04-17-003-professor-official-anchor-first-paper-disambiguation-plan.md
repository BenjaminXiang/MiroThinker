---
title: Professor Official-Anchor-First Paper Disambiguation Plan
date: 2026-04-17
owner: codex
status: active
origin:
  - docs/solutions/integration-issues/professor-official-anchor-conflict-vs-external-paper-discovery-2026-04-17.md
  - docs/solutions/integration-issues/professor-liang-yongsheng-same-name-paper-contamination-investigation-2026-04-17.md
  - docs/plans/2026-04-17-001-professor-stem-reset-and-storage-redesign-plan.md
---

# Professor Official-Anchor-First Paper Disambiguation Plan

## Goal

修复当前 professor 主线中“官网锚点存在，但外部论文结果越权覆盖”的问题，使 STEM 教师的论文关系、研究方向、英文名、教育背景与 ready 判定都受官网锚点约束。

## Scope

本计划只覆盖 professor/paper 主线，不处理 company/patent 新需求。

### Progress Update (2026-04-17 UTC)

当前这条 plan 的 targeted mainline 已经有最新真实 E2E 结果：

- `梁永生` 不再漂移成 `诚聘英才/国内合作` 等站内非人物节点，且不再合并中医/矿物加工污染
- `周垚` 保留官网锚点中的管理学/学生发展画像，不再被 `Joseph Sifakis / Model checking` 论文集覆盖
- `吴亚北` 的真实 paper 标题已去掉 MathML/HTML 残片，`WSe2/CrI3`、`MoSi2N4`、`C3N` 等公式标题在真实产物里已变干净
- `吴日` 已从 `needs_enrichment` 翻为 `ready`；根因不是官网信息稀疏，而是主线此前错误地把坏的 personal homepage 放在官方详情页前面。修复后改为 `profile_url` 官方详情页优先，`paper_count=20`、`top_papers_len=5`、`gate_passed=true`
- `吴日` 的 `official_top_papers` 里此前还会误混“期刊审稿人”这类非论文行；本轮又补了 official publication title 过滤，真实 round9 产物里已只保留论文条目

对应真实验证目录：

- `logs/data_agents/professor_url_md_e2e_official_anchor_targeted_round9_20260417/`

这说明 targeted official-anchor-first 主线已经收住；当前剩余工作不再是这 4 条样本上的冲突判定，而是把同样的约束继续扩到更大批次和后续重建发布链。

重点覆盖：

- `homepage_crawler`
- `paper_collector`
- `quality_gate`
- `summary_generator`（必要时）
- 定向真实 E2E 验证与回归测试

## Non-Negotiable Rules

1. 官网教师页正文信息视为高优先级锚点。
2. 站内泛学校页、学院总成果页、院系列表页，不得自动升级为单个教师的 publication evidence。
3. 裸外部 academic discovery 不能在与官网主题冲突时进入 verified profile。
4. 冲突样本宁可 `needs_review / needs_enrichment`，也不能 `ready`。
5. 不盲跑旧逻辑 E2E；只有主线实现改到位后，才跑定向真实 E2E。

## Repair Strategy

### P0. 建立“官网锚点优先”事实约束

目标：先把“什么算教师本人官方事实”固定下来。

实施：

- 从官网教师页正文提取 `official_anchor_profile`：
  - title
  - email
  - bio text
  - explicit education
  - explicit awards
  - explicit research topics
- 这个 anchor profile 不再只是 enrichment 输入，而要成为后续 paper/discovery 的约束输入。
- contract 固定为 `OfficialAnchorProfile`，至少包含：
  - `source_url: str`
  - `title: str | None`
  - `email: str | None`
  - `bio_text: str`
  - `research_topics: list[str]`
  - `education_lines: list[str]`
  - `award_lines: list[str]`
  - `work_role_lines: list[str]`
  - `english_name_candidates: list[str]`
  - `topic_tokens: list[str]`
  - `sparse_anchor: bool`
- `topic_tokens` 仅由主官网教师页正文生成，并随 profile 一起传递到 `paper_collector` / `quality_gate`，避免模块间漂移。

文件：

- `apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py`
- `apps/miroflow-agent/src/data_agents/professor/models.py`

测试：

- `apps/miroflow-agent/tests/data_agents/professor/test_homepage_crawler.py`

### P1. 收紧站内 follow link 与 publication evidence 选择

目标：阻断 `scientific-achievements.html`、`colleges/index.html` 这类泛页被当成教师 publication 证据。

实施：

- follow-link 规则收紧：
  - `publication_page` 必须满足教师级锚定，而不是只满足关键词命中
  - 同域但无教师级路径亲和度或无教师姓名上下文的页面，不递归
  - LLM 选中的链接仍需经过确定性二次过滤，LLM 不能越权放行 teacher-unscoped 页面
- sitewide / college-wide classifier 明确化：满足以下三类信号中的任意两类，即视为聚合页，不得作为单教师 publication evidence：
  - URL / 页面标题信号：URL path 或 H1/H2 命中 `scientific-achievements`、`research achievements`、`科研成果`、`学院成果`、`colleges/index`、`院系总览` 等聚合模式
  - 教师锚点缺失：页面标题、主标题、正文都缺失教师姓名/英文名/URL slug 线索
  - 聚合规模异常：提取出的成果数量明显超出单教师合理范围；`official_paper_count > 500` 仅作为辅助 corroboration，不单独构成聚合页判定
- publication signal 规则收紧：
  - page 被判为 sitewide / college-wide 时，不能提供 `paper_count` 或 `top_papers`
  - 只有 homepage inline publication block 或 teacher-specific publication subpage 可以进入 `official_publication_signals`

文件：

- `apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py`

测试：

- 新增 `test_homepage_crawler.py` 负例：
  - `scientific-achievements.html` 不得给单个教师贡献 `official_paper_count`
  - `colleges/index.html` 不得产出 `official_top_papers`
  - `周垚` 官网详情页正文仍可保留管理学/学生发展锚点

### P2. 外部 academic discovery 增加官网一致性校验

目标：让外部论文发现先经过“是否与官网锚点一致”的审查，再决定是否进入主链。

实施：

- 构建 `official topic fingerprint`：只从官网教师页正文提取，不包含递归页面内容。输入包括 bio / research directions / education / awards / work roles。
- fingerprint 规则写死：
  - 保留长度 >= 3 的中文词和长度 >= 4 的英文词
  - 去掉学校/学院/通用头衔/导航词以及高频学术空词 stopwords；stopword 集合固定到测试 fixture 中
  - 若官网研究方向或 bio 可提取的主题 token 少于 3 个，则视为 `sparse_official_anchor`；该阈值先按严格默认实现，后续用真实批次分布再调优
- 对 external candidate result 做两层判定：
  1. deterministic conflict check
     - `name_conflict`：若官网已给出英文名，或可从 URL / 页面标题稳定导出英文名，则 candidate author display name / aliases 必须同时匹配 surname 与 given-name token；对于常见中文姓氏映射到拼音的场景，不允许只靠 surname 通过
     - `topic_conflict`：当官网 topic token >= 3，且 candidate 至少有 5 篇论文时，按 citation 降序并保留一个近两年代表作，从前 15 篇 candidate papers 的 title/keyword/venue token 生成 candidate fingerprint；若 overlap ratio < 0.15，且 candidate 侧 dominant tokens 与官网 token 零交集，则判冲突
     - `profile_conflict`：官网教育/工作锚点出现固定学科族关键词，而 candidate corpus 的 dominant tokens 持续落在另一固定学科族时，判冲突；学科族映射表固定在代码与测试 fixture 中，不在运行时自由发挥
  2. LLM consistency verifier（仅用于 deterministic 仍无法判定的样本）
     - 输入：官网锚点摘要 + candidate top papers + candidate author metadata
     - 输出：`consistent | conflict | uncertain`
     - 运行契约：`temperature=0`；仅缓存 `consistent` / `conflict` 结果，缓存 key 为 `(official_anchor_hash, candidate_hash)`；超时、限流、JSON 解析失败一律记为当前运行的 `uncertain`，但不写入缓存，下次重跑可重试
- 只有 `consistent` 才允许 external discovery 进入 verified paper enrichment
- `conflict` 直接拒绝
- `uncertain` 降级，不进 ready
- `sparse_official_anchor` 特判：若官网 topic token < 3，且无官网 publication / 官方锚定 scholar profile / CV 进一步佐证，则 external discovery 不能把对象提升到 `ready`，最多到 `needs_enrichment`

文件：

- `apps/miroflow-agent/src/data_agents/professor/paper_collector.py`
- 可新增轻量模块：`apps/miroflow-agent/src/data_agents/professor/paper_consistency.py`

测试：

- 新增 `test_paper_collector.py`：
  - `周垚` 官网教育/方向 vs `Joseph Sifakis` 论文集 -> reject
  - `梁永生` 电子信息/高校任职 vs 中医/矿物加工论文集 -> reject
  - 正常 STEM 老师 official-topic-consistent external result -> pass

### P3. 把冲突接入 quality gate

目标：即使上游仍有漏网之鱼，ready gate 也不能放行冲突样本。

实施：

- quality gate 增加 `official_anchor_conflict` 检查
- 一旦触发：
  - `quality_status != ready`
  - failure reason 明确输出 `official_anchor_conflict`
- `sparse_official_anchor` 且缺第二证据源时，不能 `ready`
- summary 生成不得使用被标记冲突的 external paper signals
- `run_professor_url_md_e2e.py` 仅负责把新的 `failure_reason / conflict_flags / sparse_anchor` 透出到报告，不复制 gate 逻辑

文件：

- `apps/miroflow-agent/src/data_agents/professor/quality_gate.py`
- `apps/miroflow-agent/src/data_agents/professor/summary_generator.py`
- `apps/miroflow-agent/scripts/run_professor_url_md_e2e.py`

测试：

- `test_quality_gate.py`
- `test_run_professor_url_md_e2e_gate.py`

### P4. 定向真实 E2E 验证矩阵

目标：用真实样本判定问题是否真的修掉，而不是只靠单测。

#### Negative controls

- `周垚`：不能再出现 `Joseph Sifakis / Model checking / 形式化验证` 合流
- `梁永生`：不能再出现中医/矿物加工污染

#### Positive controls

- `吴亚北`：官方 publication + external metadata 仍然通过
- `吴日`：同校真实老师样本，paper 主线不能被误伤
- 另选 1-2 个已通过的工科/理科老师，确认不是“通过一刀切禁用外部论文”来达成

通过条件：

1. 负例不再 `ready`
2. 正例继续 `ready`
3. `paper_staging.jsonl` 不再出现明显冲突论文进入 verified path
4. web 控制台中 professor JSON 不再出现这类强冲突画像

## TDD Execution Posture

这轮按严格 `RED -> GREEN -> REFACTOR` 执行。

每个 implementation slice 必须遵守：

1. 先补失败测试
2. 确认测试确实红
3. 再写最小实现
4. 跑定向回归
5. 最后再跑真实 E2E

## Validation Order

1. `homepage_crawler` 负例单测
2. `paper_collector` 冲突拒绝单测
3. `quality_gate` 不放行冲突样本单测
4. 定向真实 E2E：`周垚 + 梁永生 + 正例样本`
5. 若定向真实 E2E 过，再扩到小批量 STEM 样本
6. 记录前后 `ready / needs_review / needs_enrichment` 桶变化，并产出 flipped-professors diff；只有正例未被大面积误伤时才允许发布

## P5. 旧污染记录与派生产物重处理

目标：修完主线后，不让历史污染继续停留在 staging / serving 产物里。

实施：

- 定位已知污染样本：至少包含 `周垚`、`梁永生` 及本轮真实 E2E 暴露的同类样本
- 将本轮目标目录中的 `paper_staging.jsonl`、`enriched_v3.jsonl` 与 shared serving 里对应 professor/paper 派生对象先归档到 quarantine/timestamp 路径，再由新主线结果替换
- 使用新主线对这些样本重跑，并只发布新结果
- 若样本仍落在 `conflict` 或 `sparse_official_anchor`，保留为 `needs_review/needs_enrichment`，不得为追求覆盖率强行 ready

验收：

- web 控制台与 shared store 中不再残留旧污染画像
- targeted E2E 输出与 serving 发布结果一致

## Claude Review Strategy

先 review 计划，不拿大工作区去撞大 prompt：

1. review 问题文档
2. review 本 plan
3. 实现后再 review 代码 diff

如果本地 Claude CLI 长时间静默，优先继续缩 scope，而不是把问题误判成代码逻辑失败。

## Definition of Done

满足以下条件才算这条主线完成：

- `周垚` 与 `梁永生` 的真实 E2E 样本已不再被错误 external paper 污染
- 冲突样本不会 `ready`
- `sparse_official_anchor` 样本在缺第二证据源时不会被误提为 `ready`
- 正常 STEM 正例没有被误伤
- 旧污染 staging / serving 产物已按新主线重处理
- 问题文档和 plan 文档都已更新为完成态或最新状态
- Claude cross-review 已完成，并且有效 findings 已处理或显式记录
