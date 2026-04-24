# AGENTS.md

Builder-facing repo guidance for Codex and other coding agents. This file is the execution companion to `CLAUDE.md`: Claude designs, plans, writes handoffs, and reviews; Codex implements approved slices, updates tests, runs checks, and reports evidence.

Keep this file compact and operational. Do not turn it into a full project encyclopedia.

## 1. Role and default behavior

- You are the **builder**, not the default architect, for non-trivial product code.
- For Standard or Epic/Risky work, read the current `.agents/specs/...` design contract and `.agents/handoffs/...` implementation handoff before editing code.
- Implement the requested slice exactly; do not silently broaden scope.
- Prefer minimal, local, reversible changes over broad rewrites.
- Make every changed line traceable to the task or handoff.
- Run the narrowest relevant checks first, then broaden when appropriate.
- Report commands, results, changed files, assumptions, risks, and any checks that could not run.
- Stop and request re-planning if the handoff is contradictory, unsafe, missing critical context, or requires a larger architectural decision.

Tiny local fixes may be handled directly when the task is obviously reversible and has no schema/API/auth/security/concurrency/performance impact.

## 2. Project overview

深圳科创数据平台：面向深圳科创生态的对话式科创信息检索系统。用户通过 Web 用自然语言提问，系统在教授、企业、论文、专利四个数据域中智能路由检索，并返回结构化、可追溯的回答。

The project builds on the MiroThinker deep-research agent framework. It reuses agent runtime, multi-turn tool orchestration, search/scrape/extract capabilities, and adds four-domain data collection agents plus an Agentic RAG service layer.

Baseline stack: Python 3.12+, uv, Hydra, Ruff, MCP/FastMCP, Anthropic/OpenAI SDKs, Playwright, E2B, Pydantic, SQLite, Milvus, pytest + xdist + inline snapshots. Follow the nearest `pyproject.toml`, test config, and subproject conventions when more specific.

## 3. Read order

When working from a handoff, use this order:

1. `.agents/handoffs/<date>-<slug>.md` — implementation slice, explicit do/do-not rules, validation expectations.
2. `.agents/specs/<date>-<slug>.md` — design contract, acceptance criteria, invariants, edge cases.
3. Source-of-truth docs listed below.
4. Local code and tests near the touched files.
5. `docs/solutions/` entries only when they are relevant to the current issue.

Source-of-truth docs:

- `docs/index.md` — documentation index, glossary, and implementation-status matrix (**read this first to gauge which doc is authoritative vs legacy/partial**).
- `docs/Data-Agent-Shared-Spec.md` — shared data-agent architecture, logical contracts, quality standards, MiroThinker mapping.
- `docs/{Company,Professor,Paper,Patent}-Data-Agent-PRD.md` — domain-specific requirements.
- `docs/Agentic-RAG-PRD.md` — query classification A–G, semantic routing, multi-source recall/fusion/rerank.
- `docs/Agentic-RAG-Operating-Guide.md` — M0.1–M6 全流水线运维手册（dogfood + 回滚 + 监控），对应当前在线 `/api/chat` 的运行口径。
- `docs/Multi-turn-Context-Manager-Design.md` — 多轮指代消解与跨域跳转设计（**仅部分落地**：进程内 `SessionContext` + 教授指代消歧已在 `chat.py`；持久化 / 完整 EntityStack / 跨域上下文 未做；详见 `docs/index.md`）。
- `docs/plans/index.md` / `docs/solutions/index.md` — 活跃/完成的计划、可复用的问题复盘与最佳实践。
- `docs/architecture-decisions/` — ADR（跨任务的长期架构决策）。

If the handoff conflicts with a higher-level invariant or source-of-truth doc, stop and report the conflict instead of guessing.

## 4. Repository map

**当前主线（数据采集 + Agentic RAG）**

