---
title: Professor Pipeline Residual Hardening Plan
date: 2026-04-16
owner: codex
status: completed
reviewed_by: claude_previous_pass
---

# Professor Pipeline Residual Hardening Plan

## Goal

## Completion Update

到 2026-04-16 UTC，这份 Wave 4 计划已经按真实数据 E2E 收口。

完成证据：

- [wave4 targeted round3](../../logs/data_agents/professor_url_md_e2e_wave4_discoveryfix_targeted_round3_20260416/url_e2e_summary.json)
  - `SUSTech root seed / SZU hub / CUHK teacher-search = 3 / 3 gate_passed`
- [wave4 seed036](../../logs/data_agents/professor_url_md_e2e_wave4_agentfix_seed036_20260416/url_e2e_summary.json)
- [wave4 seed013](../../logs/data_agents/professor_url_md_e2e_wave4_diag_seed013_20260416/url_e2e_summary.json)
- 针对性回归：`87 passed`

本轮实际收口的内容包括：

1. per-run fetch-policy learned state reset
2. seed fallback scheduling 收窄
3. fetch control-flow 去重与 blocked-200 error reporting
4. shared Playwright thread-local state 与 stale-browser retry
5. CUHK helper public API 对齐

`research_directions` 边界 heuristics 在本轮扩展真实 E2E 中没有再暴露为 blocker，因此保持为后续 watchpoint，而不是阻断本轮完成定义的 open issue。

在不重新打开已经收住的主线问题前提下，继续收敛教授 pipeline 当前剩余的工程硬化问题，并且始终以真实数据 E2E 结果决定下一步方向。

这轮计划的判断标准不是单测绿，而是：

1. 真实 direct-profile 回归批次持续通过
2. `docs/教授 URL.md` 的扩展样本批次持续通过
3. 新扩展批次不再暴露已知残余问题，或暴露后能被定位到新的单一主因

## Current Baseline

已确认收住的主线问题：

- Gemma4 调用链不再是 direct-profile blocker
- detail-profile 不再把 `工作履历` 之类 section heading 当姓名
- root homepage 不再把 `Teaching` 之类导航词当教授姓名
- L1 失败对象不会再带着 `quality_status=ready`
- official publication fallback 不再误吃 footer/copyright 文本

已通过的真实 E2E 基线：

- `logs/data_agents/professor_url_md_e2e_direct_identityfix_round5_20260416/url_e2e_summary.json`
- `logs/data_agents/professor_url_md_e2e_urlmd_sample20_22_round2_20260416/url_e2e_summary.json`

## Archived Scope (Preserved For History)

以下各项保留为这轮 wave 开始时的原始问题清单，用于说明修复范围；它们不再代表当前 open issues。当前收口结论以本页 `Completion Update` 和相关真实 E2E 产物为准。

### R1. Fetch policy learned-host state is process-global

Current code:

- `apps/miroflow-agent/src/data_agents/professor/discovery.py`
  - `_learned_browser_first_hosts`
  - `_learned_reader_first_hosts`
  - `_resolve_fetch_policy()`
  - `_remember_browser_first_host()`
  - `_remember_reader_first_host()`

Risk:

- 单次异常会把 host 记成 `browser_first` 或 `reader_first`
- 这个偏置会污染后续同进程的其他 seed
- 当前真实 E2E 还没把它打成 blocker，但它会让后续批次结果带有运行时历史依赖

Desired state:

- learned fetch policy 只在一次 discovery run 内生效，或至少能被显式重置
- 真实 E2E 在不同批次之间不受前一批次失败历史影响

### R2. Seed fallback page scheduling is broader than needed

Current code:

- `apps/miroflow-agent/src/data_agents/professor/discovery.py`
  - `_discover_recursive_seed()`
  - `_enqueue_seed_fallback_pages()`

Risk:

- `seed` 首页面已经抽到候选页面时，fallback 入口页仍会被调度
- 虽然队列层有去重，但会扩大抓取面，增加无关页面进入发现流程的机会
- 这会放大目录页噪声，并给后续 identity/paper 路径带来不必要干扰

Desired state:

- fallback 入口页只在真实需要时进入队列：
  - 首页抓取失败
  - 首页未抽到候选页面
  - 首页超过深度或明确需要学院级备用入口

