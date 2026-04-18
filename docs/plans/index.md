# 计划索引

一张表说清楚现在什么是活的、什么是完成的、什么该看哪个文档。

## 🟢 当前活跃（OPEN / PARTIAL — 还在推进）

| 计划 | 主题 | 状态 |
|---|---|---|
| [2026-04-16-007-plan-portfolio-execution-roadmap](./2026-04-16-007-plan-portfolio-execution-roadmap.md) | 顶层波次路线图 | ACTIVE — Round 7/8 系列已从此接过主线 |
| [2026-04-17-005-company-primary-knowledge-graph-architecture-plan](./2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md) | 企业主 KG 架构（北极星） | OPEN — canonical schema 已定，实现未开始 |
| [2026-04-08-001-feat-paper-multi-source-priority-implementation-plan](./2026-04-08-001-feat-paper-multi-source-priority-implementation-plan.md) | 论文多源证据优先级 | OPEN — Phase A 真实 E2E 已过，Phase B 排队 |
| [2026-04-17-001-professor-stem-reset-and-storage-redesign-plan](./2026-04-17-001-professor-stem-reset-and-storage-redesign-plan.md) | 教授 STEM 重置与存储重构 | OPEN — 设计完成，实现待启动 |
| [2026-04-17-002-professor-stem-parallel-rebuild-plan](./2026-04-17-002-professor-stem-parallel-rebuild-plan.md) | 三 Lane 并行重建 | OPEN — 三 Lane 设计完成 |
| [2026-04-17-003-professor-stem-issue-closure-plan](./2026-04-17-003-professor-stem-issue-closure-plan.md) | STEM 残留问题收尾 | PARTIAL — Wave 1 JSON 健壮性收住；Wave 2 paper closure 进行中 |
| [2026-04-17-003-professor-official-anchor-first-paper-disambiguation-plan](./2026-04-17-003-professor-official-anchor-first-paper-disambiguation-plan.md) | 官方锚点优先的论文消歧 | OPEN — 9 真实 E2E 验证通过，尚未大规模 rollout |
| [2026-04-18-001-user-chat-interface-plan](./2026-04-18-001-user-chat-interface-plan.md) | 用户对话检索界面 | BLOCKED — 等 Round 7/8 数据质量稳定 |
| [2026-04-18-003-company-product-capture](./2026-04-18-003-company-product-capture.md) | 企业产品信息采集 | OPEN — V008 schema 设计完成，迁移未部署 |
| [2026-04-18-004-admin-console-professor-and-ui](./2026-04-18-004-admin-console-professor-and-ui.md) | 管理后台教授 UI | PARTIAL — 后端 API 已出，React UI 待实现 |

## ✅ 已完成（COMPLETE — 保留作参考）

| 计划 | 完成点 |
|---|---|
| [2026-04-04-001-feat-admin-console-plan](./2026-04-04-001-feat-admin-console-plan.md) | 管理后台一期：FastAPI + React + SQLite 查询界面 |
| [2026-04-16-002-professor-direct-profile-identity-hardening-plan](./2026-04-16-002-professor-direct-profile-identity-hardening-plan.md) | 直跳 profile 的身份加固 |
| [2026-04-16-003-professor-pipeline-residual-hardening-plan](./2026-04-16-003-professor-pipeline-residual-hardening-plan.md) | Wave 4 发现/抓取加固 |
| [2026-04-16-004-professor-school-adapter-architecture-plan](./2026-04-16-004-professor-school-adapter-architecture-plan.md) | School adapter 架构 Phase 1（CUHK/SYSU 上线） |
| [2026-04-16-005-workbook-coverage-gap-remediation-plan](./2026-04-16-005-workbook-coverage-gap-remediation-plan.md) | 工作簿覆盖缺口补齐 |
| [2026-04-16-006-professor-workbook-closure-sequencing-plan](./2026-04-16-006-professor-workbook-closure-sequencing-plan.md) | 教授工作簿 closure 编排 |
| [2026-04-18-002-real-data-e2e-and-db-separation](./2026-04-18-002-real-data-e2e-and-db-separation.md) | `miroflow_real` / `miroflow_test_mock` 双 DB 隔离（所有 Round 7/8 流程的基础） |
| [2026-04-18-005-data-quality-guards-and-identity-gate](./2026-04-18-005-data-quality-guards-and-identity-gate.md) | Round 7.6 / 7.8 / 7.9 / 7.10' / 7.13 / 7.14 / 7.15 — LLM 优先的数据质量门 |
| [2026-04-18-006-pipeline-verification-console](./2026-04-18-006-pipeline-verification-console.md) | Round 8c：`/browse` 三 tab + `pipeline_issue` 表（3 Lane 已合并） |
| [2026-04-18-007-name-identity-gate](./2026-04-18-007-name-identity-gate.md) | Round 7.17：canonical_name ↔ canonical_name_en LLM 门；`miroflow_real` 178/557 污染清除，182 条入 `pipeline_issue` |
| [2026-04-18-008-pipeline-run-id-trace](./2026-04-18-008-pipeline-run-id-trace.md) | Round 7.16 phase 1：V007 迁移 + 40,834 行 legacy_backfill 回填。phase 2 writer wiring 延后 |

## 📖 使用规则

- 想知道**数据质量现在到哪一步**：先看 `2026-04-18-005`（Round 7.x 系列全景）。
- 想知道**下一波架构主线**：看 `2026-04-17-005`（企业 KG 架构，当前北极星）+ `2026-04-17-002`（教授 STEM 并行重建）。
- 想知道**Round 7.17 name gate 如何工作**：`2026-04-18-007` + [solutions/data-quality/name-identity-gate-round-7-17-2026-04-18](../solutions/data-quality/name-identity-gate-round-7-17-2026-04-18.md)。
- 想知道**run_id trace phase 2 还差什么**：`2026-04-18-008` §3.2–§3.3。
- 想知道**管理后台教授 UI 状态**：`2026-04-18-004`（Round 8a 已出，Round 8b 待 React）。

## 🗑️ 已删除的历史计划

以下计划已从 repo 删除，内容完全被后续计划吸收（如需查阅请 `git log --all -- docs/plans/`）：

- `2026-04-05-001-feat-professor-enrichment-pipeline-v2-plan`（v2，被 v3 取代）
- `2026-04-06-001-feat-admin-console-phase2-upgrade-plan`（被 2026-04-18-004 + 006 吸收）
- `2026-04-06-002-professor-pipeline-v3-redesign`（纯架构 historical）
- `2026-04-06-003-feat-professor-pipeline-v3-implementation-plan`（Umbrella，已被 2026-04-16/17 系列细化）
- `2026-04-17-004-shenzhen-stem-knowledge-graph-retrieval-and-ops-architecture-plan`（被 `2026-04-17-005` 明确取代）
