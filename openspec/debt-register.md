# Spec / Change Debt Register

Per CLAUDE.md §14. Records OpenSpec-related debt that is known but not in scope right now. Each open item is resolved by a future OpenSpec change that touches the relevant capability or by an explicit archive/abandon decision.

## Open

| Debt ID | Area | Symptom | Source | Risk | Resolution Plan | Status |
|---|---|---|---|---|---|---|
| professor-prd-change-001 | refine-professor-data-agent-prd | Tasks T1–T5 marked `[x]` but the change is not archived; nothing in `openspec/changes/archive/` references it | `openspec/changes/refine-professor-data-agent-prd/tasks.md` | low | Single-purpose follow-up `resolve-refine-professor-data-agent-prd`: compare `docs/Professor-Data-Agent-PRD.md` to the 5 modifications in `proposal.md`. If PRD shipped, run `openspec archive refine-professor-data-agent-prd` (use `--skip-specs` if it stays a docs-only change). If not, reopen tasks or mark abandoned. | open |
| professor-prd-change-002 | refine-professor-data-agent-prd | `specs/prd-update/spec.md` does not use OpenSpec Requirement / Scenario format — describes "modify rules" rather than ADDED/MODIFIED/REMOVED behavior | `openspec/changes/refine-professor-data-agent-prd/specs/prd-update/spec.md` | low | If the change is archived as-is, this non-conformant spec ships as legacy and the deviation is acknowledged. If the change is reopened or extended, rewrite the spec in proper Requirement / Scenario form per CLAUDE.md §14.3. | open |
| copilot-openspec-artifacts-001 | `.github/` Copilot OpenSpec artifacts | `.github/prompts/opsx-*.prompt.md` and `.github/skills/openspec-*/SKILL.md` are tracked in git from a prior OpenSpec setup; Phase 0 selected `--tools claude` only and does not actively use them | `.github/prompts/`, `.github/skills/` | none | Single-purpose change `cleanup-copilot-openspec-artifacts`: decide keep / remove / regenerate with the current OpenSpec version. Not bundled into Phase 0; tooling-removal decisions stay isolated. | open |

## Grandfathered

| Debt ID | Area | Reason for grandfathering |
|---|---|---|
| professor-prd-change-003 | refine-professor-data-agent-prd | Missing `acceptance.md`, `change-log.md`, `source-links.md`, `agent-links.md`. These are Phase-0+ artifacts (CLAUDE.md §14) and are not retroactively required for pre-Phase-0 changes. New OpenSpec changes must include them. |

## Resolved

(none)

## Notes

- Debt IDs use a `<change-or-capability>-<seq>` form.
- `grandfathered` is distinct from `open` and `wontfix`. It means the debt is acknowledged but excluded from action by an explicit boundary (typically Phase 0).
