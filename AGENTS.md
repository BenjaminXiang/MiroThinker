# AGENTS.md

Builder-facing repo guidance for Codex CLI and other coding agents.

This file is the execution companion to `CLAUDE.md`: Claude is the default designer/planner/reviewer for non-trivial product or architecture work; Codex is the default builder that implements approved slices, updates tests, runs checks, and reports evidence.

Keep this file compact and operational. Put detailed repeatable workflows in `.agents/skills/`, not here.

Recommended systemic-fix skill:

```text
.agents/skills/pattern-repair/SKILL.md
```

---

## 0. Operating principles

Optimize for correctness, traceability, regression resistance, and reversible diffs.

- Implement the requested slice exactly; do not silently broaden scope.
- Make every changed line traceable to the task, handoff, spec, or invariant.
- Prefer small, local, boring changes over broad rewrites.
- Run the narrowest relevant checks first, then broaden when needed.
- Report exact commands, results, changed files, assumptions, risks, and skipped checks.
- Do not say a command passed unless it ran successfully in the current session.
- Do not weaken tests, schemas, validation, evidence checks, or safety checks to make a change pass.
- Do not silently change public APIs, serialized formats, benchmark outputs, data contracts, or migration expectations.
- Do not hardcode secrets, API keys, tokens, cookies, credentials, or production data.
- Do not commit unless the user explicitly asks.

Use the lightest reliable workflow:

```text
tiny fix      -> inspect -> smallest safe fix -> narrow check -> diff review -> report
standard work -> task contract -> context -> short plan -> slices -> verify -> self-review -> report
pattern fix   -> use pattern-repair -> diagnose -> sibling search -> shared fix -> regression coverage -> report
risky work    -> stop for re-planning before editing
```

Pattern-fix work and risky work are never tiny fixes.

---

## 1. Project context

深圳科创数据平台：面向深圳科创生态的对话式科创信息检索系统。用户通过 Web 用自然语言提问，系统在教授、企业、论文、专利四个数据域中智能路由检索，并返回结构化、可追溯的回答。

The project builds on the MiroThinker deep-research agent framework. It reuses agent runtime, multi-turn tool orchestration, search/scrape/extract capabilities, and adds four-domain data collection agents plus an Agentic RAG service layer.

Baseline stack: Python 3.12+, uv, Hydra, Ruff, MCP/FastMCP, Anthropic/OpenAI SDKs, Playwright, E2B, Pydantic, SQLite/Postgres, Milvus, pytest + xdist + inline snapshots, FastAPI, React/Vite.

---

## 2. Source of truth and read order

When working from a handoff, read in this order:

1. `.agents/handoffs/<date>-<slug>.md` — implementation slice, do/do-not rules, validation expectations.
2. `.agents/specs/<date>-<slug>.md` — design contract, acceptance criteria, invariants, edge cases.
3. Source-of-truth docs below.
4. Local code and tests near touched files.
5. `docs/solutions/` only when directly relevant.

Source-of-truth docs:

```text
docs/index.md
  Documentation index and implementation-status matrix. Read first to distinguish authoritative docs from legacy/partial docs.

docs/Data-Agent-Shared-Spec.md
  Shared data-agent architecture, logical contracts, quality standards, MiroThinker mapping. This outranks domain-local convenience.

docs/{Company,Professor,Paper,Patent}-Data-Agent-PRD.md
  Domain-specific requirements.

docs/Agentic-RAG-PRD.md
  Query classification A–G, semantic routing, multi-source recall/fusion/rerank.

docs/Agentic-RAG-Operating-Guide.md
  Current online /api/chat operating posture, dogfood, rollback, and monitoring.

docs/Multi-turn-Context-Manager-Design.md
  Multi-turn reference resolution and cross-domain transition design. Only partially implemented unless current code says otherwise.

docs/plans/index.md / docs/solutions/index.md
  Active/completed plans and reusable lessons.

docs/architecture-decisions/
  Long-term ADRs.
```

Conflict precedence:

```text
explicit user instruction
> safety/security constraints
> nearest AGENTS instructions
> active handoff/spec
> current code/tests
> source-of-truth docs
> old notes/reviews
```

If a handoff conflicts with a higher-level invariant or source-of-truth doc, stop and report the conflict instead of guessing.

---

## 3. Repository map

Current mainline:

```text
apps/miroflow-agent/     Four-domain data collection and Agentic RAG core.
apps/admin-console/      Admin console plus user-facing chat entry.
libs/miroflow-tools/     Shared ToolManager, MCP servers, dev MCP servers.
docs/                    PRDs, architecture, plans, solutions, ADRs, source backfills.
.agents/                 specs, handoffs, reviews, harness notes, skills.
```

