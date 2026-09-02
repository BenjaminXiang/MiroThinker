# AGENTS.md

Builder-facing SOP for all coding agents in this repo. `CLAUDE.md` owns
orchestration/review policy; this file owns execution discipline. Keep this file
compact and operational — detailed repeatable workflows live in `.agents/skills/`,
durable decisions live in `docs/` and `openspec/`, current work state lives in
`docs/plans/` (see §3).

---

## 0. Project context

深圳科创数据平台：面向深圳科创生态的对话式科创信息检索系统。用户通过 Web 用自然语言提问，系统在教授、企业、论文、专利四个数据域中智能路由检索，返回结构化、可追溯的回答。

- Stack: Python 3.12+, uv, Hydra, Ruff, Pydantic, SQLite/Postgres, Milvus, pytest, FastAPI, React/Vite.
- Current serving line: canonical-v2 isolated serving stack
  (`apps/miroflow-agent/src/data_agents/canonical_v2/` + `apps/admin-console/backend/services/canonical_v2_chat.py`),
  backed by a serving pack (lookup SQLite + Milvus Lite + relationships + vectors).
- Git discipline: work happens on feature/fix branches; `release/customer-test` is
  the customer-test hot-update line — only hot-update commits land there, and the
  replay suite (§6) must pass first. **Never push to the upstream
  `MiroMindAI/MiroThinker` org repo; `origin` is `BenjaminXiang/MiroThinker` only.**

---

## 1. Source of truth

Read order when working from a handoff or task contract:

```text
1. .agents/handoffs/<slug>.md                  current implementation slice
2. openspec/changes/<change-id>/               proposal, spec deltas, design, tasks, acceptance
3. openspec/specs/<capability>/spec.md         if the capability has been migrated
4. docs/Data-Agent-Shared-Spec.md, docs/*-PRD.md, docs/Agentic-RAG-*.md,
   docs/Multi-turn-*.md                        legacy behavior baseline until migrated
5. docs/plans/index.md                         human-side progress board (what is being fixed now)
6. local code and tests near touched files
7. .agents/specs/                              frozen historical context; never create files there
```

Conflict precedence:

```text
explicit user instruction
> safety/security constraints
> active OpenSpec change/specs
> migrated openspec/specs
> legacy behavior baseline for unmigrated capabilities
> current code/tests
> .agents/handoffs and .agents/runs execution artifacts
```

Execution artifacts may narrow a slice but never override OpenSpec or the legacy
baseline. If a behavior-affecting requirement is missing from the active change,
stop and report — do not silently broaden scope.

**Language rule:** all OpenSpec artifacts are written in English. Human docs under
`docs/plans/` are written in Chinese. Code comments/commit messages may be either.

---

## 2. Repository map

```text
apps/miroflow-agent/           data agents + Agentic RAG core
  src/data_agents/canonical_v2/  CURRENT serving stack (build + isolated serving + answer)
  src/data_agents/{professor,company,paper,patent}/  domain ingestion/quality modules
  src/data_agents/providers/     model/search providers (Bocha/Serper dual web lane)
  src/data_agents/storage/       SQLite / Milvus / Postgres storage
  src/data_agents/service/       retrieval.py + search_service.py (pre-canonical era)
  conf/ scripts/ tests/ alembic/ Hydra configs, E2E/backfill scripts, tests, migrations

apps/admin-console/            admin console + user-facing chat entry
  backend/services/canonical_v2_chat.py  current /api/chat/stream session logic
  backend/static/chat.html               user-facing /chat page (stream client)
  frontend/src/                           React SPA (source-side UI; sync /api/chat)
  scripts/replay_fix_round1.py            7-session replay regression gate (pre-hot-update)
  backend/api/, tests/                    dashboard/domain/review APIs and tests

libs/miroflow-tools/           shared ToolManager, MCP servers
docs/                          PRDs, plans (human docs), solutions, ADRs
openspec/                      changes/ + specs/ (agent-side contracts)
.agents/                       handoffs, runs, skills, harness
deploy/                        customer-test deployment runbooks
```

`apps/collect-trace/`, `apps/gradio-demo/`, `apps/visualize-trace/`,
`apps/lobehub-compatibility/` are historical; modify only when explicitly targeted.

