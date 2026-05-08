# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Repo-level guidance for Claude Code. Keep this file compact: only include facts and rules useful in almost every session. Put task state, long PRDs, detailed runbooks, and temporary decisions in linked docs or `.agents/...` artifacts.

Claude is the **designer / planner / reviewer**. Codex is the default **production-code builder**. For non-trivial product work, prefer: **Claude designs → Codex implements → Claude reviews**. The Codex-facing companion is `AGENTS.md`; do not duplicate it here.

## 1. Operating model

- Claude owns requirements clarification, architecture, invariants, design contracts, Codex handoffs, reviews, and reusable lessons.
- Codex owns approved implementation slices, production-code edits, test updates, relevant checks, and evidence reporting.
- Claude may directly edit docs, specs, plans, acceptance criteria, review notes, and tiny low-risk scaffolding.
- Claude is **not** the default writer for production logic under `apps/`, `libs/`, `src/`, runtime, storage, service, API, or data-agent modules unless the user explicitly asks or the change is tiny and clearly reversible.
- Use the lightest reliable workflow. Do not turn small fixes into multi-agent rituals.

## 2. Project overview

深圳科创数据平台 — a conversational sci-tech information retrieval system for the Shenzhen innovation ecosystem. Users ask natural-language questions through a web UI; the system intelligently routes across four data domains (教授/professor, 企业/company, 论文/paper, 专利/patent) and returns structured, source-traceable answers.

The project builds on the MiroThinker deep-research agent framework. It reuses agent runtime, multi-turn tool orchestration, and search/scrape/extract capabilities, and adds four-domain data collection agents plus an Agentic RAG service layer.

Stack: Python 3.12 (uv-managed), Hydra, Ruff, MCP/FastMCP, Anthropic/OpenAI SDKs, Playwright, E2B, Pydantic v2, SQLAlchemy/Alembic, Postgres + pgvector, Milvus, SQLite, FastAPI, React + Vite, pytest + xdist + inline snapshots.

## 3. Source-of-truth docs

Repo-local docs are the system of record. If important knowledge exists only in chat, convert it into a task artifact or a durable `docs/solutions/` entry.

- `docs/index.md` — documentation index, glossary, and **implementation-status matrix** (✅/🟡/🚧/📝). Read this first to distinguish authoritative docs from legacy/partial docs.
- `docs/Data-Agent-Shared-Spec.md` — shared four-domain architecture, logical contracts, evidence/quality standards. Outranks domain-local convenience.
- `docs/{Company,Professor,Paper,Patent}-Data-Agent-PRD.md` — domain-specific requirements (PRD).
- `docs/Agentic-RAG-PRD.md` — query classification A–G, semantic routing, multi-source recall/fusion/rerank.
- `docs/Agentic-RAG-Operating-Guide.md` — current online `/api/chat` operating posture (M0.1–M6 dogfood + rollback + monitoring).
- `docs/Multi-turn-Context-Manager-Design.md` — multi-turn reference resolution and cross-domain transitions; **partially implemented** (Postgres `SessionStore` + entity stack + `last_result_set` are in; full design is not). Verify against current code.
- `docs/plans/index.md` and `docs/solutions/index.md` — active/completed plans and reusable lessons.
- `docs/architecture-decisions/` — long-term ADRs.
- `docs/source_backfills/` — JSONL/XLSX backfill data and dogfood/E2E archives.

Conflict precedence: explicit user instruction > safety/security > nearest AGENTS instructions > active handoff/spec > current code/tests > source-of-truth docs > old notes/reviews. If a handoff conflicts with a higher-level invariant, stop and report rather than guess.

## 4. Repository map

Mainline (data collection + Agentic RAG):

