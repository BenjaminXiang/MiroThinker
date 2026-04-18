# 计划索引

这里的目标不是重复每份计划内容，而是直接回答三件事：

1. 哪些计划已经完成
2. 哪些还需要继续优化
3. 当前主线任务到底是什么

## 当前执行 authority

- [2026-04-16-007-plan-portfolio-execution-roadmap.md](./2026-04-16-007-plan-portfolio-execution-roadmap.md)
  当前唯一的顶层执行路线图。它负责定义波次顺序、谁是下一波主线、哪些计划已经收口。

## 当前主线任务

- [2026-04-16-007-plan-portfolio-execution-roadmap.md](./2026-04-16-007-plan-portfolio-execution-roadmap.md)
  顶层执行 authority。
- [2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md](./2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md)
  当前下一波主线，聚焦论文多源证据增强、exact identifier、evidence quality；后续输出必须对齐 `2026-04-17-004` 里的 canonical paper + `person_paper_link` 边界，而不是继续扩旧 `released_objects` 事实模型。
- [2026-04-17-004-shenzhen-stem-knowledge-graph-retrieval-and-ops-architecture-plan.md](./2026-04-17-004-shenzhen-stem-knowledge-graph-retrieval-and-ops-architecture-plan.md)
  当前架构主线，固定 seed taxonomy、canonical graph、retrieval projection、company news refresh 和 ops dashboard 的目标形态。

这三份组合起来，定义了当前真正需要继续推进的主线。

## 排队任务

- [2026-04-06-001-feat-admin-console-phase2-upgrade-plan.md](./2026-04-06-001-feat-admin-console-phase2-upgrade-plan.md)
  管理后台二期计划，当前明确排队；后续实现必须以 `2026-04-17-004` 定义的 data quality control console 为准，对旧 count-board 目标做收缩或替换。

## 已完成闭环

- [2026-04-16-006-professor-workbook-closure-sequencing-plan.md](./2026-04-16-006-professor-workbook-closure-sequencing-plan.md)
- [2026-04-16-005-workbook-coverage-gap-remediation-plan.md](./2026-04-16-005-workbook-coverage-gap-remediation-plan.md)
- [2026-04-16-004-professor-school-adapter-architecture-plan.md](./2026-04-16-004-professor-school-adapter-architecture-plan.md)
- [2026-04-16-003-professor-pipeline-residual-hardening-plan.md](./2026-04-16-003-professor-pipeline-residual-hardening-plan.md)
- [2026-04-16-002-professor-direct-profile-identity-hardening-plan.md](./2026-04-16-002-professor-direct-profile-identity-hardening-plan.md)
- [2026-04-04-001-feat-admin-console-plan.md](./2026-04-04-001-feat-admin-console-plan.md)

这些计划已经被真实 E2E、回归测试或交付结果覆盖，不再作为待执行入口。

## 历史参考

- [2026-04-05-001-feat-professor-enrichment-pipeline-v2-plan.md](./2026-04-05-001-feat-professor-enrichment-pipeline-v2-plan.md)
- [2026-04-06-002-professor-pipeline-v3-redesign.md](./2026-04-06-002-professor-pipeline-v3-redesign.md)
- [2026-04-06-003-feat-professor-pipeline-v3-implementation-plan.md](./2026-04-06-003-feat-professor-pipeline-v3-implementation-plan.md)

这些文档保留历史设计上下文，但已被后续路线图吸收；查历史决策时可参考，执行时不要把它们当作当前 authority。

## 使用规则

- 想知道“现在该做什么”，先看 `007`。
- 想知道“下一波功能增强往哪走”，看 `2026-04-08-001`。
- 想知道“还有哪些是后面再做的”，看“排队任务”。
- 想知道“哪些事情已经做完不用再打转”，看“已完成闭环”。
- 想知道“为什么之前这样做”，再回看 reference 文档。
