---
title: Plan Portfolio Execution Roadmap
date: 2026-04-16
owner: codex
status: active
---

# Plan Portfolio Execution Roadmap

## Goal

把 `docs/plans/` 里的现有计划从“并列文档集合”收敛成一条实际可执行的路线图，明确：

1. 哪些计划已经完成
2. 哪些计划只是历史设计参考
3. 哪些计划仍然是当前执行 authority
4. 这些计划的依赖关系和执行顺序是什么

## Classification Rule

每个计划只允许落在以下三类之一：

- `completed`: 已完成，不再作为当前执行入口
- `reference`: 仍有价值，但只作为设计/历史/背景参考，不直接驱动当前排期
- `execution authority`: 当前仍驱动实现与验收的计划

## Plan Inventory

### Completed

1. `docs/plans/2026-04-04-001-feat-admin-console-plan.md`
   - 第一阶段 admin console 已交付
2. `docs/plans/2026-04-16-002-professor-direct-profile-identity-hardening-plan.md`
   - direct-profile / gemma4 / identity gate 主线已由真实 E2E 收口
3. `docs/plans/2026-04-16-005-workbook-coverage-gap-remediation-plan.md`
   - workbook 缺口修复已在真实 shared-store audit 上完成闭环
4. `docs/plans/2026-04-16-006-professor-workbook-closure-sequencing-plan.md`
   - workbook closure 的 sequencing 任务已完成并移交后续 wave
5. `docs/plans/2026-04-16-003-professor-pipeline-residual-hardening-plan.md`
   - Wave 4 discovery/fetch hardening 已在真实 targeted E2E 上完成收口
6. `docs/plans/2026-04-16-004-professor-school-adapter-architecture-plan.md`
   - Wave 5 school-adapter phase 1 已在真实 E2E 上完成收口

### Reference Only

删除策略：这些文档当前先不删。先统一标记为 `reference/superseded`，等对应 wave 完成且不存在再引用需求后，再评估是否删除。

吸收说明：`2026-04-05` v2 计划里提到的 DashScope provider，不再单独作为当前执行项；目前已由当前 gemma4 / 本地与线上 LLM 路线取代。若仓库里仍残留部分 DashScope provider 实现，应视为已取消的历史残留，不再继续扩展；当前处置策略是保留但不扩展，并在 Wave 4 工程硬化阶段统一决定是否删除或显式标 `deprecated`。

1. `docs/plans/2026-04-05-001-feat-professor-enrichment-pipeline-v2-plan.md`
   - v2 架构来源文档
   - 当前执行已转到 v3 与 2026-04-16 系列 closure plans
   - 其中 DashScope provider 单元明确取消，不再作为当前执行面
2. `docs/plans/2026-04-06-002-professor-pipeline-v3-redesign.md`
   - v3 的设计来源文档
   - 保留为架构参考，不直接当排期入口
3. `docs/plans/2026-04-06-003-feat-professor-pipeline-v3-implementation-plan.md`
   - 大部分内容已被落地或拆分进后续专项计划
   - 当前应视作 umbrella reference，而不是主执行面

### Execution Authority

1. `docs/plans/2026-04-16-007-plan-portfolio-execution-roadmap.md`
   - 当前 plan portfolio 的 meta authority，负责分类、波次排序、冲突裁决与完成定义
2. `docs/plans/2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md`
   - paper multi-source / exact identifier / evidence quality 的条件性专项执行计划
3. `docs/plans/2026-04-06-001-feat-admin-console-phase2-upgrade-plan.md`
   - Wave 6 的候选执行计划

## Authority Stack

当前的 authority stack 应固定为：

### Level 1: Portfolio Meta Authority

- `docs/plans/2026-04-16-007-plan-portfolio-execution-roadmap.md`

作用：
- 统一 `docs/plans/` 的分类、优先级和冲突裁决
- 规定各 wave 的进入条件、完成定义和回归处理规则
- 当 Level 3 计划在共享 schema / ID / evidence 语义上冲突时，由 007 做一次性裁决，并回写 shared spec

### Level 2: Next Wave Owner

- `docs/plans/2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md`

作用：
- 作为 Wave 5 完成后的下一个候选执行 owner
- 承接 paper multi-source / exact identifier / evidence quality 的后续增强

### Level 3: Queued Domain Plans

- `docs/plans/2026-04-06-001-feat-admin-console-phase2-upgrade-plan.md`

作用：
- 定义 Wave 5 之后的候选执行面
- 但不能越过 Level 1 的顺序控制
- 当 Level 3 计划在共享 contract 上冲突时，以 `docs/Data-Agent-Shared-Spec.md` 为第一裁决源；若 shared spec 仍未覆盖，再升级到本路线图一次性裁决并回写 spec