```text
apps/miroflow-agent/                Four-domain data collection + Agentic RAG core.
  conf/                             Hydra configs.
  scripts/                          50+ ingest / E2E / backfill / scan / Milvus / ORCID / release scripts.
                                    Pattern: run_<domain>_<verb>_e2e.py for real E2E,
                                    run_<thing>_backfill.py / run_*_scan.py for one-shot ops.
  alembic/versions/                 Postgres migrations V001–V018 (do not rewrite history).
  src/core/                         Pipeline entry/factory, orchestrator, tool executor,
                                    answer generator, stream handler.
  src/data_agents/
    contracts.py, evidence.py,      Shared contract layer (Pydantic). Outranks domain code.
    linking.py, normalization.py,
    publish.py, runtime.py
    canonical/                      Unified canonical schema (common/company/paper/professor/relations/source).
    taxonomy/                       Discipline hierarchy + seeds.
    quality/                        Quality thresholds + status enum.
    providers/                      Anthropic / Qwen / Dashscope / MiroThinker / web_search clients.
    storage/                        SQLite + Milvus + postgres/.
    service/                        retrieval.py + search_service.py — Agentic RAG service layer.
    company/, professor/, paper/,   Per-domain ingest, enrichment, exact/knowledge backfill, publish, import_xlsx.
    patent/
  src/llm/, src/io/, src/logging/,  Framework layers.
  src/config/, src/utils/

apps/admin-console/                 FastAPI backend + React/Vite SPA. User-facing chat + ops console.
  backend/api/
    chat.py                         /api/chat — classifier A/B/C/D/E/F/G + Serper fallback + reranker;
                                    SessionContext (entities, turns, last_result_set, TTL/cookie).
    dashboard.py, domains.py,       Ops & data-browser endpoints. /api/data/* legacy redirects to /api/{domain}.
    data.py, batch.py, export.py,
    pipeline.py, pipeline_issues.py,
    review.py, upload.py
  backend/storage/chat_session.py   Postgres-backed session store (V015/V016).
  frontend/src/                     React SPA. /chat (Round 9 P1-v1 MVP) and /browse (provenance/coverage/review).
  tests/                            chat / retrieval / professor / paper / review / upload tests.

libs/miroflow-tools/                Shared ToolManager, MCP servers, dev MCP servers.
```

Auxiliary (not mainline — modify only when targeted):
`apps/collect-trace/` (trace → SFT/DPO), `apps/gradio-demo/` (vLLM demo), `apps/visualize-trace/` (Flask dashboard), `apps/lobehub-compatibility/` (LobeChat adapter).

Coordination/state:
`.agents/specs/`, `.agents/handoffs/`, `.agents/reviews/`, `.agents/harness/`, `.agents/skills/`.

## 5. Big-picture architecture

Two pipelines share the same data-agent contract layer and storage:

**(a) Data collection pipeline** (offline, per-domain):

1. **Source ingest** — XLSX import (`import_xlsx.py`), homepage crawl (`run_homepage_paper_ingest.py`), company news (`run_company_news_ingest.py`), professor crawl V3 (`run_professor_*` scripts), patent xlsx (`run_patent_import_e2e.py`).
2. **Canonicalization & normalization** — `data_agents/canonical/*` + `normalization.py` produce unified schema rows (id prefixes: `PROF-`, `COMP-`, `PAPER-`, `PAT-`).
3. **Linking & enrichment** — cross-domain links via normalization + public evidence (`linking.py`, domain-local enrichers, ORCID/OpenAlex/S2 backfills).
4. **Quality gating** — `quality/` thresholds set `quality_status ∈ {ready, needs_review, low_confidence, needs_enrichment}`.
5. **Publish** — `publish.py` writes Postgres rows tagged with `run_id` (V007 trace).
6. **Vectorization** — Milvus collections `professor_profiles` / `paper_chunks` / `company_profiles` / `patent_profiles` populated via `run_milvus_backfill.py` and per-domain summary fields (`profile_summary`, `summary_zh`, `summary_text`).

Every row carries structured `evidence` (`source_type`, `source_url`, `fetched_at`, `snippet`, `confidence`) and a `run_id`. Evidence shape and Pydantic validation are load-bearing — do not weaken them.

**(b) Agentic RAG runtime** (online, `/api/chat`):