Note: the user-facing `/chat` (backend static page, streaming) and the React SPA
(sync) are two coexisting frontends — confirm which one a task targets before
touching chat UI behavior.

---

## 3. Dual documentation system (SOP — user rule 2026-08-17/18)

Every fix or behavior-affecting work item maintains TWO synchronized doc systems.
A work item is not Accepted until both exist and are consistent.

1. **Human docs (给人看的)** — `docs/plans/`, Chinese: symptoms with verbatim
   transcripts, root-cause analyses, design rationale, execution narratives —
   what the product owner reads, discusses, and accepts.
2. **Agent docs (给 code agent 看的)** — `openspec/changes/<change-id>/` in English
   plus `.agents/runs/<change-id>/` verification artifacts. This system gates
   implementation.

Human doc taxonomy — write the document that answers the reader's question:

| Type | File | Answers | Mutation |
|---|---|---|---|
| index | `docs/plans/index.md` | what is being fixed, status, where details are | living |
| plan | `<date>-<slug>.md` | what to fix, how, what counts as fixed | freeze after approval |
| log | `<date>-<slug>-log.md` (one per round) | what was actually done and found | append-only |
| analysis | `<date>-<slug>.md` | why this problem happens | write once |
| research | `<date>-<slug>.md` | option space and trade-offs | write once |

Split an analysis/research doc out of the log only when it exceeds ~one screen;
otherwise keep it inside the log entry.

Mandatory rules (violating any is a defect of the slice):

- **Review flow (user rule 2026-08-18)**: the user does NOT review OpenSpec
  artifacts — they are agent-governed (validate, tasks, acceptance evidence).
  Never block implementation waiting for user review of `openspec/` files. The
  user reads and accepts work via the human doc system only: evidence reports
  at slice/phase boundaries and `docs/plans/` docs.

- **Index purity**: `index.md` links ONLY to human docs under `docs/plans/`. No
  change-ids, `openspec/` paths, `.agents/` paths, or tool paths in the index.
  The index is a problem-centric status board (id / one-line symptom / status /
  detail link); active round on the first screen, completed rounds one line,
  legacy grouped.
- **Progress = log**: each round keeps one append-only log; a phase/slice is done
  for the human reader only when it has a log entry (做了什么 → 发现 → 怎么验证 →
  影响哪些问题). OpenSpec `tasks.md` remains the agent-side tracker. Every slice
  that changes behavior/evidence/scope appends its log entry and updates the
  index in the same slice.
- **Cross-linking**: the plan/problem doc names its `<change-id>` in one line;
  the OpenSpec proposal/design links the human doc. Both systems update in the
  same slice.
- **写后确认 (terminal confirmation)**: after writing any document in either
  system, print a confirmation block before the next action — files written +
  one-line purpose, index updated?, log entry appended?, cross-links updated?,
  OpenSpec checkboxes ticked?. No silent doc writes.

---

## 4. Workflow

Establish the task contract before editing (Goal / Expected behavior / Context /
Constraints / Done when / Out of scope). State assumptions explicitly; when the
request admits multiple readings, surface them — never silently pick one. Where
a simpler approach than the requested one exists, say so; where the request
itself looks wrong, push back — do not silently build either.
Anything needing 3+ steps, 3+ files, or an architecture decision is at least
standard work. Then classify:

```text
tiny fix       obvious, local, reversible, 1–2 files, no contract/schema/security impact → fix + narrow check
standard work  local feature / refactor / contract change → short plan (files, slices, checks, invariants, rollback)
pattern fix    系统性/同类/根因/反复出现/patch-only → use .agents/skills/pattern-repair/SKILL.md (sibling search + shared fix + regression matrix)
risky work     new area, schema/API/public contract, auth/secrets, concurrency/retries, retrieval-critical, multi-agent → stop for re-planning first
```

**Anti-premature-action checks** (run all of these before writing any code):

- Confirm the real goal first: restate what "fixed" means for the user, not
  the first symptom reported.
- Read the system structure around the problem before touching it — trace the
  real call path and how the symptom actually triggers; place the problem at
  the layer it belongs to (UI vs prompt vs retrieval vs storage vs data), and
  distinguish user-visible surfaces from internal engineering objects — a
  symptom on a surface does not mean the fix belongs there.