### R3. Reader/browser fallback path still has duplicated work

Current code:

- `apps/miroflow-agent/src/data_agents/professor/discovery.py`
  - `fetch_html_with_fallback()`
  - `_render_text_with_reader()`
  - `_resolve_fetch_policy()`

Risk:

- `reader_first` 路径在总失败时仍可能重复请求 reader/direct
- 即使不直接导致错误，也会拉长真实 E2E 运行时间，并让 fetch telemetry 更难解释

Desired state:

- 每条 fetch path 只有一条清晰的控制流
- 失败时能准确知道是 direct、reader 还是 browser 问题
- 同一个 URL 在一次 fetch 中不做无意义重复尝试

### R4. Research-direction heuristics are still fragile on edge content

Current code:

- `apps/miroflow-agent/src/data_agents/professor/profile.py`
  - `_extract_research_directions()`
  - `_looks_like_research_directions()`
- `apps/miroflow-agent/src/data_agents/professor/direction_cleaner.py`

Risk:

- 当前主线样本已恢复，但 blocker/cleaner 仍是关键词式规则
- 新学校页面里，交叉学科、人文教育类、或包含课程语汇的真实研究方向，仍可能被误滤

Desired state:

- `research_directions` 的过滤规则更偏结构化上下文，而不是简单词命中
- 对已知通过样本不回归
- 新增真实边界样本时能稳定区分“课程信息”与“研究方向”

### R5. Shared Playwright lifecycle is safe enough now, but not explicit enough

Current code:

- `apps/miroflow-agent/src/data_agents/professor/discovery.py`
  - `_get_shared_playwright_browser()`
  - `_shutdown_shared_playwright_browser()`
  - `_SHARED_BROWSER_RENDER_LOCK`

Risk:

- context leak 已修掉，但浏览器共享策略仍是模块级全局状态
- 后续扩大 E2E 面或并发运行时，问题会更难归因

Desired state:

- 浏览器共享策略与并发边界更明确
- 单测能覆盖生命周期，不依赖长时间跑批次才暴露问题

## Non-Goals

- 不重新处理已经收住的 Gemma4 `http/https`、stale `API_KEY` 问题，除非真实 E2E 再次出现新证据
- 不放宽质量门，不用更松的规则掩盖数据问题
- 不在没有真实 E2E 失败证据的情况下盲目重写 professor pipeline 其他模块

## Strategy

这轮不直接按代码 residual list 顺序盲修，而是按下面的顺序推进：

1. 先扩大真实 E2E 覆盖面，确认当前还会暴露什么
2. 用暴露出来的真实症状决定优先级
3. 对能从代码静态确认的工程尾项做最小安全修复
4. 每做完一组修复，就回到真实 E2E 验证

## Workstreams

### W0. Expand real-data E2E surface before more code edits

Purpose:

- 用真实 `docs/教授 URL.md` 扩大验证面，确认当前 residual issues 是否已经在更广批次里复现

Execution:

1. 保留已通过的 direct-profile 回归批次作为 smoke-equivalent guardrail
2. 扩展 `docs/教授 URL.md` 到更宽的定向样本集，覆盖：
   - direct profile root homepage
   - detail profile page
   - list/search roster page
   - 官方 publication fallback 依赖较重的页面
3. 将新增失败按症状聚类：
   - identity failed
   - required fields missing
   - paper backed failed
   - fetch instability / timeout

Decision rule:

- 如果新批次暴露出比 R1-R5 更高频的新主因，先转向修新主因
- 如果没有新主因，进入 W1-W4 工程硬化

### W1. Discovery fetch-state isolation and fallback scheduling cleanup

Scope:

- `apps/miroflow-agent/src/data_agents/professor/discovery.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_roster_validation.py`

Changes:

1. 把 learned fetch-policy state 从模块级全局状态收成 run-scoped state 或可重置状态
2. 缩窄 `_enqueue_seed_fallback_pages()` 触发时机
3. 为 fallback 调度新增正反用例：
   - 首页抽到候选时不再调度 seed fallback
   - 首页失败或无候选时才调度

Verification:

