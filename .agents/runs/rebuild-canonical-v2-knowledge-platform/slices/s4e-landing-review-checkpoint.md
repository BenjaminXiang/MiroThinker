# Slice Contract: S4E Landing Review and Checkpoint

## Status

Accepted — `2026-07-11T22:07:12Z`

- Authority: user-authorized objective-verification self-approval
- Acceptance record SHA-256:
  `20e11fbe2506a44913e58351ef27121065c0b63bfa12a85cdf9425db6578f58c`

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: 4.5 only
- Depends on: Accepted tasks 4.1-4.3 and reviewable Task 4.4 commit
  `cef42a1e075d30c5a0e179f34ab543b4878edabd`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4-landing-checkpoint-plan.md`

## Goal

Decide whether the complete S4 landing implementation is safe for canonical construction to depend
on, repair any acceptance-blocking defect, and preserve an independently restored, content-addressed
checkpoint of the exact landing-only candidate.

## Non-goals

- Implement S5 assertions, fusion, identity, or temporal decisions.
- Add canonical/domain/publish/index rows, call Web/LLM providers, recollect sources, or build/open a
  new Milvus index.
- Modify, resume, migrate, repair, or parse original/recovery sources.
- Promote, cut over, clean up, or otherwise treat the isolated candidate as production-like.

## Allowed scope

- Read-only review of commits/tasks 4.1-4.4, their source/tests, OpenSpec, and verification evidence.
- Task-scoped `s4e/` checkpoint code, tests, manifest, restore verification, and acceptance record.
- This plan/contract, a landing review note, OpenSpec task/acceptance/change log, and run
  verification contract/evidence.
- A custom-format dump under a new explicit child of
  `/md1/mirothinker-backups/`, followed by read-only freeze.
- One fresh `network=none`, no-port, `restart=no`, tmpfs-PGDATA PostgreSQL restore container and
  local Unix socket, both removed after verification.
- One exact idempotent replay through the accepted Task 4.4 public path before checkpoint capture.

## Forbidden changes

- Any candidate downgrade, row deletion/update/truncate, direct landing insert, or unreviewed
  migration.
- Any write to original `pgtest`, original/recovery PostgreSQL volumes/databases, original Milvus,
  Accepted S2B bytes, historical sources, or production-like targets.
- Persistent or anonymous Docker storage for the restore drill; published TCP ports or non-none
  networking; generic `DATABASE_URL` fallback.
- Binary dump, source payload, restored rows, credentials, or secrets committed to Git.
- Task 5.1 work in the same commit or before S4 reaches Accepted.

## Expected unchanged behavior

- S1, S2/S2B, S3, and Task 4.1-4.4 observable behavior and evidence remain valid.
- Candidate remains C2_0004 with the exact immutable landing matrix and no non-landing business
  rows, active release, or index projection.
- Existing application/chat/retrieval/legacy behavior remains untouched.

## Required checks

1. Independent review covers OpenSpec landing requirements, adapters, storage, matrix tooling,
   migrations, tests, and evidence; no Critical/Important finding remains.
1. Fresh idempotent six-family replay is byte-identical to committed summary
   `a88b44fa...e80b5`; its matrix remains `eaba2ecb...a923` and entry hash
   `5b77b4a4...c58293`; durable row hashes/counts do not change.
1. The checkpoint tool rejects changed gate/input hashes, wrong target identity/revision/system ID,
   source snapshot drift during dump, unexpected non-landing rows, invalid dump/archive, unsafe
   output roots, or ambiguous JSON.
1. The dump manifest records exact gate/git/input/database/tool identities, raw size/SHA-256,
   normalized schema fingerprint, every user-table count/hash, and landing aggregates.
1. Restore starts only in a distinct-system, explicitly marked disposable container with
   network-none/no ports/restart-no/tmpfs PGDATA/no persistent volume; `pg_restore` exits zero.
1. Restored revision, schema fingerprint, every user-table count/hash, lineage/status/error
   aggregate, and overall logical hash exactly match the source checkpoint; dump hash remains
   unchanged; restore container/socket are absent and Docker volume set is unchanged afterward.
1. Focused Task 4.5 tests, complete landing/Canonical V2 tests, real disposable migration/landing
   checks, S1, S2/S2B, Ruff, Pyright, strict OpenSpec, JSON parsing, diff checks, and final
   source/candidate invariants pass on fresh evidence.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4-landing-review.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s4d-bounded-landing-matrix.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4e/checkpoint-manifest.json`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4e/fresh-guarded-replay-summary.json`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4e/fresh-guarded-replay-execution.json`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4e/restore-verification.json`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4e/checkpoint-freeze-receipt.json`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4e/acceptance-record.json`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,acceptance.md,change-log.md}`
- This contract status and acceptance checkpoint.

## Stop conditions

- Reviewer reports an unresolved Critical/Important defect or requirements conflict.
- Gate, matrix, replay summary, source/candidate identity, schema/content hash, pause/volume, or
  original/recovery source invariant differs.
- Dump is not independently restorable, restore parity differs, or cleanup cannot prove the
  temporary target and volume are absent.
- A required repair crosses into S5+ behavior, production-like cutover, source mutation, or a
  product/architecture choice not already owned by OpenSpec.

## Done means

- All five Evidence Landing acceptance boxes have direct evidence and are checked.
- The external landing-only checkpoint is content-addressed, independently restore-verified,
  immutable, and referenced by committed manifest/acceptance hashes.
- S4 review has no open Critical/Important finding; all required checks and final invariants pass.
- Task 4.5 and all S4 become Accepted and are committed alone; Task 5.1 has not started.

## Acceptance checkpoint

- Independent final review: two read-only `Ready` verdicts; zero open Critical/Important findings.
- Fresh replay summary/matrix/entry hashes:
  `a88b44fa...e80b5` / `eaba2ecb...a923` / `5b77b4a4...c58293`.
- Checkpoint manifest SHA-256: `ab091aac1cfbf2ba1699f521b9a5629d4d9b02dfb236e0600a4f711219c966b1`.
- Restore verification SHA-256: `caf789ae87dc4c0429e068dcc3421c8d1346bec02296f6d056d816a3416f0acc`.
- Frozen external tree SHA-256: `4ae5f2ce64e4d46101a164a3c8d0a14395b6d34015338cd9fadfa09096b05012`.
- Exact C2_0004 26-table logical SHA-256:
  `6328e811d9c63f519c47f4dd7fe1a662e34b71ca6afb266688a5171d063054e8`.
- Source/restore PostgreSQL system IDs are distinct; schema, table, landing aggregate, integrity,
  and logical hashes match exactly; temporary container/socket are absent and Docker volumes did
  not change.
- Focused `48 passed`; default Canonical V2 `73 passed, 33 skipped, 4 expected xfails`; real
  disposable `35 passed`; S1 `10 passed, 5 skipped`; S2/S2B `32 passed`.
- All five Evidence Landing acceptance boxes are supported. Task 5.1 remains not started.