- A recurring problem is treated as a structural defect first (pattern-fix
  class), not another local patch.
- Delete wrong logic before adding new logic: removing the cause of the error
  outranks compensating for it.
- Decide up front what this slice is — delete / refactor / implement / copy &
  UI-only — and say so in the plan; copy-and-UI changes must not be delivered
  as code changes.
- Define acceptance (how this will be verified, per the TDD boundary) before
  implementing; no acceptance criteria, no code.

**OpenSpec gate**: behavior-affecting work (user-visible behavior, public API or
data contract, business rules, RAG retrieval/fusion/rerank/answer/citation,
agent tool policy, permissions, error semantics, acceptance criteria) requires an
active OpenSpec change before code edits — Lite for tiny, Standard (with
design.md) for standard, Standard/Epic for pattern-fix. No change exists → stop
and report; builders do not create OpenSpec changes unless the user explicitly
asks for documentation/harness work. During implementation you may update
`tasks.md`, `acceptance.md`, `change-log.md`, and `.agents/runs/<id>/verification.md`.

**Slice lifecycle**: `Ready → In Progress → Candidate → Accepted`. Only implement
a Ready slice (OpenSpec change or slice contract exists). Candidate = implemented
+ verification evidence. Only Accepted slices may be depended on. Cannot reach
Candidate → stop and report the blocker.

**TDD boundary**: for behavior-affecting work, create/update
`.agents/runs/<change-id>/verification-contract.md` before production-code edits.
RED artifacts come from OpenSpec or the verification contract. For RAG/chat/
routing/prompt/policy work, a unit test alone is not sufficient GREEN evidence.
Detailed policy: `openspec/specs/development-methodology/spec.md`.

**Coding discipline** (every class above; bias caution over speed):

- Simplicity first: no unrequested features, speculative flexibility, or error
  handling for impossible cases. Pick solutions in order — skip it (YAGNI) →
  reuse existing helpers/patterns → stdlib → platform-native → installed
  dependencies → minimal new code — and only after reading the code about to be
  touched. Record runtime-environment constraints in comments rather than
  contorting code to adapt to them. Never simplify away trust-boundary
  validation, data-loss protection, security checks, or explicitly requested
  behavior. A deliberate shortcut gets a `debt:` comment naming its ceiling and
  upgrade path.
- Precise modification: every changed line traces back to the task contract; no
  drive-by "improvements" of adjacent code, comments, or formatting. Delete
  orphans your own change creates; leave pre-existing dead code alone and
  mention it instead. Challenge a non-trivial change once for a cleaner shape,
  but rewrite only code this change introduced.
- Goal-driven completion: a step is done only when proven — plan steps carry
  their own verify check (`step → verify: ...`); bug fix = a reproducing test
  that fails before and passes after; refactor = before/after equivalence
  evidence. If execution drifts from the plan, stop and re-plan rather than
  push through.
- Root-cause autonomy: clear-answer bug fixes go straight to the root cause —
  no stopgap patches, no waiting to be walked through; §8 still governs when
  to stop and escalate.
- Self-improvement loop: after each user correction, capture the
  anti-recurrence rule — repo lessons to `docs/solutions/` or the active plan
  log, cross-project preferences to persistent memory; repeated violations get
  promoted per §10 (test/lint/hook/CI or a rule here), not more prompt text.
- Sub-agents: delegate research, exploration, and parallel analysis — one task
  each, spawned for a need, not for compute's sake; decisions stay in the
  main context.

---

## 5. Project invariants

- `docs/Data-Agent-Shared-Spec.md` outranks domain-local convenience; domain
  modules may differ physically but must conform to shared logical contracts.
- Evidence stays structured, traceable, source-grounded; cross-domain linking
  uses normalization + public evidence, not ad-hoc heuristics; structured outputs
  stay Pydantic-validated where the contract requires.
- Query classification A–G semantics and RAG pipeline behavior change only via an
  active OpenSpec change; preserve source traceability end to end.