- `apps/miroflow-agent/` — 四域数据采集与 Agentic RAG 核心。
  - `conf/` — Hydra 配置；`scripts/` — 运维与真实 E2E（`run_homepage_paper_ingest.py`、`run_professor_*`、`run_company_import_e2e.py`、`run_paper_release_e2e.py`、`run_patent_import_e2e.py`、`run_name_identity_scan.py`、`run_milvus_backfill.py`、`run_professor_orcid_backfill.py` 等 50+）；`tests/` — pytest suites；`alembic/versions/` — Postgres schema 迁移 V001–V011（含 V007 run_id trace、V009 canonical_name_zh、V011 RAG 表：`paper_full_text` / `paper_title_resolution_cache` / `professor_orcid`）。
  - `src/core/` — pipeline entry/factory、orchestrator、tool executor、answer generator、stream handler。
  - `src/data_agents/` — 四域采集与服务层：
    - 共享层：`contracts.py`、`evidence.py`、`linking.py`、`normalization.py`、`publish.py`、`runtime.py`。
    - 域子目录：`company/`、`professor/`、`paper/`、`patent/`（采集、发布、enrichment、exact/knowledge backfill、import_xlsx）。
    - 横切：`canonical/`（统一主 schema：`common`/`company`/`paper`/`professor`/`relations`/`source`）、`taxonomy/`（学科分层 + 种子）、`quality/`（阈值配置）、`providers/`（Anthropic/Qwen/Dashscope/MiroThinker/web_search）、`storage/`（SQLite / Milvus / `postgres/`）、`service/`（`retrieval.py` + `search_service.py`，RAG 服务层；**`_VALID_DOMAINS` 目前仅 professor/paper**）。
  - `src/llm/`、`src/io/`、`src/logging/`、`src/config/`、`src/utils/` — 框架层。

- `apps/admin-console/` — 管理后台 + 用户对话入口（FastAPI 后端 + React/Vite 前端）。
  - `backend/api/` — `chat.py`（`/api/chat` 用户问答，classifier A/B/D/E/F/G + 有限 C；Round 10 v2 进程内 SessionContext；Round 11 v3.1 D/E/G handlers；Serper fallback + reranker）、`dashboard.py`、`domains.py`、`data.py`、`batch.py`、`export.py`、`pipeline.py`、`pipeline_issues.py`、`review.py`、`upload.py`。
  - `frontend/src/` — React SPA，`pages/` 含 `/chat`、`Dashboard`、`DomainList`、`RecordDetail`；三 tab 管道验证台在 admin 侧。
  - `tests/` — `test_chat_v1.py`、`test_chat_retrieval.py`、`test_professor_api.py`、`test_paper_api.py`、`test_review_api.py` 等。

- `libs/miroflow-tools/` — 共享 `ToolManager`、MCP servers、dev MCP servers。

**辅助/历史应用**（非当前主线，修改前对齐 owner）

- `apps/collect-trace/` — agent trace → SFT/DPO 转换。
- `apps/gradio-demo/` — 本地 Gradio + vLLM demo。
- `apps/visualize-trace/` — Flask trace 仪表盘。
- `apps/lobehub-compatibility/` — LobeChat 适配器。

**协作记录与文档**

- `.agents/` — `specs/`、`handoffs/`、`reviews/`、`harness/`。
- `docs/` — PRD、架构、`plans/`、`solutions/`、`architecture-decisions/`（ADR）、`source_backfills/`（补全用 JSONL/XLSX），入口 `docs/index.md`。

## 5. Common commands

Repository root:

```bash
uv sync
just lint
just format
just sort-imports
just precommit
just check-license
just insert-license
just format-md
```

Agent app:

```bash
cd apps/miroflow-agent
uv run pytest
uv run pytest tests/test_foo.py
uv run pytest -k "test_name"
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m slow
uv run pytest -m requires_api_key
uv run pytest -n0
uv run python -m src.core.pipeline agent=mirothinker_v1.5 llm=default benchmark=debug
uv run python scripts/run_company_import_e2e.py
uv run python scripts/run_professor_crawler_e2e.py
uv run python scripts/run_paper_release_e2e.py
uv run python scripts/run_patent_import_e2e.py
```

