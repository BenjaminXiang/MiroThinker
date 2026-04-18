# 工作区地图

本文件是仓库根目录的快速导航，目标是让人先知道哪里是源码、哪里是当前权威文档、哪里是日志与本地状态，而不是在根目录里逐个试错。

## 当前入口

- [docs/index.md](docs/index.md): 文档总入口
- [docs/plans/index.md](docs/plans/index.md): 计划状态总览
- [docs/solutions/index.md](docs/solutions/index.md): 经验沉淀与问题处置索引
- [docs/plans/2026-04-16-007-plan-portfolio-execution-roadmap.md](docs/plans/2026-04-16-007-plan-portfolio-execution-roadmap.md): 当前执行 authority
- [logs/](logs): 真实 E2E 与发布/检索验证产物，不是设计文档，但经常是当前事实证据

## 主要工作区

### 源码与实现

- `apps/`: 主应用与数据代理实现
- `libs/`: 共享库或复用组件
- `scripts/`: 自动化脚本、E2E 入口、发布脚本、review helper
- `tests/`: 自动化测试
- `config/`: 配置文件
- `assets/`: 项目资源

### 规格、计划与知识沉淀

- `docs/`: PRD、设计、计划、经验沉淀
- `openspec/`: 规格与提案相关材料
- `tutorial/`: 教程或引导型内容
- `local-skills/`: 本地 skill/workflow 说明
- `todos/`: 文件化待办与跟踪项

### 日志与证据

- `logs/`: 真实运行日志、E2E 报告、发布产物摘要
- `htmlcov/`, `report.html`, `site/`: 生成产物，不是权威源

## 当前执行口径

- 当前顶层执行 authority 只有一个：
  [docs/plans/2026-04-16-007-plan-portfolio-execution-roadmap.md](docs/plans/2026-04-16-007-plan-portfolio-execution-roadmap.md)
- 仍处于 active 的功能计划目前有两个：
  - [2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md](docs/plans/2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md)
  - [2026-04-06-001-feat-admin-console-phase2-upgrade-plan.md](docs/plans/2026-04-06-001-feat-admin-console-phase2-upgrade-plan.md)
- 其余已完成或 reference 的计划不要再当作当前执行入口使用。

## 本地状态与生成物

这些目录通常不是需要优先阅读或手工维护的源文件：

- `.agents/`, `.claude/`, `.codex/`, `.context/`, `.gstack/`, `.worktrees/`
- `.venv/`, `.uv-cache/`, `.pytest_cache/`, `__pycache__/`
- `_bmad/`, `_bmad-output/`
- `.coverage`, `htmlcov/`, `report.html`, `site/`

这些内容可能对调试有价值，但不应该和 `docs/`、`apps/`、`tests/` 混看。

## 清理原则

- 优先做非破坏性整理：索引、状态标记、入口梳理。
- 删除历史文档前，先确认它是否仍被当前计划、经验沉淀或日志引用。
- `logs/` 是验证证据，不是随手可删的临时文件夹。
- `docs/solutions/` 中的旧文档如果还在解释当前代码或验收策略，优先标记为 baseline/reference，而不是直接删除。