- Serving-pack / Milvus schema changes require retrieval tests plus
  backfill/rollback notes. Alembic migrations stay reversible unless the user
  accepts otherwise; never rewrite historical migrations.
- Import/backfill/release scripts remain idempotent or document why not; never
  mutate source backfills or raw datasets unless explicitly asked.
- Secrets only via env vars or approved key files; never hardcode or log
  credential-bearing payloads; no ambient credential/proxy behavior.
- Before any hot update to `release/customer-test`, the replay suite must pass.
- Prefer boring, inspectable, agent-legible designs; no heavy dependencies
  without justification; match nearby style; no drive-by refactors or broad
  formatting; do not weaken tests/validation/evidence checks to make a change pass.

---

## 6. Verification and commands

Run the smallest relevant checks; never say a command passed unless it ran
successfully this session. Validate behavior, not compilation. Add regression
tests for bug fixes when practical. When a check cannot run, report
command / blocker / confidence impact / next best command.

```bash
# repo root
uv sync && just lint && just format
# agent app
cd apps/miroflow-agent && uv run pytest [tests/test_foo.py | -k name | -m unit|integration|slow]
# admin console
cd apps/admin-console && uv run pytest
# fix-round replay gate (before every hot update; --base-url to hit a remote entry)
cd apps/admin-console && uv run python scripts/replay_fix_round1.py [--base-url URL]
```

Check focus by area: data-agent → contract/evidence shape/normalization/linking;
RAG/chat → classification, routing/fusion/rerank, traceability, replay
assertions; storage → migration dry-run + rollback; provider → failure/fallback
paths + credential/logging review; pattern-fix → reported-case regression +
sibling matrix.

---

## 7. Reporting

End every non-trivial task with:

```md
## Summary / Changed files / Verification (commands + outcomes) / Self-review
## Rollback / Risks / Suggested compounding
## OpenSpec — change-id, tasks n/m, acceptance n/m, change-log entries; or "not applicable: <why>"
## 文档确认块 — per §3 (index/log/cross-links/checkboxes)
```

Self-review bar: would a senior engineer approve this diff — nothing overbuilt,
nothing that cannot be traced back to the task contract?

Verification reporting must be layered (user rule 2026-08-18 — aggregate
"all green" counts are illegible): ① new tests written this slice (count,
what each cluster locks, fixture source — verbatim transcript / constructed
scenario); ② pre-existing regression suites (count, all-pass status); ③
replay / fault-injection evidence for RAG/chat-level claims. A bare total is
not an acceptable verification report.

For pattern-fix work add: reported case fixed / defect class / sibling patterns
searched / sibling issues fixed / not fixed and why / new invariant or test /
remaining systemic risk.

---

## 8. Stop-and-escalate conditions

Stop and request clarification or re-planning when: the change conflicts with an
active OpenSpec change, source-of-truth doc, or handoff; a needed
schema/storage/API/public-contract change is not in the active artifact;
behavior-affecting work lacks an OpenSpec change; the work crosses
auth/secrets/permissions/trust/production-data boundaries; the fix requires
broad rewrites or files outside the slice; expected behavior is ambiguous and
tests are missing; hidden concurrency/idempotency/migration/rollback risk
appears; sibling search reveals cross-module inconsistency needing architecture
decisions; the right resolution is a product decision, not implementation.

---

## 9. Protected files and parallelism

Do not modify unless explicitly asked or the task is harness/docs maintenance:
`CLAUDE.md`, `AGENTS.md`, global agent config, unrelated CI/release/deploy
config, secret templates, unrelated `.agents/` artifacts, production/source data,
generated/vendor-looking files.

Parallelism: one active writer per slice; separate branches/worktrees for
multi-agent work; never assume another agent's changes are present; re-check
context after any branch/worktree/dependency/generated-file change.

---

## 10. Maintaining this file

Update only for stable, project-wide rules; prefer deleting stale rules over
adding compensating paragraphs. Routing: task evidence → `.agents/runs/`;
reusable fix → `docs/solutions/`; architecture decision → `docs/architecture-decisions/`;
repeatable workflow → `.agents/skills/<name>/SKILL.md`; deterministic requirement
→ test/lint/hook/CI; always-needed rule → here. Human-doc work follows §3.