### Level 4: Completed Closure Records

- `docs/plans/2026-04-16-003-professor-pipeline-residual-hardening-plan.md`
- `docs/plans/2026-04-16-004-professor-school-adapter-architecture-plan.md`
- `docs/plans/2026-04-16-005-workbook-coverage-gap-remediation-plan.md`
- `docs/plans/2026-04-16-006-professor-workbook-closure-sequencing-plan.md`

作用：
- 记录已经完成的 wave/closure 验收口径和 closing evidence
- 不再作为当前执行入口

### Level 5: Historical Design Context

- `docs/plans/2026-04-05-001-feat-professor-enrichment-pipeline-v2-plan.md`
- `docs/plans/2026-04-06-002-professor-pipeline-v3-redesign.md`
- `docs/plans/2026-04-06-003-feat-professor-pipeline-v3-implementation-plan.md`

作用：
- 解释为什么现在长成这样
- 不再直接驱动排期和完成定义

## Wave Entry Preconditions

每个 wave 在宣布 `in_progress` 前，必须先产出同一套基线：

1. 运行一次完整 workbook coverage audit，并把报告落到新的 wave 目录
2. 复制当前共享库 `logs/data_agents/released_objects.db` 到对应 wave snapshot 目录
3. 记录当前 git commit SHA
4. 记录本 wave 依赖的真实 E2E / release artifact 路径

推荐目录格式：

- `logs/data_agents/wave_snapshots/<wave-id>/released_objects.db`
- `logs/data_agents/wave_snapshots/<wave-id>/workbook_coverage_report.json`
- `logs/data_agents/wave_snapshots/<wave-id>/git_sha.txt`

如果没有这套 pre-wave snapshot，后面的 regression rule 默认不算可执行，wave 不允许宣告开始。

## Current Wave Status

- `Wave 0`: completed via real validation and manual equivalent conclusion
- `Wave 1`: completed；`q1/q6/q9/q17` 已在真实 shared-store audit 上通过
- `Wave 2a`: completed；workbook-critical company coverage 已通过真实 release + consolidate + audit 收口
- `Wave 2b`: completed；`q11-q16` 已通过 company knowledge fields 进入真实 shared-store 并全部转为 `pass`
- `Wave 3`: reserved / merged into `Wave 2b`，无独立执行项
- `Wave 4`: completed；targeted real E2E round3 与 seed013/seed036 代表性真实验证均已通过
- `Wave 5`: completed；phase 1 adapter dispatch 已在 `wave5 matrix B round2` 与 `wave5 SYSU faculty family round2` 上完成真实 E2E 收口
- `Wave 6`: queued；仍等待下一执行 owner 与共享数据语义进一步稳定

## Execution Waves

### Wave 0. Finish In-Flight Real Validation

目标：先把当前正在跑的真实验证跑完，避免后续执行建立在不确定结论上。

当前项：
- `清华大学深圳国际研究生院` full-harvest real E2E

完成标准：
- 产出 `enriched_v3.jsonl`
- 明确 `丁文伯 / 王学谦` 是否进入 full-harvest 候选集和 release 结果
- 决定 `P0` 是 publish 问题还是 release gate 问题

超时/升级规则：
- 当前 `Wave 0` 的绝对升级时点固定为 `2026-04-18T00:00:00Z`。如果到该时点仍未产出 `enriched_v3.jsonl`，则升级为人工排障，不再无限等待。
- 人工排障 owner 为当前 Codex 执行面；最少要完成三步：检查目标 batch 目录下的 `current_enriched_v3.jsonl/enriched_v3.jsonl` 与 release artifacts、核对 `丁文伯 / 王学谦` 是否进入候选与 release gate 日志、必要时手工跑 publish 并在 shared store 里验证对象是否存在。
- 只有当人工排障明确得出以下等价结论之一时，才允许对 `q1/q9` 做收口判断：1) 两位教授已进入 release/publish 产物但 serving 刷新链断裂；2) 两位教授未进入 release 且已定位到具体 gate/pipeline bug；3) full-harvest 输入本身缺失该对象且已记录为 source/seed 问题。
- 升级后不阻塞其他已确定的 `Wave 1` 子线实现。
- 但 `q1/q9` 的最终放行仍以 `Wave 0` 的真实结果或上述等价人工排障结论为准。

### Wave 1. Professor / Workbook Closure

执行 authority：
- `2026-04-16-006`
- `2026-04-16-005`
- `2026-04-08-001`

目标：先把最影响真实问答支撑能力的对象存在性与强关联缺口收住。

`P0 professor serving continuity` 的定义固定为：

