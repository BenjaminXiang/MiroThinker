# Agent Links — unify-data-quality-gating

> Per CLAUDE.md §14.4. Roles, skills, and verification boundary for this change.

## Roles (CLAUDE.md §1)
- **Claude (designer/reviewer):** the cross-domain audit that motivated this
  change, this OpenSpec change (proposal/specs/design/tasks/acceptance/
  source-links/agent-links/change-log), and post-implementation review against
  the contract.
- **Codex (implementer):** owns the `tasks.md` slices — `gating_contract.py`,
  `company/quality_promotion.py`, the paper writer rewire, the
  `promotion_rules.py` refactor, tests, and the real dry-run / bounded apply /
  Milvus re-backfill evidence. Reports back per slice.

## Sibling change
- `harden-entity-normalization` — the other half of the cross-domain structural
  fix (normalization, not gating). Independent code path, independent
  verification, may land in either order. Shared rationale: the 2026-06-26
  cross-domain audit. Reference each other in `change-ledger.md`.

## Skills used
- `openspec-propose` — generated this change's artifacts.
- `superpowers:test-driven-development` — drives the deterministic unit/contract
  slices (RED → GREEN) per the verification contract.
- `pattern-repair` — motivated the cross-domain structural framing (quality-gate
  fragmentation is a recurring systemic gap, not a single-domain patch).

## Verification boundary (CLAUDE.md §14.7)
- `.agents/runs/unify-data-quality-gating/verification-contract.md` (task 1.1)
  classifies the change as **behavior-affecting but deterministic at the
  new-code surface** (gates are pure functions of row fields; no LLM, no
  network). RED = unit + contract + parity tests + read-only dry-run; GREEN =
  tests pass + dry-run "0 ready degraded" + bounded apply.
- Superpowers TDD may drive the deterministic slices; it MUST NOT independently
  alter the `ready` criteria, the enum values, or the threshold values.
- Real-data apply + Milvus re-backfill (tasks 6.3–6.4) is the acceptance
  evidence; a full-population retrieval assertion is NOT required (spot-check
  is sufficient).

## Dispatch
- One active writer (Codex) per slice (CLAUDE.md §11). Slice order follows
  `tasks.md` groups 1 → 7.
- Claude reviews each slice against `acceptance.md` before the next; the dry-run
  "0 ready degraded" hard gate (task 6.2) is a stop-and-report checkpoint.
