# CLAUDE.md

Repo-level guidance for Claude Code. Keep this file compact: only include facts and rules useful in almost every session. Put task state, long PRDs, detailed runbooks, and temporary decisions in linked docs or `.agents/...` artifacts.

Claude is the **designer / planner / reviewer**. Codex is the default **production-code builder**. For non-trivial product work, prefer: **Claude designs → Codex implements → Claude reviews**.

## 1. Operating model

- Claude owns requirements clarification, architecture, invariants, design contracts, Codex handoffs, reviews, and reusable lessons.
- Codex owns approved implementation slices, production-code edits, test updates, relevant checks, and evidence reporting.
- Claude may directly edit docs, specs, plans, acceptance criteria, review notes, and tiny low-risk scaffolding.
- Claude is not the default writer for production logic under `apps/`, `libs/`, `src/`, runtime, storage, service, API, or data-agent modules unless the user explicitly asks or the change is tiny and clearly reversible.
- Use the lightest reliable workflow. Do not turn small fixes into multi-agent rituals.

## 2. Project overview

深圳科创数据平台：面向深圳科创生态的对话式科创信息检索系统。用户通过 Web 用自然语言提问，系统在教授、企业、论文、专利四个数据域中智能路由检索，并返回结构化、可追溯的回答。

The project builds on the MiroThinker deep-research agent framework. It reuses agent runtime, multi-turn tool orchestration, search/scrape/extract capabilities, and adds four-domain data collection agents plus an Agentic RAG service layer.

Baseline stack: Python 3.12+, uv, Hydra, Ruff, MCP/FastMCP, Anthropic/OpenAI SDKs, Playwright, E2B, Pydantic, SQLite, Milvus, pytest + xdist + inline snapshots. Prefer local `pyproject.toml` or subproject config when more specific.

## 3. Source-of-truth docs

Repo-local docs are the system of record. If important knowledge exists only in chat, convert it into a task artifact or a durable `docs/solutions/` entry.

- `docs/index.md` — documentation index, glossary, and implementation-status matrix.
- `docs/Data-Agent-Shared-Spec.md` — shared data-agent architecture, logical contracts, quality standards, MiroThinker mapping.
- `docs/{Company,Professor,Paper,Patent}-Data-Agent-PRD.md` — domain-specific requirements.
- `docs/Agentic-RAG-PRD.md` — query classification A–G, semantic routing, multi-source recall/fusion/rerank.
- `docs/Agentic-RAG-Operating-Guide.md` — M0.1–M6 全流水线运维手册（dogfood + 回滚 + 监控），对应当前在线 `/api/chat` 的运行口径。
- `docs/Multi-turn-Context-Manager-Design.md` — 多轮指代消解与跨域跳转设计（**当前未落地**，chat v0/v1 仍为单轮；详见 `docs/index.md` 实现状态）。
- `docs/plans/index.md` / `docs/solutions/index.md` — 活跃/完成的计划、可复用的问题复盘与最佳实践。
- `docs/architecture-decisions/` — ADR（跨任务的长期架构决策）。

## 4. Repository map

**当前主线（数据采集 + Agentic RAG）**

- `apps/miroflow-agent/` — 四域数据采集与 Agentic RAG 核心。
  - `conf/` — Hydra 配置；`scripts/` — 运维与真实 E2E（`run_homepage_paper_ingest.py`、`run_professor_*`、`run_company_import_e2e.py`、`run_paper_release_e2e.py`、`run_patent_import_e2e.py`、`run_name_identity_scan.py`、`run_milvus_backfill.py`、`run_professor_orcid_backfill.py` 等 50+）；`tests/` — pytest suites；`alembic/versions/` — Postgres schema 迁移 V001–V011（含 V007 run_id trace、V009 canonical_name_zh、V011 RAG 表：`paper_full_text` / `paper_title_resolution_cache` / `professor_orcid`）。
  - `src/core/` — pipeline entry/factory、orchestrator、tool executor、answer generator、stream handler。
  - `src/data_agents/` — 四域采集与服务层：
    - 共享层：`contracts.py`、`evidence.py`、`linking.py`、`normalization.py`、`publish.py`、`runtime.py`。
    - 域子目录：`company/`、`professor/`、`paper/`、`patent/`（采集、发布、enrichment、exact/knowledge backfill、import_xlsx）。
    - 横切：`canonical/`（统一主 schema：`common`/`company`/`paper`/`professor`/`relations`/`source`）、`taxonomy/`（学科分层 + 种子）、`quality/`（阈值配置）、`providers/`（Anthropic/Qwen/Dashscope/MiroThinker/web_search）、`storage/`（SQLite / Milvus / `postgres/`）、`service/`（`retrieval.py` + `search_service.py`，RAG 服务层）。
  - `src/llm/`、`src/io/`、`src/logging/`、`src/config/`、`src/utils/` — 框架层。

