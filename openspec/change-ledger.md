# Change Ledger

Per CLAUDE.md §14 / AGENTS.md §15. Every OpenSpec change is registered here. Status workflow: `proposed` → `in-implementation` → `in-verification` → `tasks-complete-not-archived` → `archived`. Weight follows CLAUDE.md §8 (Tiny / Standard / Epic).

## Active and pending

| Change ID | Type | Capability | Source | Status | Weight | Risk | Agent Run | PR | Archive |
|---|---|---|---|---|---|---|---|---|---|
| prof-seed-admin-console | feat (new admin UI + schema + endpoint + pipeline trigger) | professor-seed-management | Audit §2 + §9.4 + Review §3.1 Theme 2 | Phase B complete; tasks-complete-not-archived | Standard | low-medium | .agents/runs/prof-seed-admin-console/verification.md | n/a | no |
| prof-paper-patent-from-page-flow | feat (codify) + refactor (deprecate S2 discovery) + new patent extraction | paper-patent-from-prof-page | Paper Review §3.1 P4/P9/P10/P11/P15/P16 + Professor Review Theme 7.1 | in-verification; carry-over documented | Standard | medium | openspec/changes/prof-paper-patent-from-page-flow/acceptance.md | n/a | no |
| paper-pipeline-cleanup | refactor (retire legacy paper discovery path) | paper-pipeline-cleanup | `prof-paper-patent-from-page-flow` T1 carry-over | proposed | Standard | medium | — | n/a | no |
| prof-summary-fields | feat (professor paper/patent aggregate summaries) | professor-summary-fields | Professor Audit Step 15 + Review §3.1 | proposed | Standard | medium | — | n/a | no |
| prof-double-milvus-collection | feat (split professor identity/research vectors) | professor-retrieval-index-split | Professor Review §8.4 | proposed | Standard | medium-high | — | n/a | no |
| prof-lifecycle-state | feat (professor lifecycle separate from quality) | professor-lifecycle-state | Professor Audit Step 23a/23b + Review §9.2 | proposed | Standard | medium | — | n/a | no |
| patent-page-only-canonical | feat (decide page-only patent canonical strategy) | patent-page-only-canonical | `prof-paper-patent-from-page-flow` T4 / V004 carry-over | proposed | Standard | medium | — | n/a | no |
| paper-summary-text-contract-fix | bugfix (admin API contract drift) | paper-canonical-api-projection | Paper Review §3.1 P3 + audit drift item | archived 2026-05-10 | Lite | low | — | n/a | yes |
| prof-admin-workbench | epic (parent): quality-status rework + admin audit workbench + fact extraction | professor-admin-workbench (3 child capabilities) | Brainstorming 2026-05-14 + live DB inspection (miroflow_real) | proposed | Epic | medium-high | — | n/a | no |
| prof-quality-status-rework | feat/refactor (quality engine + canonical write + re-eval) | professor-quality-status | `prof-admin-workbench` child 1 | proposed | Standard | medium | — | n/a | no |
| prof-fact-extraction-expansion | feat (structured facts + profile summary backfill) | professor-fact-extraction | `prof-admin-workbench` child 2 | proposed | Standard | medium | — | n/a | no |
| prof-admin-workbench-ui | feat (admin API + workbench UI + action log) | professor-admin-workbench-ui | `prof-admin-workbench` child 3 | proposed | Standard | medium-high | — | n/a | no |

## Notes

- `refine-professor-data-agent-prd` was archived 2026-05-10 as `2026-05-10-refine-professor-data-agent-prd`. T3.1 verification (recorded in `resolve-professor-canonical-baseline` `acceptance.md`) found T1–T5 marked `[x]` but never landed in PRD body; combined with the user's 2026-05-10 canonical pivot demoting the PRD to legacy, retroactive application of T1–T5 had no value. CLI emitted a non-blocking `## Why` / `## What Changes` warning corresponding to debt `professor-prd-change-002` (resolved-by-archive).
- `resolve-professor-canonical-baseline` was the first Phase 1B change (CLAUDE.md §14.6). Doc-only governance, no `specs/`, no `design.md`. Bundled and resolved four Professor-domain debt entries (`audit-doc-untracked-001`, `professor-canonical-pivot-001`, `professor-prd-change-001`, `professor-prd-change-002`). Archived 2026-05-10 as `2026-05-10-resolve-professor-canonical-baseline` after all four debts moved to Resolved in `debt-register.md`.
- Phase-0+ artifacts (`acceptance.md`, `change-log.md`, `source-links.md`, `agent-links.md`) were not present in `refine-professor-data-agent-prd` and are grandfathered — they are required only for new changes per CLAUDE.md §14.4.
- Follow-up rows registered on 2026-05-13 are ledger placeholders only.
  They make owner/status/risk visible before full OpenSpec directories are
  drafted. `prof-lifecycle-state` must model lifecycle separately from
  `quality_status`: quality answers whether data is trustworthy; lifecycle
  answers whether the person is still active at that school.
- `prof-admin-workbench` registered 2026-05-14. Epic parent; carries
  Epic-level `proposal.md` + `design.md` only. Three child changes
  (`prof-quality-status-rework`, `prof-fact-extraction-expansion`,
  `prof-admin-workbench-ui`), sequenced quality-first and then
  data-first. Root cause: `canonical_writer` never writes
  `quality_status`, so all 495 `miroflow_real` professors sit at the
  `needs_review` default. The child changes are scaffolded; Child 1
  implementation remains gated on child-spec review and a clean
  implementation checkpoint.

## Archived

| Change ID | Archived as | Type | Capability | Status at archive | Weight | Risk | Archived on |
|---|---|---|---|---|---|---|---|
| refine-professor-data-agent-prd | `archive/2026-05-10-refine-professor-data-agent-prd/` | docs + architecture intent | professor data collection | premise-invalidated; T1–T5 marked but never shipped | Standard | low | 2026-05-10 |
| resolve-professor-canonical-baseline | `archive/2026-05-10-resolve-professor-canonical-baseline/` | doc-governance (no behavior, no code) | professor data collection — canonical baseline | tasks-complete (T1–T4 all executed; debts 4/4 resolved) | Lite+ | low | 2026-05-10 |
| paper-summary-text-contract-fix | `archive/2026-05-10-paper-summary-text-contract-fix/` | bugfix (admin API contract drift) | paper-canonical-api-projection | tasks-complete (1-line code + 2 test updates + spec delta); resolves debt paper-summary-text-contract-drift-001 | Lite | low | 2026-05-10 |
