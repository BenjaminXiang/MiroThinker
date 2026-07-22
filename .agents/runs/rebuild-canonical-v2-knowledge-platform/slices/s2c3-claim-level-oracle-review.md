# Slice Contract: s2c3-claim-level-oracle-review

## Status

In Progress. `s2c2-claim-level-corpus-migration`, Task 2.7, S2C3A, S2C3B, and S2C3C1 are Accepted at
47/80. S2C3C2 is Ready but requires authorized external human input from `2026-07-14T18:48:51Z`;
there is no active agent writer. Task 2.8, aggregate S2C acceptance, and the S8/S9 oracle gate remain
open.

## Minimal decomposition

- S2C3A: Accepted strict run-local oracle/judge/human-gate RED.
- S2C3B: Accepted deterministic evaluator and recorded-fake judge GREEN.
- S2C3C1: Accepted deterministic, unapproved external-review packet.
- S2C3C2: Ready, awaiting authorized external human review and calibration; the agent cannot
  substitute its own review for the required human decision.
- S2C3C3: pending reviewed-corpus application and aggregate S2C/Task 2.8 acceptance.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `2.8`
- Depends on: Accepted S2C2 corpus version

## Goal

Validate hard per-case outcomes, snapshot/version integrity, evidence-bounded LLM judging, and human
review/calibration, then independently accept the exact S2C corpus version used by S8/S9.

## Non-goals

- No runtime quality claim, query/answer implementation, provider-selected truth, threshold lowering,
  database/index write, or acceptance of `pending_user_review` cases by automation.

## Allowed scope

- Read-only validation/review evidence and deterministic fixtures under the S2C run directory.
- Recorded-fake LLM judge tests bound to exact contract/snapshot IDs; named real judging only if
  explicitly authorized and human-calibrated.
- Human review status updates, verification, acceptance, task/change-log/portfolio evidence.

## Forbidden changes

- External truth from LLM memory/reference prose, averaging a hard case away, silent snapshot refresh,
  auto-accepting pending cases, runtime/product writes, or historical S2 mutation.

## Expected unchanged behavior

- S8/S9 remain blocked from acceptance-oracle execution until this slice is Accepted.
- Aggregate quality metrics remain secondary to every applicable hard case outcome.

## Required checks

- Schema/corpus/snapshot deterministic rebuild and tamper matrix.
- Per-case required/forbidden identity/claim, false-exhaustiveness, protected-slot, evidence support,
  and session-transition outcomes.
- Evidence-bounded recorded LLM judge success/invalid/memory-leak/failure degradation tests.
- Human-review completeness and judge-human agreement by relevant family; unresolved cases are
  excluded from accepted oracle use rather than hidden.
- Strict OpenSpec, diff/source/scope/secret/cache checks and independent aggregate review with zero
  open Critical/Important findings.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- S2C acceptance record with schema/corpus/snapshot hashes, case/review counts, hard outcomes, judge
  calibration, reviewer identity/state, and exclusions.
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,acceptance.md,change-log.md}`
- `.agents/portfolio.md` and `agent-links.md`.

## Stop conditions

- Any case used for S8/S9 remains `pending_user_review`, lacks required snapshot/as-of, or depends on
  unbounded mutable evidence.
- Human calibration is absent for an LLM-judged family, a hard outcome fails, or a Critical/Important
  finding remains open.
- Completion would require treating agent/model review as the required human review.

## Done means

- Task 2.8 and S2C are Accepted for one exact schema/corpus/snapshot version with every included case
  human-reviewed and every hard requirement independently passing.
- S8/S9 may consume only that accepted version; historical S2 remains intact.

## Rollback note

Revoke the S2C acceptance record and return affected cases to explicit pending/excluded state. No
runtime/database/index rollback is required.
