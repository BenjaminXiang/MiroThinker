# AGENTS.md

Builder-facing repo guidance for Codex CLI and other coding agents.

This file is the execution companion to `CLAUDE.md`. Claude is the default designer/planner/reviewer for non-trivial product or architecture work. Codex is the default builder that implements approved slices, updates tests, runs checks, and reports evidence.

Keep this file compact and operational. Put detailed repeatable workflows in `.agents/skills/`, not here.

---

## 0. Operating principles

Optimize for correctness, traceability, regression resistance, and reversible diffs.

- Implement the requested slice exactly; do not silently broaden scope.
- Make every changed line traceable to the task, handoff, OpenSpec change, refactor contract, or invariant.
- Prefer small, local, boring changes over broad rewrites.
- Run the narrowest relevant checks first, then broaden when needed.
- Report exact commands, results, changed files, assumptions, risks, and skipped checks.
- Do not say a command passed unless it ran successfully in the current session.
- Do not weaken tests, schemas, validation, evidence checks, safety checks, or benchmark definitions to make a change pass.
- Do not silently change public APIs, serialized formats, benchmark outputs, data contracts, migrations, or RAG behavior.
- Do not hardcode secrets, API keys, tokens, cookies, credentials, or production data.
- Do not commit unless the user explicitly asks.

Use the lightest reliable workflow:

```text
tiny fix       -> inspect -> smallest safe fix -> narrow check -> diff review -> report
standard work  -> task contract -> context -> short plan -> Ready slice -> verify -> self-review -> report
pattern fix    -> pattern-repair -> defect class -> sibling search -> shared fix -> regression coverage -> report
risky work     -> stop for Claude planning before editing
```

Pattern-fix work and risky work are never tiny fixes.

---

## 1. Collision policy: AGENTS.md vs CLAUDE.md

`AGENTS.md` is operational guidance for builders. `CLAUDE.md` defines Claude's orchestration, review, and source-of-truth policy.

If the two files appear to conflict:

1. Do not guess.
2. Prefer active OpenSpec/refactor artifacts for the current task.
3. Follow this file for implementation/reporting behavior.
4. Stop and ask Claude/user to reconcile durable policy before broad edits.

Conflict precedence:

```text
explicit user instruction
> safety/security constraints
> active OpenSpec behavior contract
> active refactor contract for behavior-preserving refactors
> this AGENTS.md for builder execution
> CLAUDE.md for Claude orchestration/review
> current code/tests as evidence
> legacy docs and old .agents/specs
```

Current code/tests are evidence, not automatically desired behavior.

---

## 2. Source of truth and read order

When working from a handoff or task contract, read in this order:

```text
1. .agents/handoffs/<slug>.md
   Current implementation slice, do/do-not rules, validation expectations.

2. openspec/changes/<change-id>/
   Proposal, specs delta, design, tasks, acceptance, source-links, agent-links, change-log.

3. openspec/specs/<capability>/spec.md
   Current agreed behavior if migrated.

4. docs/Data-Agent-Shared-Spec.md, docs/*-PRD.md,
   docs/Agentic-RAG-*.md, docs/Multi-turn-*.md
   Legacy behavior baseline for unmigrated capabilities.

5. .agents/runs/<id>/
   Implementation plan, slice contracts, verification-contract, verification evidence.

6. Local code and tests near touched files.

7. .agents/specs/<date>-<slug>.md
   Historical context only. Do not create new files.

8. docs/solutions/ and docs/architecture-decisions/
   Only when directly relevant.
```

`.agents/handoffs/` and `.agents/runs/` are execution artifacts. They may narrow the implementation slice but cannot override OpenSpec or the legacy behavior baseline.

If a behavior-affecting requirement is missing from the active OpenSpec change, stop and report. Codex does not create new OpenSpec changes; Claude owns that. During implementation, Codex may update existing `tasks.md`, `acceptance.md`, `change-log.md`, and `.agents/runs/<id>/verification.md`.

---

## 3. Project context

深圳科创数据平台：面向深圳科创生态的对话式科创信息检索系统。用户通过 Web 用自然语言提问，系统在教授、企业、论文、专利四个数据域中智能路由检索，并返回结构化、可追溯的回答。