`chat.py` classifies the query into A/B/C/D/E/F/G/UNKNOWN, then routes:
- A: greeting/meta · B: single-domain factoid · C: cross-domain jump · D: multi-turn narrowing · E: web fallback (Serper) · F: out-of-scope · G: clarification · UNKNOWN → deterministic fallback.
- `service/retrieval.py` (`_VALID_DOMAINS = {professor, paper, company, patent}`) handles per-domain recall + fusion + rerank, preserving source traceability into the answer.
- Multi-turn state lives in `SessionContext` (entities stack, turns, `last_result_set`) backed by Postgres `chat_session` table (V015/V016). Full multi-turn design is not yet landed; treat current behavior as the source of truth.

When changing either pipeline, preserve: orchestration, rollback/failure handling, `run_id` traceability, evidence shape, classification A–G semantics, and the four-domain `_VALID_DOMAINS` boundary unless a plan explicitly expands it.

## 6. Common commands

Repository root:

```bash
uv sync
just lint                 # ruff check --fix
just format               # ruff format
just sort-imports         # ruff check --select I --fix
just format-md            # mdformat
just precommit            # lint + sort-imports + format-md + format
just check-license        # reuse lint
just frontend-fresh       # rebuild admin-console SPA into frontend/dist
just frontend-dev         # vite dev server :5180 (HMR; manual)
```

Admin-console runtime expects:

```bash
MILVUS_USE_REAL_CLIENT=1   # auto-set by backend/main.py if absent
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real
```

Agent app — tests and pipeline:

```bash
cd apps/miroflow-agent
uv run pytest                        # full suite (xdist)
uv run pytest tests/test_foo.py      # single file
uv run pytest -k "test_name"         # single test
uv run pytest -m unit                # markers: unit | integration | slow | requires_api_key
uv run pytest -n0                    # disable xdist (debugging)

# Real E2E ingest (require external services / credentials):
uv run python scripts/run_company_import_e2e.py
uv run python scripts/run_company_news_ingest.py
uv run python scripts/run_professor_crawler_e2e.py
uv run python scripts/run_homepage_paper_ingest.py
uv run python scripts/run_paper_release_e2e.py
uv run python scripts/run_paper_doi_verify.py
uv run python scripts/run_patent_import_e2e.py
uv run python scripts/run_milvus_backfill.py

# Agent benchmark / pipeline entry (Hydra):
uv run python -m src.core.pipeline agent=mirothinker_v1.5 llm=default benchmark=debug
```

Admin-console:

```bash
cd apps/admin-console
uv run pytest
# frontend tooling lives in frontend/; npm install / build / dev as needed.
```

Run the narrowest relevant check first, then broaden. Never claim completion without verification evidence or a clear reason a check could not run.

## 7. Non-negotiable invariants

- `docs/Data-Agent-Shared-Spec.md` outranks domain-local convenience.
- Evidence must remain structured, traceable, source-grounded, and suitable for user-facing audit.
- Domain modules may use independent physical schemas but must conform to shared logical contracts.
- Cross-domain linking uses normalization + public evidence, not ad-hoc heuristics.
- Structured outputs stay Pydantic-validated where the data-agent contract requires it.
- Do not silently change public APIs, serialized formats, benchmark output formats, or data contracts.
- Preserve query classification A–G semantics and the source-traceability of routing/fusion/rerank/answer generation unless a current spec changes them.
- `service/retrieval.py::_VALID_DOMAINS` is load-bearing; expanding online RAG domains requires a plan, contract tests, and traceability checks.
- Alembic V001–V018 history is immutable unless the user explicitly asks. Migration changes must be synchronized across DDL/Alembic/storage code/Pydantic models/tests/docs and reversible by default.
- Real E2E scripts may depend on external services or credentials; do not claim they passed unless they actually ran in the current session.
- Secrets, API keys, tokens, cookies, credentials must come from environment variables or approved secret managers — never hardcoded or logged.
- Repeatedly violated rules should become tests, lint rules, hooks, CI checks, or documented invariants rather than more prompt text.