Important `apps/miroflow-agent/` areas:

```text
conf/                    Hydra configs.
scripts/                 E2E, import, backfill, scan, Milvus, ORCID, release scripts.
tests/                   pytest suites.
alembic/versions/        Postgres migrations V001–V011.
src/core/                pipeline entry/factory, orchestrator, tool executor, answer generator, stream handler.
src/data_agents/         domain agents and service layer.
src/data_agents/canonical/ unified canonical schema.
src/data_agents/taxonomy/  discipline hierarchy and seeds.
src/data_agents/quality/   quality thresholds.
src/data_agents/providers/ model/search providers.
src/data_agents/storage/   SQLite / Milvus / postgres storage.
src/data_agents/service/   retrieval.py + search_service.py.
```

Known current constraint:

```text
src/data_agents/service/search_service.py currently has _VALID_DOMAINS limited to professor/paper.
Do not assume company/patent are online RAG domains unless current code/docs explicitly confirm.
Expanding online RAG domains requires plan, contract tests, and traceability checks.
```

Important `apps/admin-console/` areas:

```text
backend/api/chat.py      /api/chat; classifier A/B/D/E/F/G + limited C; in-memory SessionContext;
                         Round 11 v3.1 D/E/G handlers; Serper fallback + reranker.
backend/api/*.py         dashboard, domains, data, batch, export, pipeline, review, upload.
frontend/src/            React SPA; /chat, Dashboard, DomainList, RecordDetail.
tests/                   chat, retrieval, professor/paper API, review API tests.
```

Auxiliary/historical apps are not current mainline. Modify only when explicitly targeted:

```text
apps/collect-trace/
apps/gradio-demo/
apps/visualize-trace/
apps/lobehub-compatibility/
```

---

## 4. Task classification

Before editing, establish the task contract:

```text
Goal:
Expected behavior / invariant:
Context:
Constraints:
Done when:
Out of scope:
```

### Tiny work

Proceed directly only when the change is obvious, local, reversible, limited to one or two nearby files, and has no schema/API/auth/security/concurrency/performance/data-contract/product impact.

### Standard work

Use for local features, moderate refactors, user-visible behavior changes, contract/test updates, or multi-file work inside a known module.

Write a short plan before editing:

```md
## Plan
- Files/areas:
- Implementation slices:
- Tests/checks:
- Invariants:
- Rollback note:
```

### Pattern-fix work

Use `pattern-repair` when the user says 系统性、同类问题、类似问题、不要打补丁、不要单点修复、根因、反复出现、全面检查、跨领域同样问题、第二次出现, patch-only, systemic, recurring, regression, escaped defect, sibling pattern, root cause, defect class, system-wide, or when a bug appears after a previous fix in the same feature area.

Invoke `pattern-repair` (`.agents/skills/pattern-repair/SKILL.md`). If the skill file is unavailable, fall back to the 9-line Diagnosis block from `pattern-repair` Phase 1 and the Pattern-fix report in §11.

### Risky work

Stop for re-planning before editing if the task touches:

- new feature area or core refactor;
- schema/storage/API/public contract;
- auth, secrets, permissions, trust boundary, or production data;
- background jobs, retries, state machines, concurrency, idempotency, caching;
- performance-sensitive retrieval/RAG/runtime behavior;
- multi-session or multi-agent work;
- large changes not clearly covered by a handoff/spec.

---

## 5. Skill routing

Use installed skills/plugins by phase, not all at once.

```text
No skill          tiny local fixes, narrow doc edits, obvious changes.
ce-work           ordinary bounded implementation.
ce-debug          repeated failures, hard-to-reproduce bugs, provider/integration errors.
ce-code-review    explicit review requests.
ce-doc-review     explicit documentation review requests.
agent-browser     admin-console chat checks, UI walkthroughs, browser tests, screenshots.
pattern-repair    systemic bugs, repeated issues, escaped defects, patch-only risk.
```

Anti-overlap rules:

- Use at most one planning framework before implementation.
- Skills do not override user instructions, safety constraints, project invariants, or tests.
- If a named skill is unavailable, continue with the closest plain workflow and report that.

---

## 6. Context loading

Load context surgically. Do not scan the whole repo by default.

Before planning or editing, identify:

- nearby implementation patterns;
- relevant tests and fixtures;
- Pydantic models, public APIs, schemas, serialized formats, benchmark outputs;
- authoritative vs legacy/partial docs in `docs/index.md`;
- relevant prior solutions or ADRs only if directly applicable.

