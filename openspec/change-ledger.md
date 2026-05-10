# Change Ledger

Per CLAUDE.md §14 / AGENTS.md §15. Every OpenSpec change is registered here. Status workflow: `proposed` → `in-implementation` → `in-verification` → `tasks-complete-not-archived` → `archived`. Weight follows CLAUDE.md §8 (Tiny / Standard / Epic).

## Active and pending

| Change ID | Type | Capability | Source | Status | Weight | Risk | Agent Run | PR | Archive |
|---|---|---|---|---|---|---|---|---|---|
| prof-seed-admin-console | feat (new admin UI + schema + endpoint + pipeline trigger) | professor-seed-management | Audit §2 + §9.4 + Review §3.1 Theme 2 | proposed | Standard | low-medium | — (no run yet) | n/a | no |

## Notes

- `refine-professor-data-agent-prd` was archived 2026-05-10 as `2026-05-10-refine-professor-data-agent-prd`. T3.1 verification (recorded in `resolve-professor-canonical-baseline` `acceptance.md`) found T1–T5 marked `[x]` but never landed in PRD body; combined with the user's 2026-05-10 canonical pivot demoting the PRD to legacy, retroactive application of T1–T5 had no value. CLI emitted a non-blocking `## Why` / `## What Changes` warning corresponding to debt `professor-prd-change-002` (resolved-by-archive).
- `resolve-professor-canonical-baseline` was the first Phase 1B change (CLAUDE.md §14.6). Doc-only governance, no `specs/`, no `design.md`. Bundled and resolved four Professor-domain debt entries (`audit-doc-untracked-001`, `professor-canonical-pivot-001`, `professor-prd-change-001`, `professor-prd-change-002`). Archived 2026-05-10 as `2026-05-10-resolve-professor-canonical-baseline` after all four debts moved to Resolved in `debt-register.md`.
- Phase-0+ artifacts (`acceptance.md`, `change-log.md`, `source-links.md`, `agent-links.md`) were not present in `refine-professor-data-agent-prd` and are grandfathered — they are required only for new changes per CLAUDE.md §14.4.

## Archived

| Change ID | Archived as | Type | Capability | Status at archive | Weight | Risk | Archived on |
|---|---|---|---|---|---|---|---|
| refine-professor-data-agent-prd | `archive/2026-05-10-refine-professor-data-agent-prd/` | docs + architecture intent | professor data collection | premise-invalidated; T1–T5 marked but never shipped | Standard | low | 2026-05-10 |
| resolve-professor-canonical-baseline | `archive/2026-05-10-resolve-professor-canonical-baseline/` | doc-governance (no behavior, no code) | professor data collection — canonical baseline | tasks-complete (T1–T4 all executed; debts 4/4 resolved) | Lite+ | low | 2026-05-10 |