Baseline stack: Python 3.12+, uv, Hydra, Ruff, MCP/FastMCP, Anthropic/OpenAI SDKs, Playwright, E2B, Pydantic, SQLite/Postgres, Milvus, pytest + xdist + inline snapshots, FastAPI, React/Vite.

Use `docs/index.md` to distinguish authoritative docs from legacy/partial docs. Do not rely on stale implementation-status statements in root instructions if current code differs; inspect current code before changing behavior.

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

Invoke `pattern-repair` at `.agents/skills/pattern-repair/SKILL.md`. If unavailable, use the systemic repair policy in §8.

### Risky work

Stop for re-planning before editing if the task touches:

- new feature area or core refactor;
- schema/storage/API/public contract;
- auth, secrets, permissions, trust boundary, or production data;
- background jobs, retries, state machines, concurrency, idempotency, caching;
- performance-sensitive retrieval/RAG/runtime behavior;
- multi-session or multi-agent work;
- large changes not clearly covered by an active OpenSpec/refactor contract or handoff.

---

## 5. Workflow ownership and skill routing

Use installed skills/plugins by phase, not all at once.

```text
No skill              tiny local fixes, narrow doc edits, obvious changes
OpenSpec              behavior contract, acceptance, scope, RED/GREEN contract
Superpowers           execution discipline: planning, debugging, TDD, verification, review discipline
pattern-repair        systemic bugs, repeated issues, escaped defects, patch-only risk
Matt grill-with-docs  pre-spec clarification for vague/risky/domain-heavy work
Matt domain-modeling  stable glossary and ADR candidates only
Matt codebase-design  interface, seam, adapter, module boundary, testability review
Matt handoff          handoff document when changing session or agent
Matt test-design-review test quality review only; does not execute TDD
agent-browser         UI walkthroughs, browser checks, screenshots
compound-engineering  explicit-only; use only when the user asks for CE/Compound/ce-*
```

Anti-overlap rules:

- Use at most one planning framework before implementation.
- Skills do not override user instructions, safety constraints, OpenSpec, project invariants, or tests.
- OpenSpec owns expected behavior and verification intent.
- Superpowers may execute the workflow, but must not independently choose RED/GREEN for behavior-affecting work.
- Matt skills do not replace OpenSpec or Superpowers.
- Do not install or invoke Matt `tdd` as `/tdd` or `$tdd`.
- Do not use Matt `diagnosing-bugs` and Superpowers `systematic-debugging` together unless the user explicitly asks for a second opinion.
- If a named skill is unavailable, continue with the closest plain workflow and report that.

---

## 6. Anti-half-finished work policy

Non-trivial work must move through explicit states:

```text
Specified → Ready → In Progress → Candidate → Accepted → Archived
```

Rules:

1. Codex may only implement a `Ready` slice.
2. A `Ready` slice must have an OpenSpec change, refactor contract, or slice contract.
3. `In Progress` is not done.
4. `Candidate` means implementation and verification evidence exist, but Claude has not accepted it.
5. Only `Accepted` slices may be used as dependencies by later slices.
6. If a slice cannot reach `Candidate`, stop and report the blocker; do not broaden scope.
7. Do not start the next slice until the previous slice is `Accepted` or explicitly abandoned.

If no portfolio exists, suggest creating `.agents/portfolio.md`, but do not create it unless requested or the current task is harness maintenance.

---

## 7. Slice contract

Before implementing a non-trivial slice, ensure the handoff or `.agents/runs/<id>/slices/<slice>.md` defines:

```md
# Slice Contract: <slug>

## Status
Ready / In Progress / Candidate / Accepted / Rejected

## Parent
- OpenSpec change: `openspec/changes/<change-id>/`
- Or refactor contract: `.agents/runs/<refactor-id>/refactor-contract.md`

## Goal

## Non-goals

## Allowed scope

## Forbidden changes

## Expected unchanged behavior

## Required checks

## Evidence to update

## Stop conditions

## Done means
```

Stop if the slice is not independently testable, reviewable, and reversible.

---

## 8. Systemic repair policy

A systemic repair is not complete until it includes:

1. reported-case reproduction or evidence;
2. defect class;
3. sibling search scope and results;
4. shared fix or explicit reason no shared fix exists;
5. regression coverage for the reported case;
6. regression or invariant coverage for sibling cases;
7. remaining systemic risk;
8. reusable lesson, test, hook, ADR, or docs entry when applicable.

