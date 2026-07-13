# Slice Contract: s6h-aggregate-s6-review

## Status

Accepted at `2026-07-13T14:48:01Z` under the user's objective-verification self-approval
authorization. The first full real-PostgreSQL run exposed one systemic historical-fixture defect;
all four siblings were repaired and the complete corrected matrix is GREEN. Zero open
Critical/Important findings remain.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.8`
- Depends on: Accepted Task 5.7/S5G and Tasks 6.1-6.7 through commit
  `9b300222338e24e8faac661cf7154ef7f7fb19b8`

## Goal

Verify the complete S6 typed-domain, inclusion, relationship, persistence, and path-eligibility
foundation as one bounded candidate; account for all sibling invariants and Canonical V2 side-branch
patches; close every Critical/Important review finding; and accept Aggregate S6 as the exact Git
mainline-promotion candidate without promoting product data or indexes.

## Non-goals

- Implement S7 candidate releases, manifests, publication, Milvus projection/indexing, or rollback.
- Implement KnowledgeRead, KnowledgeAnswer, consumer migration, UI/admin behavior, or S8-S12.
- Write, migrate, resume, mount, or connect to original `pgtest`, original Milvus, the recovery
  checkpoint, or the durable C2_0004 landing candidate.
- Merge, rebase, push, archive the OpenSpec change, or move Git `main` inside this slice.

## Allowed scope

- Read-only review of Accepted Tasks 5.7 and 6.1-6.7 source, tests, migrations, contracts, and
  evidence.
- A focused S6 aggregate regression only if review proves an observable cross-slice invariant is
  not already exercised; a discovered implementation defect may be repaired only within the S6
  internal seams and must receive independent RED/GREEN evidence.
- Existing Canonical V2 fixtures that create, mark, migrate, and remove their own disposable sibling
  PostgreSQL databases from the explicit S6c base target.
- This slice, aggregate review/evidence, current continuation and promotion-gate documents, and the
  existing OpenSpec/portfolio/ledger status artifacts after objective acceptance.

## Forbidden changes

- New public interfaces, compatibility `ready` fields, release/publish/index pointers, product or
  source data, catalog semantics, C2_0001-C2_0010 history rewrites, or provider calls.
- Treating source-potential catalog rows as built relationships, derived/session relations as
  canonical, ordinary quality as hard exclusion, or a cross-domain endpoint as valid without its
  typed projection/evidence lineage.
- Blind cherry-pick of the S6c/S6d/S6f RED branches or the Task 6.1 preparation-only candidate
  artifacts; every unique patch must be shown integrated, superseded, or intentionally abandoned.
- Generic database URLs, writes to the explicit base database, destructive worktree cleanup, or any
  modification of the dirty root worktree.

## Expected unchanged behavior

- One content-addressed catalog continues to define exactly four domains, 28 typed subobjects, 34
  canonical relationship types in seven families, and eight cross-domain traversal directions.
- Inclusion, typed projections, typed relationships, and six independent path decisions remain
  release/evidence/policy bound; no global readiness value appears.
- All four future public Modules remain expected REDs for their exact missing S7-S9 seams.
- Original/recovery/durable-candidate data, legacy runtime behavior, and remote Git state remain
  unchanged.

## Required checks

1. Review the S6 code/test/evidence surface against every Task 6.1-6.8 requirement and canonical
   acceptance criterion; close all Critical/Important findings with exact evidence.
2. Prove the bounded matrix accounts for all four domain roots, 101 domain fields, 28 typed
   subobjects, 34 relationship types/seven families, eight directions, six paths, and the sibling
   identity/domain/evidence/release/time/currentness invariants.
3. Re-run focused inclusion/domain/relationship/path pure tests and the complete no-external
   Canonical V2 suite; only the four future public-module xfails may remain.
4. Re-run domain and relationship persistence/migration matrices only through per-test explicitly
   marked disposable siblings; prove every sibling is removed and the base target is unchanged.
5. Re-run deterministic catalog generation/check, shared contracts, Ruff, Pyright, strict OpenSpec,
   migration-head, formal backup-gate, frozen-source, diff/scope/secret/import, and generated-file
   cleanup checks.
6. Inventory every Canonical V2 branch/worktree patch, preserve the root dirty state byte-for-byte,
   and leave the V2 integration worktree clean at the Accepted commit.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s6-aggregate-review.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/code-grounded-mainline-plan-2026-07-13.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/mainline-promotion-gate.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,acceptance.md,change-log.md}`
- `openspec/change-ledger.md`
- `.agents/portfolio.md`

## Stop conditions

- A finding needs S7+ behavior, a new public/data contract, product policy, catalog semantics, or a
  schema revision beyond the accepted Task 6 scope.
- Any required command can target only the original/recovery/durable candidate, cannot prove a
  disposable sibling identity before write, or fails to clean its owned sibling.
- A Critical/Important finding remains unresolved, a side-branch patch is unaccounted, the root
  dirty-state inventory changes, or a non-future-module xfail/failure remains.

## Done means

- Task 6.8 and Aggregate S6 have zero open Critical/Important findings and complete fresh evidence.
- Tasks 6.1-6.8 are Accepted at one independent local commit; S7 remains unstarted.
- The exact Accepted commit is a clean, strict fast-forward descendant of Git `main`, every V2 side
  patch is accounted for, and the separate mainline-promotion gate is Ready to run.
- No database/index/product cutover, push, PR, archive, merge, rebase, or root-worktree mutation
  occurred.

## Rollback note

Revert the independent Aggregate S6 documentation/test commit. Any owned disposable PostgreSQL
sibling must already be absent; no product database, index, release pointer, or remote Git rollback
is required.