Exception: for pattern-fix work, run targeted repository-wide searches for sibling patterns, shared helpers, contracts, tests, routes, prompts, state fields, config surfaces, and pipeline stages before choosing the fix level.

Useful targeted searches:

```bash
rg -n "query_class|classifier|rerank|Serper|SessionContext" apps/admin-console apps/miroflow-agent tests docs
rg -n "evidence|source|trace|citation|provenance|Pydantic|BaseModel" apps/miroflow-agent tests docs
rg -n "Milvus|vector|embedding|fusion|recall|_VALID_DOMAINS" apps/miroflow-agent apps/admin-console tests docs
rg -n "canonical|normalization|linking|canonical_name|orcid|run_id" apps/miroflow-agent tests docs
rg -n "secret|token|api_key|cookie|credential|Authorization" . --glob '!**/.venv/**'
```

---

## 7. Project invariants

### Data-agent contract

- `docs/Data-Agent-Shared-Spec.md` outranks domain-local convenience.
- Domain modules may use independent physical schemas but must conform to shared logical contracts.
- Evidence must remain structured, traceable, source-grounded, and suitable for user-facing audit.
- Cross-domain linking must use normalization plus public evidence, not ad-hoc heuristics.
- Structured outputs must stay Pydantic-validated where the data-agent contract requires it.
- Quality thresholds, canonical schema, normalization, and linking behavior must remain testable.
- Do not silently change public APIs, serialized formats, benchmark output formats, or data contracts.

### Agentic RAG and chat

- Preserve query classification A–G semantics unless a current spec changes them.
- Routing, semantic recall, fusion, rerank, and answer generation must preserve source traceability.
- `/api/chat` behavior should match `docs/Agentic-RAG-Operating-Guide.md` and current `chat.py`.
- Multi-turn context is only partially implemented unless current code says otherwise.
- Serper fallback, reranker behavior, and domain coverage must be validated when touched.
- `_VALID_DOMAINS` limited to professor/paper is load-bearing until a plan expands it.

### Data collection and pipeline runtime

- Pipeline changes must preserve orchestration, rollback/failure handling, output modes, and run traceability.
- Import/backfill/release scripts should remain idempotent or explicitly document when they are not.
- Real E2E scripts may depend on external services or credentials; do not claim they passed unless they actually ran.
- Do not mutate source backfills, raw datasets, or reference assets unless explicitly asked.

### Storage and migrations

- Migration changes require synchronized updates across DDL/Alembic, storage code, Pydantic models, tests, and docs where applicable.
- Alembic migrations must be reversible unless the user explicitly accepts an irreversible migration.
- Preserve V001–V011 history; do not rewrite historical migrations unless explicitly instructed.
- Milvus collection/schema changes require retrieval tests and backfill/rollback notes.

### Security and maintainability

- Secrets, API keys, tokens, cookies, and credentials must come from environment variables or approved secret managers.
- Never hardcode secrets or log credential-bearing payloads.
- Do not introduce ambient credential/proxy behavior without an explicit reason.
- Security, auth, permission, and production-data boundaries require explicit planning.
- Prefer boring, inspectable, agent-legible designs over clever abstractions.
- Do not introduce heavy dependencies without explicit justification and approval.
- Keep experimental paths separated from production paths.

---

## 8. Implementation standards

- Match local style and nearby patterns before introducing abstractions.
- Preserve type hints, Pydantic models, validation boundaries, and existing error-handling conventions.
- Keep data transformations explicit and testable.
- Prefer dependency injection or configuration over hidden globals.
- Preserve idempotency, retry semantics, and state-machine transitions unless explicitly changed by the handoff.
- Avoid drive-by refactors, broad formatting, and unrelated cleanup.
- Do not weaken tests, skip assertions, or change benchmark definitions just to make results pass.
- When modifying generated or vendored-looking files, first verify they are intended to be edited directly.

---

## 9. Verification

Use the handoff’s validation commands when present. Otherwise run the smallest relevant checks.

Before reporting completion:

- run relevant tests/checks, or clearly state why they could not run;
- include exact commands and outcomes;
- validate behavior, not just compilation;
- add regression tests for bug fixes when practical;
- update docs/tests when public behavior changes;
- never say “all tests pass” unless relevant tests actually passed in the current session.

Suggested matrix:

```text
Pure logic:             nearest unit test; lint/type if imports or typing changed.
Data-agent:             contract behavior, evidence shape, normalization/linking, domain edge cases.
Agentic RAG/chat:       classification, routing/fusion/rerank, source traceability, /api/chat tests.
Pipeline/runtime:       orchestration, rollback/failure handling, output modes, relevant E2E if available.
Storage/schema:         migration/dry-run, storage integration, rollback/backfill impact.
Provider/tooling:       client tests, failure/fallback tests, credential/logging review.
Admin UI/API:           backend API tests; frontend lint/type/test or browser walkthrough when relevant.
Pattern-fix:            reported-case regression + sibling-case matrix/invariant test + targeted re-check.
```

