# Slice Contract: s6r2-catalog-and-boundary-green

## Status

Accepted at `2026-07-13T18:57:32Z`. The additive catalog/shared-boundary increment passed its
deterministic, tamper, compatibility, package, full no-external-database, static, scope, and two
independent review gates. Task 6.10 remains open; S6R3 Person projection is the next Ready increment.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.10` (catalog/shared-boundary increment)
- Depends on: Accepted S6R1 RED

## Goal

Create a new deterministic catalog/version and shared manifest contracts that describe internal
Person/Technology reference knowledge while retaining exactly four public domains and preserving the
historical Accepted S6 catalog bytes as evidence.

## Non-goals

- No Person/Technology projection builder, relationship execution, persistence, index construction,
  query/answer behavior, or candidate publication.
- No modification of historical catalog/migration artifacts in place.

## Allowed scope

- New S6R catalog builder/validator/evidence under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s6r/`.
- New packaged versioned catalog/config under
  `apps/miroflow-agent/src/data_agents/canonical_v2/catalogs/` and minimal loader changes.
- Shared projection/index manifest scope types in `contracts.py` and focused catalog/shared tests.
- S6R1 tests owned by this increment when converting their catalog/boundary groups GREEN.

## Forbidden changes

- Existing Accepted S6 catalog bytes, C2_0001-C2_0010, domain projection/inclusion semantics,
  relationship execution, path eligibility, S7+ code, databases, indexes, provider calls, or active
  pointers.
- Public-domain values other than `professor`, `company`, `paper`, `patent`.
- `product_has_capability` or any Product-capability canonical field/relation.

## Expected unchanged behavior

- Historical catalog v1 remains reproducible from its historical authority snapshot/evidence.
- Four-domain typed projection tests continue to bind the catalog selected for their release.
- Public domain and internal auxiliary are distinguishable without making internal references public.

## Required implementation effects

- Versioned internal reference definitions for `person`, `technology_concept`, and
  `technology_route`, including evidence/time/release obligations.
- Catalog relationship states distinguish non-adoption discussion-or-mention, claimed adoption, and
  demonstrated use; any changed relationship type receives a new version.
- Shared projection/index manifests carry a validated `public_domain` or `internal_auxiliary` scope;
  auxiliaries name their reference type and cannot masquerade as a public domain.
- Deterministic serialization, source citations/hashes, content identity, and packaged/evidence
  parity.

## Required checks

- Observe the applicable S6R1 RED groups fail before implementation, then pass after the smallest
  catalog/shared-contract changes.
- Deterministic new-catalog build and `--check`; historical v1 byte/hash preservation.
- Catalog/validator/shared-contract tests, four-public-domain and no-Product-capability negatives.
- Ruff, Pyright, wheel/package-content check, strict OpenSpec, diff/source/scope/secret/cache checks.
- Independent merged spec/code-quality review with zero open Critical/Important findings.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- S6R catalog manifest/hash evidence.
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{change-log.md,tasks.md}` only at the
  owning Task 6.10 aggregate checkpoint; do not mark Task 6.10 complete here.

## Stop conditions

- A public domain must be added, an Accepted artifact/migration rewritten, or runtime code must read
  `.agents/runs`.
- Relationship semantics change without versioning or old/new versions cannot coexist.
- Manifest scope cannot be validated without S7 publication implementation.
- Correctness requires Person/Technology runtime projection behavior owned by later S6R increments.

## Done means

- Catalog/boundary RED groups are GREEN through a new content-addressed catalog and shared contracts.
- Exactly four public domains remain; internal reference definitions/scopes are machine-distinct;
  historical v1 evidence is unchanged; `product_has_capability` is absent.
- All required checks/review pass and this increment is Accepted; Task 6.10 remains In Progress.

## Acceptance evidence

- New builder/validator TDD: initial missing-script/artifact RED was `10 failed`; the final suite is
  `13 passed`, including exact semantic-matrix mutations and symlink-parent write escape.
- S6R catalog/shared seam: `32 passed, 5 xfailed`; the five xfails are the later Person/Technology/
  relationship groups, while both catalog/scope groups are GREEN.
- Complete no-external-database Canonical V2 suite: `214 passed, 137 skipped, 9 xfailed`; all nine
  xfails are the five pending S6R projection/relationship contracts plus four historical future
  public-module REDs, with no real failure.
- Reference catalog content SHA-256 is
  `ff347833ce4e86f06ead0282c566e691e983cc19d3a1c81a294d3bdb378a45a7`; evidence/package file
  SHA-256 is `84d778384f8dfb27118f39e498f28a3c51026c2c488d64a9b467f6d23491dbbf`
  and `cmp` is clean. Historical v1 remains byte-identical at
  `b227285fef5d49ad0b30871e5ccb0c1932443206fac99f5fa708ae586c5383c0`.
- Deterministic `--write` and `--check` passed. The wheel contains both catalog JSON resources.
  Ruff check/format and Pyright passed with `0 errors, 0 warnings, 0 informations`.
- Strict OpenSpec, `git diff --check`, allowed production scope, high-confidence secret, and
  generated-cache checks passed.
- The main review initially found three Important defects and the integrity audit found three
  non-duplicate Important defects. Corrections made Technology unresolved endpoints fail closed,
  preserved Person predecessor role/evidence/time/path semantics, froze exact validator matrices,
  made reference re-exports lazy, versioned manifests as explicit v2, and rejected symlink-parent
  writes. Both final re-reviews returned `Ready: Yes` with zero open Critical/Important findings.
- Known Minor: evidence and packaged files are replaced sequentially; interruption can temporarily
  break parity, but deterministic `--check` detects it. No runtime/database/index state is involved.

## Rollback note

Remove the new catalog/version and revert loader/shared-scope changes. Historical catalog bytes and
all data/index state remain untouched.