- 单测覆盖 fetch-policy 记忆与 fallback 调度
- 真实 E2E 对比修复前后：
  - 已通过样本不回归
  - 访问页面数不异常膨胀

### W2. Fetch control-flow dedup and telemetry hardening

Scope:

- `apps/miroflow-agent/src/data_agents/professor/discovery.py`
- 相关测试文件按实际落点补充

Changes:

1. 梳理 `fetch_html_with_fallback()` 控制流，避免同一 URL 在单次 fetch 内无意义重复尝试
2. 统一 `fetch_method` / error reporting，使报告能精确区分：
   - `cache`
   - `direct`
   - `reader`
   - `browser`
3. 对 `reader_first`、`browser_first`、`direct_first` 三条路径补失败和降级测试

Verification:

- 单测断言每条路径的尝试顺序和最终 `fetch_method`
- 真实 E2E 抽查日志，确认没有同一 URL 的重复 reader/direct 波动

### W3. Research-direction extractor hardening

Scope:

- `apps/miroflow-agent/src/data_agents/professor/profile.py`
- `apps/miroflow-agent/src/data_agents/professor/direction_cleaner.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_profile_extraction.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_direction_cleaner.py`

Changes:

1. 为边界研究方向补 characterization tests：
   - 含 `课程` 但确属研究方向的样本
   - 人文/教育类研究方向
   - 交叉学科长短句
2. 将 blocker 规则尽量收敛到结构化上下文判断，而不是单纯 substring 命中
3. 保持当前已通过样本不过滤回归

Verification:

- 单测覆盖边界样本
- 真实 E2E 选择一组已知容易受 research-direction 影响的学校样本回归

### W4. Shared Playwright lifecycle hardening

Scope:

- `apps/miroflow-agent/src/data_agents/professor/discovery.py`
- 对应测试文件按实现落点补充

Changes:

1. 明确 shared browser 生命周期与锁边界
2. 如有必要，引入可测试的 browser manager 包装，而不是继续在模块级直接操控对象
3. 补最小生命周期测试，至少覆盖：
   - browser lazy init
   - repeated render reuse
   - shutdown idempotence

Verification:

- 单测断言生命周期与幂等行为
- 真实 E2E 不以“更快”为完成标准，而以“更稳定且不回归”为标准

## Execution Order

1. W0 扩展真实 E2E 面
2. W1 discovery state / fallback 硬化
3. W2 fetch control-flow 硬化
4. W3 research-direction 硬化
5. W4 shared browser 生命周期硬化
6. 扩展后的真实 E2E 复跑
7. Claude cross-review
8. 文档更新与经验沉淀

## Test-First Posture

这轮继续保持严格 TDD：

- 先用失败测试刻画残余问题
- 再做最小实现
- 最后用真实数据 E2E 判断修复是否真的有价值

对于仅能在真实站点上暴露的问题：

- 单测负责刻画已知故障形态
- 真实 E2E 负责决定是否继续投入该方向

## Real-Data E2E Ladder

### E1. Guardrail batch

固定回归：

- `http://materials.sysu.edu.cn/teacher/162`
- `https://jianwei.cuhk.edu.cn/`

Purpose:

- 防止 direct-profile 主线回归

### E2. Targeted URL.md batch

基于 `docs/教授 URL.md` 选取更宽但仍可控的真实样本：

- 至少覆盖 root-homepage、detail-page、roster/list、publication-heavy 四类

Purpose:

- 判断 residual issue 是否在主路径上真实可见

### E3. Broader confirmation batch

当前两层都稳定后，再扩到更大样本量。

Purpose:

- 决定本轮问题是否真正收口

## Success Criteria

本轮计划完成时，应满足：

1. 已通过的 direct-profile 回归批次继续全绿
2. 扩展的 `docs/教授 URL.md` 真实样本批次没有再暴露当前已知残余问题
3. 如果出现新失败，其主因已被收敛成新的单一问题文档，而不是混杂在旧问题里
4. 本轮新增修复都已沉淀到 `docs/solutions/` 或更新到现有问题清单文档

## Deliverables

- 更新后的残余问题计划文档
- 对应测试与代码修复
- 新的真实 E2E 产物目录与结论
- 更新后的 `docs/solutions/workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md`
- 至少一份新的经验沉淀文档
