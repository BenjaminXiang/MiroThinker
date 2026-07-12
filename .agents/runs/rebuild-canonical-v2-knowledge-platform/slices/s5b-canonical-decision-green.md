# Slice Contract: s5b-canonical-decision-green

## Status

Accepted at `2026-07-12T04:32:46Z`. This slice implements OpenSpec Task 5.2 against Accepted Task
5.1 commit `72c9a7d`. It does not authorize Task 5.3 identity construction, an S5 aggregate
acceptance, or a durable-candidate write.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `5.2`
- Depends on: Accepted Task 5.1 at commit `72c9a7d`

## Lean execution

- This slice contract and OpenSpec Task 5.2 are the only implementation-plan sources.
- Implement one observable vertical RED/GREEN increment at a time and run only its focused checks.
- Perform one combined specification/code-quality review for Task 5.2. Migration and database-
  safety boundaries additionally receive one focused safety review.
- Run complete regression, source-isolation, backup-gate, and safety verification only at the Task
  5.2 commit checkpoint.

## Goal

Turn the accepted assertion/decision RED into a reproducible deep decision module and durable,
append-only PostgreSQL history so users receive only evidence-supported current facts while every
competing or rejected assertion remains auditable.

## Non-goals

- Normalize, merge, split, reverse, review, or publish canonical identities (Tasks 5.3–5.4/5.6).
- Implement full temporal policy or eligibility (Tasks 5.5/6.5).
- Add typed Professor/Company/Paper/Patent projections or the relationship catalog (S6).
- Implement `KnowledgeBuild`, candidate release publication, Milvus, query, answer, or Web behavior.
- Call a live LLM/provider or use model world knowledge as source evidence.

## Allowed scope

- Shared Task 5.2 contract reconciliation already identified by Accepted Task 5.1.
- One package-internal decision-engine module and one explicit-target PostgreSQL adapter.
- One shared Canonical V2 minimum-revision helper and the landing runtime call site.
- One new forward Alembic revision after C2_0004, with bounded decision-integrity objects only.
- Focused unit/contract and real disposable PostgreSQL tests.
- This slice, OpenSpec task/change log, and verification evidence.

## Forbidden changes

- Any original/recovery/durable-candidate database write, original Milvus client, source replay,
  provider call, or active-release/index pointer mutation.
- Generic `DATABASE_URL` fallback, implicit target identity, or write before Accepted backup gate.
- Historical migration or frozen S4 checkpoint/replay artifact rewrite.
- S6 typed projection tables, Task 7 public interfaces, dependency changes, or legacy runtime/API
  behavior.
- Weakening evidence, source, role, hash, append-only, test, migration, or gate constraints to make
  Task 5.2 pass.

## Expected unchanged behavior

- All Accepted S1–S4 and Task 5.1 contract behavior remains GREEN.
- Landing persistence works at its exact C2_0004 capability and at known compatible descendants.
- KnowledgeBuild, KnowledgeRead, KnowledgeAnswer, and ReleasePublication remain strict RED.
- The durable candidate remains C2_0004 with the accepted S4 landing checkpoint and zero canonical,
  relationship, or publication rows.

## Required checks

- Accepted Task 5.1 forced RED is observed before production implementation.
- Unit/contract tests cover retention, deterministic constraints, zero/one/many survivors,
  structured-output integrity, stable replay, unresolved no-current behavior, and relationships.
- A fresh network-none/tmpfs PostgreSQL disposable proves C2_0005 upgrade/downgrade/re-upgrade,
  database constraints, append-only history, exact replay, restart readback, and atomic rollback.
- Complete Canonical V2/S1/S2/S2B, Ruff, Pyright, strict OpenSpec, diff/secret, formal gate, source
  hash/pause/isolation, S4 checkpoint, and durable-candidate read-only checks pass.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`

## Stop conditions

- A test target cannot be independently proved disposable before any migration/storage write.
- Correctness requires original/recovery/durable-candidate data, a live provider, an S6/S7 public
  contract, or a product decision absent from approved OpenSpec/Task 5.1 RED.
- Complete assertion/outcome/decision persistence cannot be atomic, append-only, replay-stable, and
  reconstructable without broadening the approved schema surface.
- A C2_0005 change would invalidate or rewrite accepted C2_0004 landing evidence rather than adding
  a compatible descendant capability.

## Done means

- Every supplied field/relationship assertion is retained with a stable constraint outcome and
  auditable decision, including zero-survivor and unresolved cases.
- Selected/accepted current values are traceable to retained assertions; rejected, conflicting, or
  unresolved evidence never becomes a current fact.
- Exact replay is order-independent/idempotent, all invalid trace/role/history writes fail closed,
  and a fresh process reads the same typed durable result.
- The disposable is deleted, source/candidate invariants match, Task 5.2 is Accepted and committed
  alone, and Task 5.3 has not started in the same commit.

## Acceptance checkpoint

- The merged specification/code-quality review and its migration-safety closure are `APPROVED` with
  zero open Critical/Important findings.
- Default Canonical V2: `93 passed, 48 explicit skips, 4 approved future-interface xfails`.
- Real disposable PostgreSQL baseline/integrity/decision: `41 passed`; isolated landing
  compatibility: `10 passed`; decision engine: `11 passed`.
- S1 plus S2/S2B: `49 passed`; S4 checkpoint harness: `23 passed`.
- Ruff check/format and Pyright passed; the wheel contains the complete C2_0001–C2_0005 history and
  decision modules; strict OpenSpec, diff, and secret scans passed.
- Exact Accepted S2B gate/source hashes, original `pgtest` pause/volume, original Milvus hash-only
  check, S4 checkpoint hashes, candidate marker/system/revision/counts, and zero non-landing rows
  were reverified. Candidate probes forced read-only sessions; persistent candidate read-only is not
  claimed because its unforced database default remains `off`.
- The Task 5 disposable container, its three owned databases, host socket root, and wheel-check
  artifacts were removed gracefully; Docker volume-set SHA-256 remained
  `8314a2b0200baffdf78d25ebfe0a9f11c5b22f129f8f33c05f1aa4f859ec896c`.
- OpenSpec task 5.2 is complete. Task 5.3 remains pending and no durable candidate, source, index,
  provider, legacy `chat.py`, or runtime API behavior changed.