Use the handoff’s validation commands when present. Otherwise choose the smallest relevant command based on touched files.

## 6. Non-negotiable implementation invariants

- `docs/Data-Agent-Shared-Spec.md` outranks domain-local convenience.
- Evidence must remain structured, traceable, source-grounded, and suitable for user-facing audit.
- Domain modules may use independent physical schemas but must conform to shared logical contracts.
- Cross-domain linking must use normalization plus public evidence, not ad-hoc heuristics.
- Structured outputs must stay Pydantic-validated where the data-agent contract requires it.
- Do not silently change public APIs, serialized formats, benchmark output formats, or data contracts.
- Secrets, API keys, tokens, cookies, and credentials must come from environment variables or approved secret managers. Never hardcode them.
- Do not introduce heavy dependencies without explicit justification and approval.
- Prefer boring, inspectable, agent-legible designs over clever abstractions.
- Avoid drive-by refactors, broad formatting, and unrelated cleanup.

## 7. Coding standards

- Match local style and nearby patterns before introducing new abstractions.
- Preserve type hints, Pydantic models, validation boundaries, and existing error-handling conventions.
- Keep data transformations explicit and testable.
- Prefer dependency injection or configuration over hidden globals when adding runtime behavior.
- Preserve idempotency, retry semantics, and state-machine transitions unless the handoff explicitly changes them.
- Keep experimental paths clearly separated from production paths.
- Do not weaken tests, skip assertions, or change benchmark definitions just to make results pass.
- When modifying generated or vendored-looking files, first verify they are intended to be edited directly.

## 8. Testing and verification

Before reporting completion:

- Run relevant tests/checks, or clearly state why they could not run.
- Include exact commands and outcomes.
- For data-agent changes, validate contract behavior, evidence shape, normalization/linking behavior, and relevant domain edge cases.
- For retrieval/RAG/routing changes, validate routing/classification behavior and source traceability.
- For pipeline/runtime changes, validate orchestration, rollback/failure handling, and output modes where relevant.
- For public behavior changes, update or add docs/tests as appropriate.

Never say “all tests pass” unless the relevant tests actually passed in the current run.

## 9. Reporting format

When done, report concisely:

```text
Summary:
- <what changed>

Changed files:
- <path>: <reason>

Verification:
- <command> — <result>
- <command not run> — <why>

Risks / notes:
- <remaining risk, assumption, or follow-up>
```

For partial work, say what is complete, what remains, and the next safest step.

## 10. Stop-and-escalate conditions

Stop and request clarification or re-planning when any of these occur:

- The requested change conflicts with `docs/Data-Agent-Shared-Spec.md`, the design contract, or the handoff.
- The work requires a schema/storage/API/public contract change not listed in the handoff.
- The implementation would cross a security, auth, secrets, permissions, or trust boundary.
- The fix requires broad rewrites, unrelated cleanup, or modifying many files outside the slice.
- Required tests or fixtures are missing and the correct behavior is ambiguous.
- Existing tests fail for reasons unrelated to the change and affect confidence.
- You discover hidden performance, concurrency, retry, idempotency, or migration/rollback risk.
- A dependency, tool, or environment requirement is missing and cannot be safely inferred.

## 11. Protected files and areas

Do not modify these unless the user explicitly asks or the task is specifically about harness/docs maintenance:

- `CLAUDE.md`
- `AGENTS.md`
- global agent config
- unrelated CI/release/deployment config
- secret templates or credential-related config
- unrelated `.agents/...` artifacts

When editing `.agents/specs/`, `.agents/handoffs/`, or `.agents/reviews/`, preserve task slug, acceptance criteria, changed files, command results, unresolved risks, and next owner.

## 12. Parallelism and multi-agent work

Use parallelism only when slices have clear file/interface boundaries, independent verification, and an obvious merge order. Prefer separate branches or git worktrees for multi-agent or multi-session work. One active writer per slice.

Do not assume another agent’s changes are present unless they are visible in the working tree. Re-check local context before editing.
