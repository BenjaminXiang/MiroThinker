# Slice Contract: s6r1-internal-reference-contract-red

## Status

Accepted at `2026-07-13T18:21:59Z`. Seven strict RED groups fail only through the intended absent
catalog/interface sentinels, the historical four-domain/path baseline remains GREEN, and the final
independent test-design review has zero Critical, Important, or Minor findings. No production code
changed in this slice.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.9`
- Depends on: historical Aggregate S6 Accepted at commit `f0e6224`
- Correction authority: ADR-014, ADR-015, ADR-016, and the active canonical/release specs

## Goal

Freeze executable RED contracts for the smallest internal-reference seam that reconciles role-neutral
Person identity/projection, unresolved Person references, Technology concepts/routes, exact
relationship semantics/versioning, and public-domain versus internal-auxiliary release scope without
widening the four-domain product.

## Non-goals

- No production module, catalog artifact, migration, persistence, release/index builder, query path,
  answer path, or provider behavior.
- No fifth public Person or Technology inclusion domain.
- No canonical Product-capability assertion or relationship.
- No rewrite of historical S6 catalog artifacts, migrations, or acceptance evidence.

## Allowed scope

- New focused RED tests under `apps/miroflow-agent/tests/canonical_v2/`.
- Focused catalog contract tests under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s6/` only when they assert the new desired
  contract without changing accepted catalog bytes.
- This slice contract and Task 6.9 verification/task/change-log evidence.

## Forbidden changes

- `apps/miroflow-agent/src/`, Alembic revisions, packaged catalogs, database/index state, original or
  recovery evidence, durable candidate state, active pointers, legacy consumers, and S7+ behavior.
- Reclassifying Professor as Person, forcing name-only references into identity, unchecked registry
  endpoints, `product_has_capability`, or adding Person/Technology to public `Domain` literals.

## Expected unchanged behavior

- `DomainProjectionBuilder` still returns only Professor, Company, Paper, and Patent projections.
- The accepted S6 catalog, four-domain inclusion, relationship, and six-path behavior remain the
  historical GREEN baseline.
- Existing source hashes are allowed to show the known authority drift until S6R2 creates a new
  versioned catalog; the drift is evidence, not a hash-only fix in this RED slice.

## RED groups

1. The catalog keeps exactly four public domains while declaring internal `person`,
   `technology_concept`, and `technology_route` reference types.
2. Shared manifests distinguish `public_domain` from `internal_auxiliary`, and the catalog contains
   no `product_has_capability` relation.
3. Accepted resolved Professor/personnel/author/inventor evidence can bind one role-neutral Person
   identity/projection without changing the source public-domain identity.
4. Name-only, same-name-conflicting, or otherwise unresolved Person references remain separate and
   materialize no Person identity.
5. Technology projections preserve aliases, definition, hierarchy, release/source/time lineage and
   distinct non-adoption discussion-or-mention, claimed-adoption, and demonstrated-use semantics.
6. Relationship projection accepts resolved internal-reference endpoints only through an explicit
   registry and validates exact `(relationship_type_id, version)` coexistence.
7. Person/Technology cannot enter public inclusion/path domains, Industry Brief remains derived, and
   Product/Technology evidence never entails Product capability.

Normal RED SHALL report exactly seven strict expected failures. Forced RED SHALL report exactly seven
failures caused by the missing/new contract behavior, not import typos or unrelated dependencies.

## Required checks

- Focused normal RED and `--runxfail` forced RED for the two new contract-test files.
- Existing deterministic catalog `--check`, recorded as the expected authority-source drift.
- Existing four-domain/path negative tests proving no public-domain widening.
- Ruff and Pyright for test code, strict OpenSpec, `git diff --check`, scope/secret/generated-cache
  checks.
- One independent specification/test-design review with zero open Critical/Important findings.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`
- This slice status and exact normal/forced RED output.

## Stop conditions

- Desired behavior cannot be tested through one package-internal reference-projection interface.
- A test needs S7 publication/index or S8/S9 query/answer behavior to prove S6R semantics.
- Correctness requires a fifth public domain, canonical Product-capability relation, historical
  artifact/migration rewrite, or production/candidate write.
- A RED passes before implementation, fails for an unrelated reason, or masks sibling behavior.

## Done means

- All seven observable RED groups exist and fail for the exact absent contract behavior.
- Existing historical S6 behavior remains unchanged, review has zero Critical/Important findings,
  required static/scope checks pass, and Task 6.9 is marked complete.
- The slice is Accepted as a test contract only; Task 6.10 remains unimplemented and S7 remains
  blocked.

## Acceptance evidence

- Focused normal RED: exactly `7 xfailed in 5.18s`, exit 0.
- Focused forced RED with `--runxfail`: exactly `7 failed in 5.14s`, expected exit 1; every failure
  is an exact missing additive catalog, manifest-scope, internal-reference projection, or explicit
  relationship-registry contract.
- Existing inclusion/domain/path matrix: `45 passed in 6.03s`.
- Ruff check/format and app-environment Pyright passed; Pyright reported `0 errors, 0 warnings, 0
  informations`.
- Historical `build_domain_catalog.py --check` failed only on the recorded
  `design.md` authority-source hash drift; S6R2 owns the new additive versioned catalog and must not
  rewrite the accepted v1 bytes.
- Strict OpenSpec and `git diff --check` passed; production-scope, high-confidence secret, and
  generated-cache checks were clean.
- The final independent re-review returned `Ready: Yes` with no Critical, Important, or Minor
  findings. This accepts only the test contract, not production, merge, publication, or cutover.

## Rollback note

Delete the new RED tests and revert this slice/evidence update. No product, database, index, or
provider rollback is required.
