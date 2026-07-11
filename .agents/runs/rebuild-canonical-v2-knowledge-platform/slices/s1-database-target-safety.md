# Slice Contract: S1 Database Target Safety

## Status

Accepted. The user approved the Candidate evidence and accepted S1 on 2026-07-11T05:39:19Z.
Tasks 1.1–1.5 are complete. This acceptance closes only the database-target-safety slice; no later
slice has started.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Tasks: 1.1–1.5 only

## Goal

Make every destructive Alembic, migration-test, and database-reset path require an explicit target,
prove that the target is disposable/isolated, and fail before writes when target identity is missing,
ambiguous, or conflicts with a generic environment database URL.

## User / operator effect

Running tests or rebuild tooling cannot silently migrate or erase a real or recovery-evidence
database because of inherited environment configuration.

## Non-goals

- No Canonical V2 schema or domain implementation.
- No source inventory, replay, recollection, salvage import, Milvus client open, or index build.
- No broad test suite before the S1 safety mechanism is GREEN.
- No production-like cutover, repair, or data restoration.

## Allowed scope

- `apps/miroflow-agent/alembic/env.py`
- New or existing narrowly relevant database-target helper module under
  `apps/miroflow-agent/src/data_agents/storage/` or the nearest existing storage/config seam
- Narrow migration/database-target tests under `apps/miroflow-agent/tests/storage/`
- Minimal test configuration/fixtures only when required for explicit disposable target injection
- S1 OpenSpec task/evidence files

## Forbidden changes

- Original `pgtest`, port `15432`, source volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`
- Original `apps/miroflow-agent/milvus.db` client access or mutation
- Recovery checkpoint databases `miroflow_recovery_candidate` and
  `miroflow_recovery_candidate_verify`
- Domain schemas, canonical writers, retrieval/chat behavior, admin behavior, or benchmark rules
- Dependency upgrades, broad formatting, unrelated cleanup, commits, or pushes

## Expected unchanged behavior

- Alembic upgrade/downgrade behavior on an explicitly approved disposable database.
- Non-destructive application runtime may continue to use its documented runtime DSN path; the S1
  change only forbids ambiguous fallback for destructive/test/recovery operations.
- Existing migrations remain historical artifacts; S1 does not rewrite them.

## Required RED cases

1. Explicit test DSN plus conflicting generic real DSN selects only the explicit disposable target.
2. Missing explicit destructive target fails before Alembic connects or runs migrations.
3. Explicit target with a non-disposable database identity fails before writes.
4. Explicit approved disposable target permits upgrade/downgrade and changes only that target.

Each RED must fail for the expected missing-safety behavior before production implementation.

## Required checks

- Narrow pure/contract tests for target selection and identity validation.
- Narrow real-Postgres Alembic upgrade/downgrade against a newly created disposable database in the
  network-none recovery lab or another explicitly approved isolated instance.
- Pre/post database-name, Alembic revision, and core-table/count checks on the disposable target.
- Pre/post `pgtest` paused state and original Milvus SHA-256 check.
- `openspec validate rebuild-canonical-v2-knowledge-platform --strict`.
- `git diff --check` and focused lint/type checks for touched Python files.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- OpenSpec tasks 1.3–1.5 only after their evidence exists
- S1 review note recording accept/revise/reject and remaining risk

## Stop conditions

- Any target resolves to port `15432`, database `miroflow_real`, a recovery checkpoint database, or
  the original source volume.
- Any missing/ambiguous target reaches Alembic connection or migration execution.
- A RED test passes before implementation or fails for an unrelated setup reason.
- Narrow GREEN causes unrelated test failures or requires schema/domain behavior not in this slice.
- Original pause state or Milvus hash changes.

## Done means

- Tasks 1.1–1.4 have current-session evidence.
- All required RED cases were observed failing for the intended reason before implementation.
- Narrow pure and real disposable-Postgres GREEN checks pass.
- Original-source invariants remain unchanged.
- Independent review accepts S1 and task 1.5 is marked complete.
- S2 may then be made Ready; no later slice starts in this session without explicit scope update.
