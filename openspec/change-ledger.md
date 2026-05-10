# Change Ledger

Per CLAUDE.md §14 / AGENTS.md §15. Every OpenSpec change is registered here. Status workflow: `proposed` → `in-implementation` → `in-verification` → `tasks-complete-not-archived` → `archived`. Weight follows CLAUDE.md §8 (Tiny / Standard / Epic).

## Active and pending

| Change ID | Type | Capability | Source | Status | Weight | Risk | Agent Run | PR | Archive |
|---|---|---|---|---|---|---|---|---|---|
| refine-professor-data-agent-prd | docs + architecture intent | professor data collection | pre-Phase-0 (Mar 18, 2026) | tasks-complete-not-archived | Standard | low | — (predates `.agents/runs/`) | unknown | no |

## Notes

- `refine-professor-data-agent-prd` predates Phase 0 (CLAUDE.md §14). Tasks T1–T5 are checked complete; the change has not been archived via `openspec archive`. See `debt-register.md` entries `professor-prd-change-001` and `professor-prd-change-002`.
- The change targets `docs/Professor-Data-Agent-PRD.md` and anticipates BatchScheduler + ProfessorOrchestrator agent architecture. Per CLAUDE.md §14.2 it is a borderline behavior-affecting change (PRD update with downstream architectural intent); registered as Standard for traceability.
- Phase-0+ artifacts (`acceptance.md`, `change-log.md`, `source-links.md`, `agent-links.md`) are not present and are grandfathered — they are required only for new changes per CLAUDE.md §14.4.

## Archived

(none)
