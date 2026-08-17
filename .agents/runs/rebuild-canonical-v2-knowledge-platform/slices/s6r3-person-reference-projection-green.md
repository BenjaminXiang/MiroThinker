# Slice Contract: s6r3-person-reference-projection-green

## Status

Accepted at `2026-07-13T20:37:07Z` after deterministic closed-graph replay, focused/full regression,
static, strict OpenSpec, scope, and two independent review gates passed with zero open Critical,
Important, or Minor findings. Technology and relationship integration remain outside this slice.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.10` (Person identity/reference/projection increment)
- Depends on: Accepted S6R2 catalog/shared boundary

## Goal

Implement the Person half of one package-internal deep module:
`InternalReferenceProjectionBuilder.project(request) -> InternalReferenceProjectionResult`. Resolve
accepted role-neutral Person identities across four-domain evidence while preserving explicit
unresolved references and leaving `DomainProjectionBuilder` four-domain-only.

## Non-goals

- No Technology implementation, relationship integration, persistence/migration, publication/index,
  public Person domain, query/answer path, or provider call.
- No attempt to resolve same-name references from name alone.

## Allowed scope

- `contracts.py`, `domain_projection_models.py`, `canonical_identity_resolution.py`.
- New `internal_reference_projection.py` and focused identity/reference/projection tests.
- Existing domain-projection tests only for Person-bearing typed-reference compatibility and the
  four-domain negative invariant.

## Forbidden changes

- Domain inclusion or public path-domain literals, four-domain projection union/counts, C2_0001-
  C2_0010, database/index state, legacy consumers, S7+ behavior, Product capability, or runtime
  access to `.agents/runs`.
- Reclassifying a Professor canonical identity as Person or mutating query-time identity state.

## Expected unchanged behavior

- Professor remains a public-domain identity/projection; an accepted role-neutral Person identity is
  a separate internal identity connected by evidence/decisions.
- Company/Paper/Patent/Professor root projection bytes change only where the new versioned typed
  reference contract explicitly requires it.
- Existing four-domain inclusion, relationship, and path behavior remains GREEN.

## Required implementation effects

- A strict Person reference discriminates resolved from unresolved state and binds source reference,
  evidence IDs, and optional canonical Person identity only when resolved.
- Person identity policy permits shared resolution only from accepted evidence/decision lineage;
  name-only, same-name conflict, or insufficient evidence produces no provisional Person identity.
- Person projections retain release/as-of/content hash, aliases/display identity, typed education,
  work/Company-role/author/inventor links, and their public-domain evidence anchors.
- Request/result manifests are deterministic and reject wrong release/type, dangling evidence,
  unresolved-as-canonical, duplicate ownership, and non-public evidence anchors.

## Required checks

- Observe Person S6R1 RED groups fail first, then pass through real pure code paths.
- Focused identity-resolution and internal-reference projection tests, Person-bearing four-domain
  model tests, and four-domain inclusion/path negative tests.
- Existing canonical identity/history/reversal and domain projection suites.
- Ruff, Pyright, strict OpenSpec, diff/scope/secret/cache checks.
- Independent merged spec/code-quality review with zero open Critical/Important findings.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- This slice status and exact RED/GREEN outputs.
- `change-log.md`; Task 6.10 remains unchecked.

## Stop conditions

- Generic identity behavior cannot prevent name-only provisional Person materialization without
  weakening another domain's accepted behavior.
- Correctness requires a public Person inclusion/path domain, persistence migration, S7 index, S8
  retrieval, or query-time identity write.
- A Person projection cannot trace every resolved reference to accepted four-domain evidence.

## Done means

- All resolved/unresolved Person RED groups are GREEN through the internal-reference interface.
- Zero unresolved references create Person identities; Professor remains Professor; exactly four
  public domains remain; deterministic lineage/content checks pass.
- Required checks/review pass and this increment is Accepted; Task 6.10 remains In Progress.

## Rollback note

Revert Person reference/identity/projection code and tests. No persistence, data, index, or provider
rollback is required.