## 8. Task classification

**Tiny**: typo, doc note, obvious local bug, reversible one- or two-file edit, no schema/API/auth/security/concurrency/performance impact. Inspect local context, apply the smallest fix or delegate it, run a narrow check, review the diff.

**Standard**: local feature, moderate refactor, user-visible behavior change, contract/test update. Flow: clarify goal and done criteria → write/update `.agents/specs/...` and `.agents/handoffs/...` → Codex implements/verifies → Claude reviews.

**Epic / Risky**: new feature area, core refactor, schema/storage/API change, trust boundary, auth/secrets, background jobs, retries, state machines, concurrency, idempotency, caching, performance-sensitive or multi-session work. Flow: pressure-test scope → lock architecture/invariants/validation → plan implementation slices → Codex implements each slice → Claude reviews each slice → durable lessons go to `docs/solutions/`.

**Pattern-fix**: invoke the `pattern-repair` skill (Claude Code: `.claude/skills/pattern-repair/SKILL.md`; Codex: `.agents/skills/pattern-repair/SKILL.md`) when the user says 系统性 / 同类问题 / 不要打补丁 / 根因 / 反复出现 / 全面检查 / 跨领域同样问题, or when a bug recurs after a previous fix in the same area. Pattern-fix is never a tiny fix. See `AGENTS.md §4` (Pattern-fix work subsection) for the Codex-side fallback.

## 9. Task artifacts

For Standard or Epic/Risky work, externalize state before implementation:

- `.agents/specs/<YYYY-MM-DD>-<slug>.md` — Claude-owned design contract (goal, user-visible behavior, non-goals, affected paths, architecture/data flow, interface/Pydantic expectations, invariants, edge cases, failure modes, validation commands, expected evidence, migration/rollback notes, assumptions, open questions).
- `.agents/handoffs/<YYYY-MM-DD>-<slug>.md` — Codex implementation handoff (spec path, slice scope, source docs to read, likely files, do-not rules, tests/checks, done criteria, what to report back).
- `.agents/reviews/<YYYY-MM-DD>-<slug>.md` — Claude review and accept/revise/reject decision.

When compacting or restarting, preserve task slug, artifact paths, acceptance criteria, changed files, commands/results, unresolved risks, and next owner.

## 10. Review and completion policy

Claude reviews Codex output against the approved contract, acceptance criteria, unchanged invariants, interface contracts, evidence traceability, touched-file boundaries, command output, security/trust boundaries, concurrency/retry/state/idempotency/performance risks, docs drift, and migration/rollback risk.

Do not declare done unless contract scope is implemented, relevant checks passed (or failures are explicitly explained), public docs are updated when behavior changed, no secrets are hardcoded, risks/assumptions/unsupported checks are stated, and Claude has decided accept / revise / reject.

## 11. Skills, plugins, and parallelism

Use skills/plugins as targeted harness components, not always-on rituals. Keep at most one planning framework before implementation; don't chain them. Keep detailed plugin command catalogs outside this file (`.agents/harness/skills.md` or tool-specific docs). Deterministic requirements belong in hooks, permissions, lint, tests, CI, or secret scans whenever possible.

Use targeted parallelism only when slices have clear file/interface boundaries, independent verification, and an obvious merge order. Prefer separate branches or git worktrees for multi-agent / multi-session work. One active writer per slice.

## 12. Protected files

Do not modify these unless the user explicitly asks or the task is specifically about harness/docs maintenance: `CLAUDE.md`, `AGENTS.md`, global agent config, unrelated CI/release/deployment config, secret templates, credential-related config, generated/vendor-looking files, raw datasets under `docs/source_backfills/`, and unrelated `.agents/...` artifacts.

## 13. Maintaining this file

Keep `CLAUDE.md` specific and compact. Remove stale generic rules. Link to deeper docs instead of duplicating them. Update `AGENTS.md` when Codex-facing behavior changes. Promote repeated mistakes into checks/docs/skills rather than expanding root instructions indefinitely.
