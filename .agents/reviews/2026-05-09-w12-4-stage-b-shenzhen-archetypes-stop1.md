---
title: "Review — W12-4 Stage B (Codex stop #1, §5.1 dry-run DSN format)"
date: 2026-05-09
spec: .agents/specs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md
handoff: .agents/handoffs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md
codex_agent_id: a716610f7717fdb9f
decision: revise-and-resume
---

# Review — W12-4 Stage B Codex stop #1

## Outcome

Codex 正确触发 spec §11 stop condition（§5.1 dry-run cannot start），未硬推、未伪造 fixture、未越界。这正是 spec 设计要求的行为 → discipline check ✅。

## Codex 报告核心

- 失败点：`scripts/run_homepage_paper_ingest.py` line 28 `psycopg.connect(dsn, row_factory=dict_row)`
- 错误：`psycopg.ProgrammingError: missing "=" after "postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real"`
- 根因：脚本直连 psycopg，DSN 解析走 libpq；handoff §8 / §9 + spec §5.1 / §9 给的是 SQLAlchemy `postgresql+psycopg://` 形式

## Claude 二次核实（独立验证）

```bash
$ grep -nE "psycopg\.connect|create_engine" apps/miroflow-agent/scripts/run_homepage_paper_ingest.py
13:from psycopg.rows import dict_row
28:    return psycopg.connect(dsn, row_factory=dict_row)
```

确认：脚本完全不走 SQLAlchemy。Codex 诊断准确。

## CLAUDE.md §6 上下文

```
Admin-console runtime expects:
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real
```

CLAUDE.md 文档化的是 admin-console（FastAPI + SQLAlchemy）的 DSN，不是 ingest 脚本。
两者使用同名环境变量但格式约束不同——这是 CLAUDE.md 的隐式 invariant。
本 slice 不修这个 doc gap（属另一议题），仅修当前 spec/handoff 的运行命令。

## 决定：revise-and-resume

1. 修 handoff §3.4c / §8 + spec §5.1 / §9 的 `DATABASE_URL` 形式：
   - `postgresql+psycopg://...`（错）→ `postgresql://...`（对）
2. 通过 SendMessage 让 Codex 接续 §5.1，从 dry-run before 开始
3. 不重建 codex agent；保持上下文延续

## Spec/handoff 文档质量复盘（一句）

Stop condition #1 暴露了 spec §13 假设 A2 的不完整描述（"Postgres miroflow_real 起着" 被认为足够，但实际还需 DSN 格式正确）——记入 spec §13 的 follow-up 修订。

## Follow-up（不做，仅记录）

- F1: CLAUDE.md §6 应分两块写明 admin-console（SQLAlchemy）和 agent 脚本（raw psycopg）的 DSN 形式差异
- F2: agent app 内部不一致：可能某些 ingest 脚本走 SQLAlchemy 而本 script 走 raw psycopg；统一处理在另一 spec
- F3: `run_homepage_paper_ingest.py` 可加 DSN normalize 兼容层（与 F1/F2 一并考虑）

## Files touched

- 本 review（新增）
- handoff（即将编辑）
- spec（即将编辑）

无产品代码变更。Codex 未 commit。
