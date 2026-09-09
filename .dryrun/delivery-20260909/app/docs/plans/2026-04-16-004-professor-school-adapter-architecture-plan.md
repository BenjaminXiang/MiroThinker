---
title: Professor School-Adapter Architecture Plan
date: 2026-04-16
owner: codex
status: completed
---

# Professor School-Adapter Architecture Plan

## Goal

在不破坏现有教授 pipeline 主链的前提下，把当前分散在 `roster.py` / `discovery.py` 中的 host-specific 规则显式化为**学校级 adapter**，提升：

- 真实 E2E 吞吐稳定性
- host-specific 结构差异下的正确性与可解释性
- 新学校/新院系接入时的可维护性

## Current Evidence Refresh

到 2026-04-16 UTC，最新真实 E2E 已把当前优先级钉住：

- `wave5 matrix A` 已 `6/6 gate_passed`
  - [wave5 matrix A](../../logs/data_agents/professor_url_md_e2e_wave5_matrix_a_20260416/url_e2e_summary.json)
- `SYSU materials faculty/staff` 修前曾错误放出 `教师队伍`，修后已回到真实教师 `陈文多`
  - 修前 baseline：
    [wave5 matrix B baseline](../../logs/data_agents/professor_url_md_e2e_wave5_matrix_b_20260416/url_e2e_summary.json)
  - 修后单点复验：
    [SYSU materials round4](../../logs/data_agents/professor_url_md_e2e_sysu_materials_round4_20260416/url_e2e_summary.json)
- `李立浧 main.htm` 这类 `姓名 + 直达个人页 URL` seed 已在主 pipeline 收口
  - [direct label round2](../../logs/data_agents/professor_url_md_e2e_direct_label_postfix_round2_20260416/url_e2e_summary.json)
- `CUHK teacher-search` correctness 稳定，但仍是明显慢尾 host family
  - baseline 可见 [wave5 matrix B baseline](../../logs/data_agents/professor_url_md_e2e_wave5_matrix_b_20260416/url_e2e_summary.json)

从这组证据出发，下一波 adapter 优先级应调整为：

1. `SYSU faculty/staff` family
2. `CUHK teacher-search`
3. `SZTU / SUAT-SZ` heading/card mixed roster family
4. `SUSTech` 仅保留 watchpoint，不作为当前第一优先

## Current Phase-1 Progress

到当前代码状态，phase 1 已经不是纯计划：

- `apps/miroflow-agent/src/data_agents/professor/school_adapters.py` 已落地最小 registry / matcher / bypass 语义
- `apps/miroflow-agent/src/data_agents/professor/roster.py` 顶层已经接入 first-match-wins dispatch
- 第一批 adapter 先接了 `CUHK teacher-search` 与 `SYSU faculty/staff` 的最小包装
- fresh 回归：`12 passed`（adapter + CUHK/SYSU targeted tests），`140 passed`（更宽 professor targeted suite）
- fresh 真实 E2E：`wave5 matrix B round2 = 6 / 6 gate_passed`

这意味着 phase 1 的 `IU1/IU2` 已经完成。后续 fresh 真实 E2E 又补齐了：

- [wave5 SYSU faculty family round2](../../logs/data_agents/professor_url_md_e2e_wave5_sysu_faculty_family_round2_20260416/url_e2e_summary.json)
  - `saa / sa = 2 / 2 gate_passed`

因此这个 phase 1 计划的 closing 条件已经满足。后续如果继续做 `SZTU / SUAT-SZ`，应单独开 phase 2 计划，而不是继续把本计划保持为 active。

## Problem Frame

当前现实不是“没有学校特判”，而是“学校特判已经存在，但结构上是隐式的”。

最明显的位置是：

- `apps/miroflow-agent/src/data_agents/professor/roster.py`
- `apps/miroflow-agent/src/data_agents/professor/discovery.py`

现状问题：

1. host-specific 条件散落在通用逻辑里
2. 难以判断某个学校到底由哪一层负责
3. 新学校接入时容易在多个模块重复加条件
4. 当前剩余问题更像 `paper-backed / publication-evidence / roster structure` 长尾，而不是 broad identity 主线崩溃

## Scope

这轮只做**学校级 adapter 架构第一阶段**，不做全链推倒重写。

纳入范围：

- `roster discovery`
- adapter registry
- 首批学校 adapter 接入
- 只在 `roster.py` 这一层做显式 dispatch

暂不纳入范围：

- `discovery.py` 全量学校分发重构
- `profile/detail page identity extraction` adapter 化
- `homepage/publication` adapter 化
- `paper/company/patent` 的学校级 adapter
- 行业研究类知识建模
- professor/company/patent serving coverage 提升

## Design

### 1. 保持统一主 pipeline

主链不变：

- `seed parsing`
- `discovery`
- `roster extraction`
- `profile extraction`
- `homepage/publication`
- `paper/company/patent linking`
- `quality gate`

adapter 只负责“站点结构差异”，不负责改变主线语义。