- `apps/admin-console/` — 管理后台 + 用户对话入口（FastAPI 后端 + React/Vite 前端）。
  - `backend/api/` — `chat.py`（`/api/chat` 用户问答，B/D/E 路由 + Serper fallback + reranker）、`dashboard.py`、`domains.py`、`data.py`、`batch.py`、`export.py`、`pipeline.py`、`pipeline_issues.py`、`review.py`、`upload.py`。
  - `frontend/src/` — React SPA，`pages/` 含 `/chat`（Round 9 P1-v1 MVP）与 `/browse`（三 tab 管道验证台：provenance / coverage / review）。

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

Run the narrowest relevant check first, then broaden. Never claim completion without verification evidence or a clear reason a check could not run.

## 6. Non-negotiable invariants

- `docs/Data-Agent-Shared-Spec.md` outranks domain-local convenience.
- Evidence must remain structured, traceable, source-grounded, and suitable for user-facing audit.
- Domain modules may use independent physical schemas but must conform to shared logical contracts.
- Cross-domain linking must use normalization plus public evidence, not ad-hoc heuristics.
- Structured outputs must stay Pydantic-validated where the data-agent contract requires it.
- Do not silently change public APIs, serialized formats, benchmark output formats, or data contracts.
- Secrets, API keys, tokens, cookies, and credentials must come from environment variables or approved secret managers. Never hardcode them.
- Prefer boring, inspectable, agent-legible designs over clever abstractions.
- Make changed lines traceable to the task. Avoid drive-by refactors, broad formatting, and unrelated cleanup.
- Repeatedly violated rules should become tests, lint rules, hooks, CI checks, or documented invariants rather than more prompt text.

## 7. Task classification

**Tiny**: typo, doc note, obvious local bug, reversible one- or two-file edit, no schema/API/auth/security/concurrency/performance impact. Inspect local context, apply the smallest fix or delegate it, run a narrow check, review the diff.

**Standard**: local feature, moderate refactor, user-visible behavior change, contract/test update. Flow: clarify goal and done criteria → write/update `.agents/specs/...` and `.agents/handoffs/...` → Codex implements/verifies → Claude reviews.

**Epic/Risky**: new feature area, core refactor, schema/storage/API change, trust boundary, auth/secrets, background jobs, retries, state machines, concurrency, idempotency, caching, performance-sensitive or multi-session work. Flow: pressure-test scope → lock architecture/invariants/validation → plan implementation slices → Codex implements each slice → Claude reviews each slice → durable lessons go to `docs/solutions/`.

## 8. Task artifacts

For Standard or Epic/Risky work, externalize state before implementation:

- `.agents/specs/<YYYY-MM-DD>-<slug>.md` — Claude-owned design contract.
- `.agents/handoffs/<YYYY-MM-DD>-<slug>.md` — Codex implementation handoff.
- `.agents/reviews/<YYYY-MM-DD>-<slug>.md` — Claude review and rework decision.

Design contracts should include: goal, user-visible behavior, non-goals, affected paths, architecture/data flow, interface/type/Pydantic expectations, invariants, edge cases, failure modes, validation commands, expected evidence, migration/rollback notes, assumptions, and open questions.

Handoffs should include: spec path, slice scope, source docs to read, likely files/directories, explicit do-not rules, tests/checks, done criteria, and what Codex must report back.

When compacting or restarting, preserve task slug, artifact paths, acceptance criteria, changed files, commands/results, unresolved risks, and next owner.

## 9. Review and completion policy

Claude reviews Codex output against the approved contract, acceptance criteria, unchanged invariants, interface contracts, evidence traceability, touched-file boundaries, command output, security/trust boundaries, concurrency/retry/state/idempotency/performance risks, docs drift, and migration/rollback risk.

Do not declare done unless:

- contract scope is implemented;
- relevant checks passed, or failures are explicitly explained;
- public docs are updated when behavior changed;
- no secrets or credentials are hardcoded;
- risks, assumptions, and unsupported checks are stated;
- Claude has decided accept / revise / reject after review.

## 10. Skills, plugins, and deterministic controls

Use skills/plugins as targeted harness components, not an always-on ritual.

- Use gstack / Compound / Superpowers / BMAD only when the task genuinely needs architecture challenge, technical planning, TDD slice design, QA, or epic-level product decomposition.
- Do not chain planning frameworks by default. One good plan is better than stacked rituals.
- Keep detailed plugin command catalogs outside this root file, for example in `.agents/harness/skills.md` or tool-specific docs.
- Deterministic requirements belong in hooks, permissions, lint, tests, CI, or secret scans whenever possible.

## 11. Parallelism and protected files

Use targeted parallelism only when slices have clear file/interface boundaries, independent verification, and an obvious merge order. Prefer separate branches or git worktrees for multi-agent/multi-session work. One active writer per slice.

Do not modify these unless the user asks or the task is specifically about harness/docs maintenance: `CLAUDE.md`, `AGENTS.md`, global agent config, unrelated CI/release/deployment config, secret templates, or credential-related config.

## 12. Maintaining this file

Keep `CLAUDE.md` specific and compact. Remove stale generic rules. Link to deeper docs instead of duplicating them. Update `AGENTS.md` when Codex-facing behavior changes. Promote repeated mistakes into checks/docs/skills rather than expanding root instructions indefinitely.