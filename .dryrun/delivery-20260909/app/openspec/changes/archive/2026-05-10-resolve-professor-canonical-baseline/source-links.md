# Source Links: resolve-professor-canonical-baseline

This file enumerates the artifacts read by, modified by, or coordinated through this change, and the relationships between them. Per `CLAUDE.md §14.4`, source-links is required for OpenSpec Lite+ changes.

## Authority graph

```
                            user declaration 2026-05-10
                                       │
                                       ▼
docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md   ← canonical (temporary, untracked)
                                       │
                                       │  supersedes (for behavior interpretation)
                                       ▼
docs/Professor-Data-Agent-PRD.md                              ← legacy reference (post-T2)
                                       ▲
                                       │  targeted by tasks T1–T5 [x]
                                       │
openspec/changes/refine-professor-data-agent-prd/             ← stale; disposition decided in T3
                                       │
                                       │  registered in
                                       ▼
openspec/change-ledger.md                                     ← updated by T3.4 and T4.3
                                       │
                                       │  tracks debts referencing all of the above
                                       ▼
openspec/debt-register.md                                     ← 4 entries closed by this change

docs/data-agent-domain-index.md (Phase 1A, §Domain 4)         ← already records the pivot;
                                                                 §Phase 1B/1C list updated by T4.2
```

## Canonical artifacts (Professor domain, post-change)

- **`docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md`** — Canonical (temporary). 447 lines. Currently working-tree-only; T1.1 stages and commits it. Self-describes (§0): "若与 PRD 冲突，**临时**以本文档为准；下一步动作是把本文档 §1–§7 沉淀回 PRD 后撤掉本文档".
- **`docs/Data-Agent-Shared-Spec.md`** — Cross-domain shared baseline. Not modified by this change. Continues to outrank domain-local convenience per `CLAUDE.md §3 / §7`.

## Legacy / pre-pivot artifacts

- **`docs/Professor-Data-Agent-PRD.md`** — 368 lines. Was canonical pre-2026-05-10; becomes legacy reference after T2. Contains the agent-driven Phase 1 architecture introduced by `refine-professor-data-agent-prd` T1–T5. Body content is preserved by this change; only frontmatter is added.

## Stale OpenSpec change being resolved

- **`openspec/changes/refine-professor-data-agent-prd/proposal.md`** — Original premise: refine PRD §4.1 / §5.1 / §5.2 / §5.4 to introduce BatchScheduler + ProfessorOrchestrator agent architecture and local MiroThinker Phase 4. Premise partly invalidated post-pivot (target = PRD = no longer canonical).
- **`openspec/changes/refine-professor-data-agent-prd/tasks.md`** — T1–T5 marked `[x]`.
- **`openspec/changes/refine-professor-data-agent-prd/design.md`** — Architecture rationale; preserved on archive.
- **`openspec/changes/refine-professor-data-agent-prd/specs/prd-update/spec.md`** — Non-conformant to OpenSpec Requirement / Scenario form. Tracked as debt `professor-prd-change-002`. Resolved transitively by T3.

## Governance artifacts updated by this change

- **`openspec/change-ledger.md`** — T3.4 moves the stale change to Archived; T4.3 moves this change's row Active → Archived after acceptance is filled.
- **`openspec/debt-register.md`** — T1.4, T2.4, T3.5, T3.6 move `audit-doc-untracked-001`, `professor-canonical-pivot-001`, `professor-prd-change-001`, `professor-prd-change-002` from Open to Resolved with back-references to this change ID.
- **`docs/data-agent-domain-index.md`** — T4.2 updates §Phase 1B / 1C scope: removes the three Professor pivot bullets; appends a resolution-note line.
- **`docs/index.md`** — T2.2 updates the Professor row: PRD → 🟡 legacy; Audit → ✅ canonical.
- **`CLAUDE.md`** — T2.3 edits §3 Source-of-truth docs Professor entry only. No other section touched.

## Originating documents (read but not modified by this change)

- **`docs/data-agent-domain-index.md §Domain 4: Professor`** — Phase 1A inventory recording the user declaration of 2026-05-10. Names this change as the bundled resolution path.
- **`openspec/debt-register.md`** — Open table entries `audit-doc-untracked-001`, `professor-canonical-pivot-001`, `professor-prd-change-001`, `professor-prd-change-002`. All four resolved by this change.
- **`CLAUDE.md §14.5`** — `.agents/specs/` frozen as legacy. Not directly relevant but informs why the four debt items are tracked in `debt-register.md` rather than via `.agents/specs/` updates.
- **`CLAUDE.md §14.6`** — Phase 1B+ scope. Authorizes this change as Phase 1B work.

## Relationships explicitly excluded from this change

- **Audit ↔ PRD merge** — The Audit §0 names "把本文档 §1–§7 沉淀回 PRD 后撤掉本文档" as the next step. This change does **not** perform that merge; it only marks the PRD as legacy and tracks the Audit. The merge would require its own OpenSpec change (likely Standard, since it touches Professor requirements as documented).
- **Audit ↔ Plans** — Plans under `docs/plans/2026-04-17-*-professor-stem-*` etc. are operational, not requirement sources. Their status is unchanged by this change.
- **Audit ↔ Solutions** — `docs/solutions/data-quality/...` and `docs/solutions/workflow-issues/...` Professor entries are retrospectives, not authority. Unchanged.
- **Audit ↔ `.agents/specs/`** — Multiple frozen specs (e.g. `2026-04-30-w9-1-prof-academic-metrics.md`) reference Professor capabilities. Per `CLAUDE.md §14.5` they are frozen; per debt `agents-specs-frozen-but-uncategorized-001` per-file triage is deferred. This change does not touch them.

## Cross-domain dependencies

None. This change is entirely Professor-domain, doc-only, and does not coordinate with Company / Paper / Patent reconciliation work in flight.