Do not close systemic repair by fixing only the reported line.

Pattern-fix report:

```md
## Pattern-fix report
- Reported case fixed:
- Defect class:
- Sibling patterns searched:
- Sibling issues found/fixed:
- Not fixed and why:
- New invariant/helper/contract/test:
- Remaining systemic risk:
```

---

## 9. OpenSpec gate

OpenSpec artifacts must be written in English.

OpenSpec is required iff the work is behavior-affecting: user-visible behavior, public API or data contract, business rules, query classification A-G semantics, RAG retrieval/fusion/rerank/answer/citation behavior, agent tool-use policy, permissions, data lifecycle, error semantics, or acceptance criteria.

Behavior-affecting work must have:

```text
openspec/changes/<change-id>/proposal.md
openspec/changes/<change-id>/specs/
openspec/changes/<change-id>/design.md      # optional for Lite, required for Standard/Epic
openspec/changes/<change-id>/tasks.md
openspec/changes/<change-id>/acceptance.md
.agents/runs/<change-id>/verification-contract.md
.agents/runs/<change-id>/verification.md
```

Codex may update existing per-change artifacts:

```text
openspec/changes/<id>/tasks.md
openspec/changes/<id>/acceptance.md
openspec/changes/<id>/change-log.md
.agents/runs/<id>/verification.md
```

Codex must not create new OpenSpec changes unless the user explicitly asks it to do documentation/harness work.

`.agents/specs/` is frozen legacy. Do not create new files there.

---

## 10. Refactor contract

Behavior-preserving refactors do not require OpenSpec by default, but risky refactors require:

```text
.agents/runs/<refactor-id>/refactor-contract.md
.agents/runs/<refactor-id>/verification.md
```

A behavior-preserving refactor must preserve public API, serialized format, data contract, RAG semantics, evidence shape, migration semantics, and acceptance criteria unless an approved OpenSpec change says otherwise.

Stop and re-plan if:

- behavior change appears;
- public contracts need to change;
- expected behavior is ambiguous and tests are missing;
- the slice spreads across unrelated modules;
- rollback becomes unclear;
- verification evidence is insufficient.

---

## 11. TDD and test design

Superpowers owns RED → GREEN → REFACTOR execution.

For behavior-affecting work, the RED artifact must come from OpenSpec or `.agents/runs/<change-id>/verification-contract.md`.

Matt TDD principles enter only through `test-design-review`:

- test observable behavior, not implementation detail;
- exercise public interfaces;
- prefer integration-style tests through real code paths;
- mock only system boundaries;
- avoid private methods, internal call counts, and implementation order;
- use vertical slices;
- treat hard-to-write tests as design feedback.

Do not invoke Matt `/tdd` or `$tdd`.

For Agentic RAG/chat, routing, prompt, memory, tool-choice, policy, or badcase work, a unit test alone is not sufficient GREEN evidence.

---

## 12. Context loading

Load context surgically. Do not scan the whole repo by default.

Before planning or editing, identify:

- nearby implementation patterns;
- relevant tests and fixtures;
- Pydantic models, public APIs, schemas, serialized formats, benchmark outputs;
- authoritative vs legacy/partial docs in `docs/index.md`;
- relevant prior solutions or ADRs only if directly applicable.

For pattern-fix work, run targeted repository-wide searches for sibling patterns, shared helpers, contracts, tests, routes, prompts, state fields, config surfaces, and pipeline stages before choosing the fix level.

Useful searches:

```bash
rg -n "query_class|classifier|rerank|Serper|SessionContext" apps/admin-console apps/miroflow-agent tests docs
rg -n "evidence|source|trace|citation|provenance|Pydantic|BaseModel" apps/miroflow-agent tests docs
rg -n "Milvus|vector|embedding|fusion|recall|_VALID_DOMAINS" apps/miroflow-agent apps/admin-console tests docs
rg -n "canonical|normalization|linking|canonical_name|orcid|run_id" apps/miroflow-agent tests docs
rg -n "secret|token|api_key|cookie|credential|Authorization" . --glob '!**/.venv/**'
```

---

## 13. Project invariants