### 2. 引入学校级 adapter registry

新增一个显式 registry 模块，例如：

- `src/data_agents/professor/school_adapters.py`

最小接口建议：

- `matches(source_url: str) -> bool`
- `extract_roster_entries(html, institution, department, source_url) -> list[DiscoveredProfessorSeed] | None`

设计原则：

- adapter 命中时优先处理
- adapter 返回 `None` 时回退通用逻辑
- adapter 不改动质量门和发布语义
- `first-match-wins`

### 3. 第一阶段 adapter 选择

第一阶段不再只做 `CUHK`，而是两条并行优先线：

1. `SYSU faculty/staff` family
   - 目标：避免通用 roster / direct-profile heuristics 再把通用 faculty 页判错
   - 第一批样本：
     - `http://materials.sysu.edu.cn/faculty/staff`
     - `http://saa.sysu.edu.cn/faculty`
     - `http://sa.sysu.edu.cn/zh-hans/teacher/faculty`
2. `CUHK teacher-search`
   - 目标：把已有强 host-specific 路径收敛到 adapter registry，并为后续慢尾优化做结构承接
   - 第一批样本：
     - `https://sse.cuhk.edu.cn/teacher-search`
     - `https://med.cuhk.edu.cn/teacher-search`

第二阶段再视真实 E2E 扩到：

- `SZTU`
- `SUAT-SZ`
- `SUSTech`（仅当真实样本重新暴露问题时）

### 4. 渐进迁移

迁移策略：

1. 先把现有 host-specific 提取函数包进 adapter
2. 通用入口优先调用 adapter
3. 行为不变时先做结构重组
4. 再根据真实 E2E 暴露的问题做 adapter 内部增强

## Implementation Units

### IU1. Adapter Registry Skeleton

Files:

- `apps/miroflow-agent/src/data_agents/professor/school_adapters.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_school_adapters.py`

Responsibilities:

- 定义 adapter 协议/基类
- 注册 `SYSU faculty/staff` 与 `CUHK teacher-search` 首批 adapter
- 提供 `extract_roster_entries_with_adapter(...)`
- 提供一键旁路开关，允许快速退回 generic roster logic

### IU2. Roster Entry Extraction Dispatch

Files:

- `apps/miroflow-agent/src/data_agents/professor/roster.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_roster_validation.py`

Responsibilities:

- 在 `extract_roster_entries()` 顶部接入 adapter dispatch
- 先迁移 `CUHK teacher-search` 与 `SYSU faculty/staff` 的现有 host-specific/heuristic 路径
- 保留 generic fallback

### IU3. Discovery Boundary Guardrails

Files:

- `apps/miroflow-agent/src/data_agents/professor/discovery.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_roster_validation.py`

Responsibilities:

- 保持 `discovery.py` orchestration 边界清晰
- 不让 `faculty/staff` 再被误判成 direct-profile
- 不回归已通过的 `姓名 + URL` direct-profile seed

### IU4. Real E2E Validation Round

Target validation set:

- `SYSU faculty/staff` family:
  - `http://materials.sysu.edu.cn/faculty/staff`
  - `http://ise.sysu.edu.cn/teachers`
- `CUHK teacher-search`:
  - `https://sse.cuhk.edu.cn/teacher-search`
  - `https://med.cuhk.edu.cn/teacher-search`
- direct-profile guardrail:
  - `https://www.sigs.tsinghua.edu.cn/llyys/main.htm`
  - `https://jianwei.cuhk.edu.cn/`

Success criteria:

- `SYSU materials` 不再出现通用导航词假对象
- `CUHK teacher-search` 不回归
- direct-profile seed 不回归
- 若可能，`CUHK` 总耗时相较 baseline 有下降

## Test-First Posture

这轮继续保持 TDD：

1. 先给 adapter registry / dispatch / host family characterization 补测试
2. 再做最小实现
3. 再用真实 E2E 判是否继续扩更多学校

## Risks

### 风险 1：adapter 只是“换个地方堆 if-else”

Mitigation:

- 必须有显式 registry 和统一接口
- 不允许 adapter 直接改通用全局状态

### 风险 2：学校级 adapter 过细，膨胀成“每院系一个文件”

Mitigation:

- 优先学校级 family
- 只有在学校内部结构显著分叉时才做院系 override

### 风险 3：结构重组引入真实回归

Mitigation:

- 每个迁移步骤后跑 targeted real E2E
- 先迁移已有逻辑，不先发明新逻辑

## Verification Plan

### 单测

- `test_school_adapters.py`
- `test_roster_validation.py`

### 真实 E2E

1. direct-profile guardrail batch
2. `SYSU faculty/staff + CUHK teacher-search` targeted batch
3. 必要时再扩大到更宽样本

### 判定规则

- 如果结构显式化后，真实 E2E 无回归且 host family 边界更清晰，则继续推进
- 如果 adapter 引入明显回归，则先停在 registry + dispatch，不继续扩更多 host
