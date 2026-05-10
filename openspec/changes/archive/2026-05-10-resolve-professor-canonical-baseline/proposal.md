---
change_id: resolve-professor-canonical-baseline
type: doc-governance
weight: OpenSpec Lite+
behavior_change: false
code_change: false
adds_requirements: false
created: 2026-05-10
---

# Proposal: resolve-professor-canonical-baseline

## Summary

Bundle three Professor-domain documentation-debt items into a single coordinated, doc-only governance change so the canonical-baseline pivot declared by the user on 2026-05-10 stops leaking into stale pointers, untracked files, and an unarchived OpenSpec change.

This change introduces no new product behavior, no code edits, and no new Professor data requirements. It only realigns documentation pointers and disposes of a stale OpenSpec change whose premise has been invalidated.

## Background

On 2026-05-10 the user declared `docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md` (the "Audit doc") as the canonical requirement source for the Professor data-agent domain, superseding `docs/Professor-Data-Agent-PRD.md` (the "PRD") for behavioral interpretation. The Audit doc itself states (§0): "若与 `Professor-Data-Agent-PRD.md` 冲突，**临时**以本文档为准；下一步动作是把本文档 §1–§7 沉淀回 PRD 后撤掉本文档" — i.e. the Audit explicitly anticipates eventual reabsorption back into the PRD, but until then it is canonical.

The Phase 1A inventory (`docs/data-agent-domain-index.md`) recorded this declaration and short-circuited the originally anticipated `resolve-professor-canonical-baseline` change (the question of *which doc is canonical* is now answered by user fiat). However, the canonical pivot leaves three concrete governance gaps:

1. The canonical doc is not version-controlled (`audit-doc-untracked-001`).
2. The PRD has no legacy marker; `CLAUDE.md §3` and `docs/index.md` still treat it as canonical without annotation (`professor-canonical-pivot-001`).
3. `openspec/changes/refine-professor-data-agent-prd/` has tasks T1–T5 marked complete but is not archived; its target (the PRD) is no longer the canonical doc, so its premise is partly invalidated (`professor-prd-change-001`). Its `specs/prd-update/spec.md` also does not follow OpenSpec Requirement / Scenario form (`professor-prd-change-002`).

This change resolves all four debt entries in one coordinated pass.

## In-scope debt items

| Debt ID | Origin | Resolution path |
|---|---|---|
| `audit-doc-untracked-001` | `openspec/debt-register.md` | Stage and commit Audit at current path; optional frontmatter extension |
| `professor-canonical-pivot-001` | `openspec/debt-register.md` | Add legacy frontmatter to PRD; update `docs/index.md`; update `CLAUDE.md §3` |
| `professor-prd-change-001` | `openspec/debt-register.md` | Decide and execute disposition of the stale change; recommended: archive as historical |
| `professor-prd-change-002` | `openspec/debt-register.md` | Transitively resolved by T3 outcome (legacy-shipped or removed; no rewrite required) |

## Recommendations

The change recommends but does not mandate the following decisions. `tasks.md` lists each as an explicit decision step; `acceptance.md` accepts any defensible outcome.

1. **Audit doc disposition** — keep at current path (`docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md`). Stage and commit with no rename. The path is already self-documenting via its date suffix; relocating would invalidate every existing reference (Phase 1A inventory, debt-register, CLAUDE.md §3 pending update).
2. **PRD legacy marking** — add YAML frontmatter declaring legacy status with `canonical: docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md`. Do not rewrite or delete PRD body content; readers may still consult it as historical context.
3. **Stale change disposition** — archive as historical via `openspec archive --skip-specs` (or its current equivalent). Rationale: T1–T5 are checked complete against the now-superseded PRD; reopening to retarget at the Audit would force a rewrite while adding no behavioral value. Archiving preserves provenance.

## Out of scope

- Any change to product behavior, RAG pipeline, agent runtime, storage, or admin console.
- Any new Professor data requirement. The Audit content is taken as-is; whether it should later be merged back into the PRD (the Audit's own §0 next step) is deferred to a future change.
- Phase 1B+ work for Company / Paper / Patent debt items, multi-turn design realignment, Agentic-RAG PRD ↔ Operating-Guide relationship, or `.agents/specs/` per-file triage.
- Rewriting `openspec/changes/refine-professor-data-agent-prd/specs/prd-update/spec.md` into OpenSpec Requirement / Scenario form (`professor-prd-change-002`). Resolved transitively by T3.

## Why doc-only governance, not behavior change

Per `CLAUDE.md §14.2`, doc-only changes that do not affect behavior are not required to write `specs/` deltas. This change moves doc authority pointers without changing what the system does. It is registered in `openspec/change-ledger.md` for traceability and to coordinate the four debt entries.

Per `CLAUDE.md §14.6`, this is Phase 1B work. It is the first OpenSpec change after the Phase 0 scaffolding and the Phase 1A inventory.

## Risk

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Audit doc later merged back into PRD makes the legacy marker obsolete | medium | low | Frontmatter is a one-line edit; future merge change can flip it back |
| Archiving stale change without verifying T1–T5 actually landed | low | low | T3.1 mandates verification before archive; findings recorded in `acceptance.md` |
| Other agents still cite PRD as canonical because their context predates this change | low | low | `CLAUDE.md §3` update, on next session start, propagates the new pointer |
| Loss of provenance if Audit doc is deleted before tracking | low | medium | T1.1 stages immediately at current path; no rename, no edit |

## Weight rationale

Lite+ (proposal + tasks + source-links + acceptance, no `specs/`, no `design.md`). The change is doc-only and bundles four already-classified low-risk debt items; full Standard ceremony is unnecessary, but the multi-debt coordination justifies more than bare Lite (proposal + tasks).