- 目标教授：`丁文伯`、`王学谦`
- 连续性含义：教授 released object 必须进入当前共享 `released_objects.db`，并能被 workbook 审计与共享检索稳定命中
- 最小验收：`q1/q9` 的 `professor_exists` 维度通过，且 shared store 查询能直接命中上述两位教授
- 这不是缓存、UI 或搜索排序问题；只关注 release -> publish -> serving store 的连续性

顺序：
1. `P0` professor serving continuity
2. `P1a` professor-company link
3. `P1b` exact paper identifier
4. `P1c` exact patent identifier

说明：`P1c` 当前只覆盖“既有 patent domain 数据里的精确命中与回填”，实现方式也限定为现有 patent import/release/search 路径上的 identifier backfill、匹配和发布校正；不在本波引入基于 professor web-search 的新专利发现，也不把 `cross_domain_linker` 扩成专利抓取器。如果后续需要“从 web search 为教授发现新专利并反向链接”，那是后续新增子计划，不混入当前 Wave 1。

这一波的完成标准：
当前进展（2026-04-16）：`q6` 与 `q17` 已通过真实 source backfill 收口为 `pass`，因此 `Wave 1` 当前仍未收口的 workbook 主缺口只剩 `q1` 与 `q9`；若后续回归导致 `q6/q17` 再次失效，仍视为本 wave 阻断项。

- `q1`: `pass`，即 `professor_exists` 与 `professor_company_link` 都通过
- `q6`: `pass`，即 `pFedGPA` 可在 shared store 中精确命中
- `q9`: `pass`，即 `王学谦` professor object 存在并可检索
- `q17`: `pass`，即 `优必选` 专利存在且 `CN117873146A` 可精确命中
- 对象存在性、company link、exact identifier 都能在 shared store 中命中
- 若某个 exact identifier 在上游 source 中根本不存在，应显式转入 source acquisition/backfill，而不是继续在 release/search 层空转

### Wave 2a. Workbook-Critical Company Coverage

执行 authority：
- `2026-04-16-005`

目标：补齐 workbook 点名而当前 serving store 缺失的公司对象。

顺序：
1. 先做 source presence 核验
2. 已有 source 的走 import -> release -> consolidate
3. 缺 source 的单独进入 acquisition backlog

这一波的完成标准：
- `q2`, `q5` 改善
- `q7` 至少从“对象不全”变成“对象齐全但字段不足”

### Wave 2b. Company Knowledge Fields

执行 authority：
- `2026-04-16-005`
- `2026-04-08-001`（如果字段扩展涉及 paper evidence）

目标：解决 `q7` 和 `q11-q16` 这种不能靠“对象存在”回答的问题。

最小字段：
- `founder_education / founder_background`
- `industry / sub_industry`
- `capability_facets`
- `data_route`
- `collection_methods / generation_methods`
- `scenario / product_type / modality`
- `evidence`

来源策略：
- 先优先复用现有 company source / XLSX 中可结构化字段。
- source 不足时，再补 `company enrichment / web extraction` 路径；这部分在进入 Wave 3 前必须补成独立可执行子计划，不能隐含跳过。
- 触发规则：在 Wave 2a 进入收尾且已明确哪些公司对象存在但字段不足后，立即创建独立子计划 `docs/plans/<date>-company-knowledge-fields-plan.md`，owner 为当前 Codex 执行面；子计划至少要定义 source mapping、字段 contract、enrichment strategy、真实数据验证样本。
- 时间要求：上述子计划必须在 `Wave 2a` 进入 closing verification 后 `2` 天内创建完成；若超时仍不存在，自动升级到本路线图 owner 进行优先级裁决。
- 前置门：`Wave 2b` 不能开工，直到上述子计划已创建、完成 review、并标记为 `active`。

这一波的完成标准：
- `q7` 提升
- `q11-q16` 至少部分从 `model_gap` 进入 `partial`

### Wave 3. Reserved / Merged Into Wave 2b Hardening

说明：

- 这里不再保留独立执行 wave。
- 原本可能拆成单独 wave 的“company knowledge fields 子计划固化与验收标准硬化”，已并入 `Wave 2b` 的前置门与完成标准设计中。
- 保留 `Wave 3` 编号只是为了避免后续历史文档和执行记录产生歧义。

### Wave 4. Professor Pipeline Hardening

说明：Wave 4-6 当前仍是方向性定义；在正式开工前，必须先把各自 completion criteria hardened 成可量化验收项，并追加回本路线图或对应 owner plan。该硬化动作最迟不得晚于 `Wave 2b` 进入 final verification；如果到那时仍未补完，后续 wave 自动阻断，owner 为当前 Codex 执行面。

