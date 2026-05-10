# Tasks: resolve-professor-canonical-baseline

All tasks are documentation / governance edits. None modify code under `apps/`, `libs/`, or `src/`. Tasks within a section may be batched. Sections 1, 2, and 3 are independent and may be done in any order; section 4 must come last.

## 1. Track the Audit doc — debt `audit-doc-untracked-001`

- [ ] T1.1: Stage `docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md` at its current path. No rename, no relocation, no body edits.
- [ ] T1.2: (Optional) Extend the Audit's existing YAML frontmatter with a `governance:` block referencing this change ID and reaffirming its canonical-temporary status:
  ```yaml
  governance:
    change_id: resolve-professor-canonical-baseline
    canonical_for: professor-data-agent-domain
    canonical_status: temporary
    superseded_target: docs/Professor-Data-Agent-PRD.md
    next_step: merge §1–§7 back into PRD (deferred to future change)
  ```
  If T1.2 is skipped, record the rationale in `acceptance.md`.
- [ ] T1.3: Commit T1.1 (and T1.2 if taken) in a single commit message that names this change ID.
- [ ] T1.4: Mark `audit-doc-untracked-001` as Resolved in `openspec/debt-register.md` with a pointer to this change.

## 2. Mark the PRD as legacy — debt `professor-canonical-pivot-001`

- [ ] T2.1: Add (or extend) YAML frontmatter at the top of `docs/Professor-Data-Agent-PRD.md`:
  ```yaml
  ---
  status: legacy
  superseded_by: docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md
  superseded_on: 2026-05-10
  governance:
    change_id: resolve-professor-canonical-baseline
    note: |
      This PRD is retained as historical reference. For canonical Professor-domain
      requirements, see the Audit doc above. The Audit's §0 anticipates eventual
      reabsorption back into a PRD; until that change ships, this file is legacy.
  ---
  ```
  Do not rewrite PRD body content. Do not delete sections.
- [ ] T2.2: Update `docs/index.md` Professor row: PRD status → 🟡 legacy with arrow → Audit; Audit status → ✅ canonical (or whatever symbol the index conventions use for canonical). If `docs/index.md` does not yet list the Audit, add a row.
- [ ] T2.3: Update `CLAUDE.md §3` "Source-of-truth docs" Professor entry. Replace the bare PRD line with one that names the Audit as canonical and the PRD as legacy reference. No behavior-text change elsewhere in `CLAUDE.md`.
- [ ] T2.4: Mark `professor-canonical-pivot-001` as Resolved in `openspec/debt-register.md`.

## 3. Dispose of the stale OpenSpec change — debts `professor-prd-change-001` and `professor-prd-change-002`

- [ ] T3.1: **Verification step.** Read the current `docs/Professor-Data-Agent-PRD.md` and confirm whether tasks T1–T5 of `openspec/changes/refine-professor-data-agent-prd/tasks.md` actually landed against the PRD (i.e. whether the agent-driven Phase 1, the 字段采集策略 column, the BatchScheduler + ProfessorOrchestrator architecture section, and the Phase 4 本地 MiroThinker change are present in the current PRD body). Record findings in this change's `acceptance.md` "Evidence" section, citing PRD section / line numbers.
- [ ] T3.2: **Decision step.** Choose disposition:
  - (a) **Archive as historical** (recommended). Rationale: T1–T5 already complete against the now-legacy PRD; preserves provenance.
  - (b) Re-target to Audit. Cost: rewrite proposal/tasks/specs to point at Audit; reopen tasks; high churn for unclear behavioral value.
  - (c) Abandon (mark abandoned without archive). Cost: leaves a non-archived, non-active row in the ledger; ambiguous.
  Record the chosen path in `acceptance.md`.
- [ ] T3.3: **Execution step.** Carry out the chosen disposition.
  - For (a): run `openspec archive --skip-specs refine-professor-data-agent-prd` (or the current equivalent of an OpenSpec archive command); the `--skip-specs` flag is appropriate because the change targets PRD doc text, not behavioral specs in `openspec/specs/`.
  - For (b): rewrite the change artifacts; reopen tasks; this becomes a new line of work outside this change's scope and should split into its own change.
  - For (c): add an `archived: false; abandoned: true` marker in the change's frontmatter and to the ledger row.
- [ ] T3.4: Update `openspec/change-ledger.md` to reflect T3.3:
  - For (a): move `refine-professor-data-agent-prd` row from Active to Archived; archive note: "premise invalidated by canonical pivot 2026-05-10; tasks already complete against now-legacy PRD".
  - For (b)/(c): update Status column accordingly.
- [ ] T3.5: Mark `professor-prd-change-001` as Resolved in `openspec/debt-register.md`.
- [ ] T3.6: Resolve `professor-prd-change-002` transitively:
  - For (a): record as resolved-by-archive (the non-conformant spec ships as legacy; `CLAUDE.md §14.4` allows pre-Phase-0 deviations).
  - For (b): defer to the new change that re-targets the spec.
  - For (c): record as wontfix (change is abandoned).

## 4. Close out

- [ ] T4.1: Re-scan `openspec/debt-register.md`. Confirm 3 or 4 entries (depending on whether 002 was deferred to a new change) moved from Open to Resolved with cross-references back to this change.
- [ ] T4.2: Update `docs/data-agent-domain-index.md §Phase 1B / 1C scope`: strike through or remove the three bullets (`audit-doc-untracked-001`, `professor-canonical-pivot-001`, `professor-prd-change-001`, `professor-prd-change-002`) and append a one-line note pointing at this change as their resolution.
- [ ] T4.3: When all preceding tasks are complete, archive this change itself: move `openspec/change-ledger.md` row from Active to Archived; ensure `acceptance.md` is fully filled (no `(to be filled)` placeholders remaining).

## Tasks not in this change

- Merging Audit §1–§7 back into the PRD (deferred; the Audit's own §0 names this as a future step).
- `multi-turn-design-partial-001`, `agentic-rag-prd-vs-guide-001`, `paper-companion-design-relationship-001`, `agents-specs-frozen-but-uncategorized-001`, `copilot-openspec-artifacts-001` — all independent, all Phase 1B+, all deferred to their own changes.
- Any code-level changes to Professor pipeline, Milvus collections, vectorizer, or admin console.
- Any update to Professor blockers (BL-Professor-001 / 002 / 003); those are acceptance gaps belonging to the Audit's own §8 and the PRD's §8, not document debt.
