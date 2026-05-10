# Acceptance: resolve-professor-canonical-baseline

This file is filled in two passes: (1) when the change is proposed, the criteria are committed; (2) during execution, the Evidence sections are filled with verification output. The change archives only when every checkbox below is checked or explicitly reasoned-away in writing.

## 1. Audit doc tracked — debt `audit-doc-untracked-001`

- [ ] `git ls-files | grep "Professor-Data-Agent-Requirements-Audit-2026-05-09.md"` returns the file path
- [ ] File path is exactly `docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md` (no rename, no relocation)
- [ ] Body content unchanged from working-tree state at proposal time (frontmatter extension via T1.2 is the only permitted edit; if T1.2 was skipped, the rationale is recorded in Evidence below)
- [ ] One commit message names this change ID

## 2. PRD legacy marking — debt `professor-canonical-pivot-001`

- [ ] `docs/Professor-Data-Agent-PRD.md` opens with frontmatter declaring `status: legacy` and `superseded_by: docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md`
- [ ] `docs/index.md` Professor row reflects: Audit canonical / PRD legacy (status symbols match index conventions)
- [ ] `CLAUDE.md §3` Source-of-truth docs Professor entry names the Audit as canonical and the PRD as legacy reference
- [ ] No other section of `CLAUDE.md` is touched
- [ ] No body section of `docs/Professor-Data-Agent-PRD.md` is rewritten or deleted

## 3. Stale change disposed — debts `professor-prd-change-001` + `professor-prd-change-002`

- [ ] T3.1 verification of PRD ↔ refine-change actually-shipped status is recorded in Evidence below before T3.2 decision is taken
- [ ] T3.2 disposition is one of {archive, re-target, abandon} and the chosen path is recorded in Evidence below
- [ ] T3.3 execution matches T3.2 decision; no in-flight half-state (e.g. archived in ledger but files still in `openspec/changes/`)
- [ ] `openspec/change-ledger.md` reflects the chosen state for `refine-professor-data-agent-prd`
- [ ] `professor-prd-change-002` is resolved consistent with the T3 outcome (resolved-by-archive / deferred to new change / wontfix)

## 4. Debt register updated

- [ ] `openspec/debt-register.md` Open table no longer contains `audit-doc-untracked-001`, `professor-canonical-pivot-001`, `professor-prd-change-001`
- [ ] `openspec/debt-register.md` Resolved table (or equivalent) contains the four entries with back-references to `resolve-professor-canonical-baseline`
- [ ] No new debt entries were created by this change (any new doc-debt discovered would belong to a different change)

## 5. Inventory consistency

- [ ] `docs/data-agent-domain-index.md §Phase 1B / 1C scope` no longer lists the three Professor bullets as pending
- [ ] `docs/data-agent-domain-index.md §Domain 4: Professor` Canonical baseline recommendation row is unchanged (Audit is and remains canonical)

## 6. This change registered and archived

- [ ] `openspec/change-ledger.md` Active table contains `resolve-professor-canonical-baseline` during T1–T3
- [ ] `openspec/change-ledger.md` Archived table contains `resolve-professor-canonical-baseline` after T4.3
- [ ] `openspec/changes/resolve-professor-canonical-baseline/` directory remains in place after archive (per `CLAUDE.md §14.4` archive workflow)

## 7. Non-goals not violated

- [ ] No file under `apps/`, `libs/`, or `src/` was modified
- [ ] No Pydantic contract changed
- [ ] No Alembic migration added or modified
- [ ] No new Professor data requirement was introduced (Audit content unchanged)
- [ ] No `specs/` delta was written for this change
- [ ] No `design.md` was written for this change
- [ ] Phase 1B+ items for Company / Paper / Patent / multi-turn / agentic-rag / agents-specs / copilot were not touched as part of this change

## Evidence

> Filled by the executing agent during T1 / T2 / T3. Not filled at proposal time.

### T1.2 — Audit doc frontmatter extension
- Decision: (taken | skipped)
- Rationale if skipped:
- Diff hash / commit ref:

### T3.1 — PRD ↔ refine-change actually-shipped reconciliation
For each task T1–T5 of `refine-professor-data-agent-prd/tasks.md`, cite the PRD section confirming the change is present (or absent):

| Task | Description (short) | Present in PRD? | PRD section / line range | Notes |
|---|---|---|---|---|
| T1 | 4.1 字段定义表 source → 采集策略 列重写 | (yes / no / partial) | | |
| T2 | 5.1 Phase 1 改 agent 驱动；Phase 4 本地 MiroThinker | (yes / no / partial) | | |
| T3 | 5.2 Phase 1 BatchScheduler + ProfessorOrchestrator | (yes / no / partial) | | |
| T4 | 新增技术架构章节 (MCP 工具集 / Hydra / 并发) | (yes / no / partial) | | |
| T5 | 5.4 Phase 4 本地 MiroThinker 部署 | (yes / no / partial) | | |

Summary judgement (one sentence):

### T3.2 — Disposition decision
- Chosen path: (archive | re-target | abandon)
- Rationale (one paragraph):

### T3.3 — Execution evidence
- Command run:
- Output (or `acceptance` block of resulting archived change):

### Final verification
- `openspec list --status active` excludes `refine-professor-data-agent-prd`: (verified | tool unavailable, see manual check below)
- `openspec/debt-register.md` Open count delta: −3 or −4 (depending on T3.6 path)
- `git status` clean except for files named in `source-links.md §Governance artifacts updated`

## Failure modes that block archive

If any of the following holds, this change does **not** archive and a follow-up issue is logged:

- T3.1 verification finds T1–T5 did *not* land in the PRD → the PRD is more out-of-sync than expected; the disposition decision needs reconsideration.
- The Audit doc was edited mid-flight by another session → resolve conflict before T1.1 commit; do not silently overwrite.
- A new Professor requirement is requested in the middle of execution → out of scope; spawn a new change.