执行 authority：
- `2026-04-16-003`

目标：在主缺口收住后，再清工程尾项，避免在主线仍不稳定时过早投入次要优化。

纳入：
- fetch policy state
- fallback page enqueue
- fetch 控制流去重
- research direction 边界硬化
- shared Playwright 生命周期边界
- DashScope provider 历史残留的最终处置（删除或显式 `deprecated`）

完成标准：
- 更宽真实 `URL.md` 样本无新回归
- 工程硬化项不再反复暴露为真实 E2E blocker

### Wave 5. School Adapter Phase 1

执行 authority：
- `2026-04-16-004`

结果：
- `IU1/IU2` 已完成：registry、旁路开关、顶层 dispatch 均已落地
- 真实验证已通过：`direct label round2`、`SYSU materials round4`、`wave5 matrix A`、`wave5 matrix B round2`、`wave5 SYSU faculty family round2`
- `sa -> ab` 首页重定向导致 fallback 被栏目候选饿死的问题已修掉，`sa` 现在能正确进入 faculty fallback 页面并发现教师

完成判断：
- Wave 5 phase 1 已完成，不再保持 active
- 若继续推进 `SZTU / SUAT-SZ`，应新建 phase 2 计划，不把新 scope 继续塞进 `2026-04-16-004`

### Wave 6. Admin Console Phase 2

执行 authority：
- `2026-04-06-001`

前置条件：
- quality semantics 稳定
- workbook coverage semantics 稳定
- company/professor/paper/patent 发布字段稳定

目标：
- 把已稳定的数据语义、安全地暴露到 admin console 的查询、筛选、批量操作和审计能力

完成标准：
- UI 不再追着未稳定的 schema 反复改
- 管理面和 pipeline 的语义一致

## Parallelization Rules

### Can Run In Parallel Now

1. Wave 0 的 real E2E 运行
2. Wave 1 的三条子线：
   - professor-company link
   - exact paper identifier
   - exact patent identifier

### Can Run In Parallel After Wave 1

1. Wave 2a company coverage
2. Wave 2b company knowledge fields

说明：
- 对于已经存在于 serving store 的公司，Wave 2b 可以先做字段扩展。
- 对于 Wave 2a 新补进来的公司，必须先完成 import/release/consolidate，再进入 Wave 2b。
- 对象集合边界以 `Wave 2a` 开始时的 serving store 快照为准：当时已经存在的公司可立即进入 `Wave 2b`；由 `Wave 2a` 新导入的公司，只有在其 import/release/consolidate 完成并通过 point-check 后，才获得进入 `Wave 2b` 的资格。
- Wave 2a/2b 的并行是按对象集合拆分，不是整个 wave 无条件同时放行。

### Should Not Run Early

1. Wave 5 的后续 family 扩展（若要继续）
2. Wave 6 admin console phase 2

原因：
- Wave 5 的 phase 1 已完成，后续扩展需要新的独立计划与完成定义
- Wave 6 仍依赖前面数据语义收稳

## Verification Artifacts

- Workbook 定义文件：`docs/测试集答案.xlsx`
- Workbook 覆盖审计脚本：`apps/miroflow-agent/scripts/run_workbook_coverage_audit.py`
- 默认共享库：`logs/data_agents/released_objects.db`
- 标准执行命令：`cd apps/miroflow-agent && . .venv/bin/activate && PYTHONPATH=. python3 scripts/run_workbook_coverage_audit.py --db-path logs/data_agents/released_objects.db --output-dir <dir>`

## Cross-Wave Regression Rule

- 每个 wave 宣布完成前，必须重跑完整 workbook coverage audit。
- 如果任何此前已 `pass` 的 query 回退，当前 wave 自动阻断，默认恢复到 pre-wave 快照或修复后重跑。
- 只有用户显式接受并记录 rationale，才允许带回归进入下一 wave。

## Definition Of “All Plans Executed”

`docs/plans/` 里的“全部执行完”不等于所有文档都逐字实现一遍，而是：

1. `completed` 类计划全部验收完毕
2. `reference` 类计划的有效内容已经被后续实现或后续执行计划吸收
3. `execution authority` 类计划按 wave 全部完成，且对应真实验收通过
4. 每个计划都能被明确标记为：
   - `completed`
   - `superseded by <newer plan>`
   - `cancelled with rationale`
5. `2026-04-16-006` 在其直接编排范围完成且真实验收通过后，必须同步转为 `completed`，避免继续充当悬空 authority
6. `2026-04-16-007` 在所有 wave 完成、所有计划已分类收口、且 shared spec/verification artifacts 已同步后，转为 `completed`

## Immediate Next Step
