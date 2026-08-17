# Worktree 整治与版本对照（2026-08-17，GitHub 中转前置）

Mode: 保全性整理（preserve-before-migration）。原则：真实代码与过程证据全部
提交到各自分支防丢；垃圾文件保持未跟踪（不删、不提交）；推送等用户确认。

## 处置结果（9 处脏 worktree → 全部保全提交）

| 位置/分支 | 提交 | 内容 |
|---|---|---|
| 主 checkout feat/professor-retrievability | `a389abc` | 检索门禁脚本+测试、refactor-control-plane、harness 文件、AGENTS/CLAUDE/CONTEXT、locks、dry-run 证据（18 文件 +4193） |
| paper-pipeline-cleanup | `aa1fa87` | 论文管线模块改造 + 管理台前后端 + 55 openspec + 8 runs（165 文件 +13156）——整条功能线首次入库 |
| canonical-v2-s2-baseline | `d7182b1` | S2 阶段 207 项（101 runs + 源码 + 11 ADR）首次入库 |
| prof-quality-status-rework（repo 外） | `361fd6f` | 质量门/写入器重构 + 测试 + openspec（10 文件） |
| 5 个 seed worktree + task61-prep | `7b56238`/`297b6e9`/`fda0fdc`/`c67d80d`/`6838f83`/`0b996a2` | 教授采集小修 + 测试 + run 证据 |

刻意未提交（保持 untracked）：主 checkout 的 `AGENTS.bak.md`、`CLAUDE.bak.md`、
`kimi-debug-session_*.zip`(22M)、`国先 logo.jpg`；s11 worktree 的
`.tmp-chat-responsive/`。均属垃圾/超重产物，不入库也不删除。

## 版本对照（"我测试的代码"是哪份）

| 线 | 位置 @ 分支 | HEAD | 说明 |
|---|---|---|---|
| **生产/被测** | `.worktrees/canonical-v2-s11-consolidation` @ `codex/canonical-v2-s12a-ready` | `1235b42` | 你八组测试打的版本：V2 服务栈 + 深化轮修复(438300a) + 今日全部测试/审计记录。18188 editable 安装跑的就是它 |
| 生产**数据**（≠代码） | `/var/tmp/mirothinker-canonical-v2-s12f/` serving pack | `candidate-s12f-20260801-v1` | 8/1 一次性薄回填（覆盖/字段贫困已审计）。**你测的是"最新代码 + 8/1 陈旧数据"** |
| 旧主线（冻结） | 主 checkout @ `feat/professor-retrievability` | `a389abc` | legacy A-G/RetrievalService 线，被 V2 取代 |
| main | `main` | `f0e6224` | Aggregate-S6 检查点；本地领先 origin/main **234 提交** |
| 未完功能线 | `paper-pipeline-cleanup` | `aa1fa87` | 论文管线+管理台（今日首次入库） |
| 其余 | canonical-v2 s1/s6c/s6d/s6f/task61、5 seed 分支等 | — | 历史切片，已保全 |

## 推送状态与计划（待用户确认执行）

- 已推送：仅 `main`（且 origin 落后 234 提交）；**21 个本地分支从未推送**；3 个
  tag（canonical-v2-s12g-candidate-20260807 等）未推送；origin 另有 5 个
  `issue-*` 分支仅远端存在（无需处理）。
- 建议一次性：`git push origin main && git push origin --all && git push origin --tags`
  （密钥类文件已确认在 .gitignore，不会误推）。
