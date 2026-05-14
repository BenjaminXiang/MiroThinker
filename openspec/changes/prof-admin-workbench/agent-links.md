# Agent Links: prof-admin-workbench

## Execution workspace

- `.agents/runs/prof-admin-workbench/` — not yet created. It is created
  when child implementation starts (`tasks.md` T2.3); each child change
  gets its own run workspace under `.agents/runs/<child-change-id>/`.

## Design and review provenance

- 2026-05-14 brainstorming session (Claude) — produced the five locked
  decisions and the Epic decomposition recorded in `design.md`
  ("Locked decisions"), plus the Layout A frontend decision.
- 2026-05-14 design review round 1 — 5 findings; resolution recorded in
  `change-log.md`.
- 2026-05-14 design review round 2 — 4 findings; resolution recorded in
  `change-log.md`.

## Handoffs

- No Codex handoff yet. Implementation handoffs
  (`.agents/handoffs/<slug>`) are created per child change once
  scaffolded, each referencing its child `change-id`.
