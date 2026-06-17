# Agent Links — wire-paper-identity-gate-rejection

> Per CLAUDE.md §14.4. Roles, skills, and verification boundary for this change.

## Roles (CLAUDE.md §1)
- **Claude (designer/reviewer):** root-cause investigation, portfolio plan, this OpenSpec change (proposal/specs/design/tasks/acceptance/source-links/agent-links), and post-implementation review against the contract.
- **Codex (implementer):** owns the `tasks.md` slices — `paper/identity_status_writer.py`, `scripts/run_paper_identity_scan.py`, tests, real dry-run/apply evidence. Reports back per slice.

## Skills used
- `pattern-repair` — drove the systemic root-cause investigation (E1) that motivated this change.
- `superpowers:writing-plans` — produced the portfolio plan this change derives from.
- `openspec-propose` — generated this change's artifacts.

## Verification boundary (CLAUDE.md §14.7)
- `.agents/runs/wire-paper-identity-gate-rejection/verification-contract.md` (task 1.1) classifies the change as **behavior-affecting but deterministic at the new-code surface** (the LLM gate is reused unchanged). RED = contract/unit tests for the rejection guard + scan dry-run/apply + reversibility. Superpowers TDD may drive the deterministic slices; it must not independently alter the gate threshold or semantics.
- Real-LLM E2E on the full unverified population is **not** the RED artifact; bounded-slice dry-run + apply evidence (tasks 6.1–6.3) is the acceptance evidence.

## Dispatch
- Single active writer (Codex) per slice (CLAUDE.md §11). Slice order follows `tasks.md` groups 1 → 7.
- Claude reviews each slice against `acceptance.md` before the next.
