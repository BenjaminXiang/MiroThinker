# Slice Contract: s6r5-aggregate-s6-reacceptance

## Status

Accepted at `2026-07-14T02:05:34Z` after all Required checks passed and both final independent
re-reviews reported zero Critical/Important findings. S7 release/index RED is now Ready.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.11`
- Depends on: Accepted S6R1-S6R4 and historical Aggregate S6

## Goal

Independently reaccept the complete S6 foundation after Person/Technology reconciliation, proving
catalog/source binding, identity/reference/domain/relationship/path sibling invariants, applicable
persistence safety, and the no-fifth-public-domain/no-Product-capability boundaries before S7.

## Non-goals

- No new implementation unless aggregate review first produces a focused observable S6R regression.
- No S7 release/index work, S8/S9 behavior, candidate data build, provider call, pointer change,
  commit/push/PR/archive, or cutover.

## Allowed scope

- Read-only review and complete targeted regression of Accepted S6/S6R code, tests, catalogs,
  migrations, and evidence.
- Focused regression tests/fixes only inside the S6R-owned seams when review proves a defect.
- Aggregate review, verification, task/acceptance/change-log/portfolio status evidence.

## Forbidden changes

- New public interface/domain/product policy, S7+ implementation, historical migration/catalog
  rewrite, original/recovery/durable-candidate write, active pointer, unbounded provider call, or
  unrelated cleanup.

## Expected unchanged behavior

- Historical S1-S6 acceptance evidence remains intact and auditable.
- Four public domains, six public paths, retained evidence/decision/temporal semantics, and explicit
  disposable-target safety remain GREEN.
- Internal Person/Technology projections remain release-scoped candidate-build auxiliaries;
  publication/index persistence belongs to S7.

## Required checks

- Deterministic historical-v1 preservation and current S6R catalog build/check/source-hash parity.
- Complete catalog/shared/identity/domain projection/inclusion/relationship/path pure matrix.
- Complete applicable Canonical V2 no-external suite; only named future public-module xfails may
  remain.
- Existing C2_0009/C2_0010 plus any S6R-touched adapter real-disposable PostgreSQL matrix, exact
  target guard, restart/rollback/version coexistence, owned cleanup, and unchanged base.
- Ruff, Pyright, package contents, migration heads, strict OpenSpec, formal S2B gate, frozen source,
  diff/scope/secret/import/cache checks.
- Independent merged aggregate review with zero open Critical/Important findings.

## Evidence to update

- New `.agents/runs/rebuild-canonical-v2-knowledge-platform/s6r-aggregate-review.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,acceptance.md,change-log.md}`
- `.agents/portfolio.md` and `agent-links.md` current DAG/status.

## Stop conditions

- Any non-future expected xfail/failure remains, source/catalog hashes drift, or a Critical/Important
  finding remains open.
- A test can run only against original/recovery/durable-candidate state or cannot prove disposable
  identity/cleanup.
- Correctness requires S7+ behavior, new product semantics, public-domain widening, Product capability,
  or historical artifact/migration rewrite.

## Done means

- Task 6.11 and S6R are Accepted with fresh deterministic, pure, applicable PostgreSQL, static,
  safety, scope, and independent-review evidence.
- Exactly four public domains remain; internal reference counts/hashes and unresolved outcomes are
  recorded; relationship versions coexist; `product_has_capability` is absent.
- S7 becomes the next Ready critical-path slice, but no S7 implementation starts inside this slice.

## Rollback note

Revert only aggregate evidence or a review-proven focused S6R repair. Owned disposable databases are
already removed; no product/candidate/index/provider rollback is required.

## Acceptance evidence

- Aggregate review: `../s6r-aggregate-review.md`.
- Pure aggregate: `167 passed`; complete no-external Canonical V2: `265 passed, 139 skipped, 4
  expected xfailed`.
- Owned real-disposable PostgreSQL identity/domain/relationship matrix: `68 passed`; empty marked
  base, no sibling databases, tmpfs PGDATA, and owned container/port cleanup proved.
- Catalog builder: `13 passed`; catalog check/parity, Ruff, focused format, Pyright, wheel contents,
  imports, unique `C2_0010` head, strict OpenSpec, formal S2B, frozen-source, diff/scope/secret/cache,
  and original-`pgtest` pause checks passed.
- Final review disposition: zero Critical, zero Important. The two recorded aggregate hardening
  Minors are explicitly nonblocking and were not expanded into idealized S6R5 work.