### Data-agent contract

- `docs/Data-Agent-Shared-Spec.md` outranks domain-local convenience.
- Domain modules may use independent physical schemas but must conform to shared logical contracts.
- Evidence must remain structured, traceable, source-grounded, and suitable for user-facing audit.
- Cross-domain linking must use normalization plus public evidence, not ad-hoc heuristics.
- Structured outputs must stay Pydantic-validated where the data-agent contract requires it.
- Quality thresholds, canonical schema, normalization, and linking behavior must remain testable.
- Do not silently change public APIs, serialized formats, benchmark output formats, or data contracts.

### Agentic RAG and chat

- Preserve query classification A-G semantics unless a current spec changes them.
- Routing, semantic recall, fusion, rerank, and answer generation must preserve source traceability.
- `/api/chat` behavior should match active OpenSpec or current code when unmigrated.
- Multi-turn context is partially implemented unless current code says otherwise.
- Serper fallback, reranker behavior, and domain coverage must be validated when touched.
- Domain expansion requires plan, contract tests, and traceability checks.

### Storage and migrations

- Migration changes require synchronized updates across DDL/Alembic, storage code, Pydantic models, tests, and docs where applicable.
- Alembic migrations must be reversible unless the user explicitly accepts an irreversible migration.
- Do not rewrite historical migrations unless explicitly instructed.
- Milvus collection/schema changes require retrieval tests and backfill/rollback notes.

### Security and maintainability

- Secrets, API keys, tokens, cookies, and credentials must come from environment variables or approved secret managers.
- Never hardcode secrets or log credential-bearing payloads.
- Prefer boring, inspectable, agent-legible designs over clever abstractions.
- Do not introduce heavy dependencies without explicit justification and approval.

---

## 14. Verification

Use the handoff's validation commands when present. Otherwise run the smallest relevant checks.

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

## 15. Common commands

Repository root:

```bash
uv sync
just lint
just format
just sort-imports
just precommit
just check-license
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

## 16. Reporting

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

## OpenSpec / Refactor contract
- Change/refactor id:
- tasks.md status:
- acceptance.md / verification.md evidence:
- Not applicable because:

## Rollback / checkpoint
- <How to revert or current checkpoint status>

## Risks / assumptions / skipped checks
- <Any remaining risk or none>

## Suggested compounding
- <Lesson/doc/skill/test/hook suggestion, or "None">
```

For pattern-fix work, also include the Pattern-fix report from §8.

---

## 17. Stop-and-escalate conditions

Stop and request clarification or re-planning when:

- requested change conflicts with source-of-truth docs, active OpenSpec, refactor contract, or handoff;
- schema/storage/API/public contract change is needed but not in the active artifact;
- behavior-affecting work lacks an active OpenSpec change;
- implementation crosses security, auth, secrets, permissions, trust boundary, or production-data boundaries;
- fix requires broad rewrites, unrelated cleanup, or many files outside the slice;
- required tests or fixtures are missing and expected behavior is ambiguous;
- existing unrelated test failures reduce confidence;
- hidden performance, concurrency, retry, idempotency, migration, or rollback risk appears;
- sibling search reveals cross-module inconsistency requiring schema/API/routing/domain decisions;
- the correct resolution is product or architecture decision rather than implementation.

---

## 18. Protected files and multi-agent work

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

Parallelism rules:

- one active writer per slice;
- use separate branches or git worktrees for multi-agent or multi-session work;
- do not assume another agent's changes are present unless visible in the working tree;
- re-check local context after any branch, worktree, dependency, or generated-file change.

---

## 19. Maintaining this file

Update `AGENTS.md` only for stable, project-wide builder rules.

Use the lightest durable form:

```text
task-specific review evidence -> .agents/reviews/
current task progress          -> .agents/runs/ or .agents/handoffs/
portfolio state                -> .agents/portfolio.md
reusable technical fix         -> docs/solutions/
architecture decision          -> docs/architecture-decisions/
workflow/harness rule          -> docs/agents/ or .agents/harness/
repeatable workflow            -> .agents/skills/<skill-name>/SKILL.md
deterministic requirement      -> test / lint / hook / CI / config
always-needed builder rule     -> AGENTS.md
```

Prefer deleting stale rules over adding compensating paragraphs.
