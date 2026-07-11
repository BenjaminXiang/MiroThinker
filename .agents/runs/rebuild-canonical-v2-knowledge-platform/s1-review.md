# S1 Review: Database Target Safety

## Status

Accepted by the user on 2026-07-11T05:39:19Z after review of the Candidate implementation and
verification report. Acceptance is recorded by the user, not self-granted by the implementing
agent.

## Candidate under review

- Code worktree: `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s1`
- Branch: `canonical-v2-s1-safety`
- Parent commit: `c0f3db2`
- OpenSpec tasks: 1.3 and 1.4 complete; 1.5 pending
- Evidence: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`

## Reviewer checks

- [x] Confirm generic `DATABASE_URL` / `DATABASE_URL_TEST` cannot become Alembic targets.
- [x] Confirm config and dedicated environment conflicts fail before engine creation.
- [x] Confirm real/system/recovery-checkpoint identities and port `15432` fail before connection.
- [x] Confirm connected server database identity is checked before migrations.
- [x] Confirm the database-side comment marker binds target kind and name and fails closed when
      missing or mismatched.
- [x] Confirm identity-query transaction cleanup preserves Alembic commit semantics.
- [x] Confirm the non-Alembic seed-loader `DROP SCHEMA` fixture cannot use generic DSN fallback and
      verifies the same database marker before DDL.
- [x] Confirm real disposable upgrade/downgrade evidence is sufficient and source invariants match.
- [x] Confirm ordinary runtime connections and historical migrations are outside and unchanged.
- [x] Record decision: accept / revise / reject, with blocking findings if any.

## Implementer self-review notes (not independent acceptance)

- A first real validation exposed an implicit-transaction rollback defect in the candidate. The
  database stayed empty, the root cause was reproduced with a RED assertion, and the transaction
  boundary was fixed before the successful real cycle.
- The protection is centralized at the Alembic environment boundary, so all current Alembic callers
  fail closed even if individual legacy fixtures still contain generic fallback code. The sibling
  search found and fixed the one generic-fallback autocommit destructive test path that did not
  cross Alembic (`postgres_seed_loader`).
- Self-review found that a caller-only kind/name assertion was not independent proof. The candidate
  now requires a matching database-side marker; missing and wrong-kind markers have pure RED/GREEN
  coverage and a real lab fail-closed probe.
- Legacy fixtures and `run_phase1_e2e.sh` now require operators to supply the dedicated target
  contract; they cannot silently retain their old destructive behavior.

## Decision

Accept. User acceptance received at 2026-07-11T05:39:19Z. No blocking findings remain for S1.