When a check cannot run, report:

```text
Command:
Blocker:
Confidence impact:
Next best command:
```

---

## 10. Common commands

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

Admin console:

```bash
cd apps/admin-console
uv run pytest
# If frontend tooling is present:
# npm install
# npm run lint
# npm run test
# npm run build
```

Do not run broad formatting over unrelated files unless the task is explicitly a formatting/lint cleanup.

---

## 11. Self-review and reporting

Before reporting completion, review the final diff:

- Does every changed line trace to the task?
- Did the implementation stay within the requested slice?
- Are source-of-truth docs and invariants preserved?
- Are Pydantic validation boundaries, data contracts, evidence shape, and traceability preserved?
- Are public APIs, serialized formats, benchmark outputs, and migration expectations unchanged unless explicitly requested?
- Are secrets, credentials, tokens, cookies, and production data absent from code and logs?
- Are tests meaningful rather than weakened?
- For pattern-fix work: did the fix address the defect class, not only the reported case?

End every non-trivial task with:

```md
## Summary
- <What changed>

## Changed files
- `<path>` - <reason>

## Verification
- `<command>` - <result>
- `<command not run>` - <why>

## Self-review
- Scope control:
- Invariants preserved:
- Risks checked:

## Rollback / checkpoint
- <How to revert or current checkpoint status>

## Risks / assumptions / skipped checks
- <Any remaining risk or none>

## Suggested compounding
- <Lesson/doc/skill/test/hook suggestion, or "None">
```

For pattern-fix work, also include the section below. The skill at `.agents/skills/pattern-repair/SKILL.md` produces an extended version with sibling-search lanes; use that when the skill is active.

```md
## Pattern-fix report
- Reported case fixed:
- Sibling patterns searched:
- Sibling issues found/fixed:
- Not fixed and why:
- New invariant/helper/contract/test:
- Remaining systemic risk:
```

---

## 12. Stop-and-escalate conditions

Stop and request clarification or re-planning when:

- the requested change conflicts with `docs/Data-Agent-Shared-Spec.md`, a design contract, or a handoff;
- the work requires a schema/storage/API/public contract change not listed in the handoff;
- the implementation crosses security, auth, secrets, permissions, trust-boundary, or production-data boundaries;
- the fix requires broad rewrites, unrelated cleanup, or many files outside the slice;
- required tests or fixtures are missing and expected behavior is ambiguous;
- existing unrelated test failures reduce confidence;
- hidden performance, concurrency, retry, idempotency, migration, or rollback risk appears;
- a dependency, tool, or environment requirement is missing and cannot be safely inferred;
- the correct resolution is a product or architecture decision rather than implementation.

For pattern-fix work, stop and re-plan when sibling search reveals cross-module inconsistency that requires schema/API/routing/domain-coverage decisions.

---

## 13. Protected files and multi-agent work

Do not modify these unless the user explicitly asks or the task targets harness/docs maintenance:

```text
CLAUDE.md
AGENTS.md
global agent config
unrelated CI/release/deployment config
secret templates or credential-related config
unrelated .agents/... artifacts
production or business source data
generated/vendor-looking files unless confirmed editable
```

When editing `.agents/specs/`, `.agents/handoffs/`, `.agents/reviews/`, `.agents/harness/`, or `.agents/skills/`, preserve task slug, acceptance criteria, changed files, command results, unresolved risks, and next owner.

Parallelism rules:

- one active writer per slice;
- use separate branches or git worktrees for multi-agent or multi-session work;
- do not assume another agent’s changes are present unless visible in the working tree;
- re-check local context after any branch, worktree, dependency, or generated-file change.

---

## 14. Maintaining this file

Update `AGENTS.md` only for stable, project-wide rules.

Use the lightest durable form:

```text
task-specific review evidence -> .agents/reviews/
current task progress          -> .agents/progress.md or .agents/handoffs/
reusable technical fix         -> docs/solutions/
architecture decision          -> docs/architecture-decisions/
workflow/harness rule          -> .agents/harness/
repeatable workflow            -> .agents/skills/<skill-name>/SKILL.md
deterministic requirement      -> test / lint / hook / CI / config
always-needed repo rule        -> AGENTS.md
```

Prefer deleting stale rules over adding compensating paragraphs. Keep detailed repeatable workflows in skills.
