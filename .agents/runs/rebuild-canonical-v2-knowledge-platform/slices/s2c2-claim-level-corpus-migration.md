# Slice Contract: s2c2-claim-level-corpus-migration

## Status

Accepted at `2026-07-14T16:53:22Z`. Task 2.7 is Accepted and the ledger is 47/80. S2C3/Task 2.8
remains the sole owner of human review, judge calibration, acceptance eligibility, aggregate S2C
acceptance, and the S8/S9 oracle unlock.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `2.7` (schema/validator and corpus-migration GREEN)
- Depends on: Accepted S2C1 RED and immutable historical S2 corpus

## Goal

Implement the versioned case-contract schema/validator and migrate applicable regression/challenge
turns into a new content-addressed corpus version while retaining prose/key points only as review
context and preserving every unresolved review state explicitly.

## Non-goals

- No automatic truth creation, live provider refresh, LLM judge acceptance, runtime S8/S9 behavior,
  database/index write, or mutation of historical S2 artifacts.

## Allowed scope

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/` schema, validator, conversion tooling,
  new case contracts, snapshots, manifests, and tests.
- Read-only inputs from accepted S2/workbook/PRD/challenge artifacts.
- Verification/task/change-log updates at Task 2.7 acceptance.

## Forbidden changes

- Historical corpus/threshold bytes, reference prose, known-bad response relabeling as positive truth,
  model-memory facts, runtime code, provider calls, databases, indexes, or lowered thresholds.

## Expected unchanged behavior

- Historical S2 remains separately reproducible and Accepted.
- Cases not yet human-reviewed remain `pending_user_review` and cannot enter an S8/S9 acceptance run.

## Required implementation effects

- Deterministic schema/validator with stable IDs and content hashes.
- Applicable cases encode required/forbidden claims/entities, variants, snapshots/as-of,
  enumeration policy, stage oracles, and hard/soft distinctions.
- Dynamic evidence uses bounded content-addressed snapshots or an explicit unavailable-evidence
  outcome; reference prose is non-normative metadata.
- Conversion reports migrated, excluded/not-applicable, blocked-missing-evidence, and pending-review
  counts without silently dropping a case.

## Required checks

- Observe S2C1 RED first, then focused schema/validator/conversion GREEN.
- Deterministic rebuild/check and snapshot/manifest tamper tests.
- Case-family accounting against accepted S2 regression/challenge manifests.
- Ruff, Pyright, strict OpenSpec, diff/source/scope/secret/cache checks.
- Independent merged spec/code-quality review with zero open Critical/Important findings.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- New S2C manifest/schema/corpus hashes and review-state counts.
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`; mark Task 2.7
  complete only when this slice is Accepted.

## Stop conditions

- A case cannot be migrated without inventing truth, using live mutable evidence, or resolving a
  material product ambiguity absent from OpenSpec.
- Conversion would overwrite historical S2 bytes or hide pending review/missing evidence.

## Done means

- Task 2.7 is Accepted with a deterministic new schema/corpus version and complete accounting.
- No pending/unreviewed case is mislabeled accepted; S2C itself remains In Progress until Task 2.8.

## Acceptance evidence

- The run-local Pydantic interface exposes only `ClaimLevelCaseContract` and
  `validate_case_contracts`. Six S2C1 groups are GREEN; focused schema/conversion verification is
  `11 passed in 0.90s`.
- Deterministic `--write` then `--check` retains exactly 52 contracts and 53 snapshots with zero
  omitted/extra source cases: 29 `pending_user_review`, 23 `blocked_missing_evidence`, zero
  `human_reviewed`, and zero `acceptance_eligible`. All 52 source families are accounted for.
- Manifest content identity is
  `df3a7b09a4f049ac6b34bfd1f128329dc9e7effb3ec61398317026778dc0c8ff`.
  Corpus/accounting/snapshot/manifest file SHA-256 values are respectively
  `75ff02e0610b93274eba530994a3b04c2bc2a427df9db2ae6d07aaee690a6668`,
  `e953c2fcf64daf66614e26831f0d1263f087263bcdb9771fc20b6123e34fbc48`,
  `85c1e4c1660e151526d54f9b1416917782f961b318091550bb3ef8042d16e253`, and
  `fbc95a25fc662ac9b3c32491a45ef40953a50643888759ee1d438529f00d682f`.
- The schema/builder/schema-test/migration-test SHA-256 values are respectively
  `0e6347e857dee2270cfca8acf16b0f89347521b531ce703d3e3e574230775c9d`,
  `aad3735c7c8369a7e76e10e016b0f1db19588b158a86da73b71feccf14d1bdbc`,
  `1815c1cbd3c15b80eded172ddc05d3607c5fe77694c41b6913b1e381f42dab09`, and
  `9f2d9bd32c4e112bec87467c5d5f56f916ae2e595588109414e8a75ff0990efb`.
- Historical S2 verification is `20 passed in 0.27s`; its challenge/regression/manifest/threshold
  and workbook hashes remain unchanged. Ruff check/format, Pyright, strict OpenSpec,
  `git diff --check`, source/scope/secret/cache checks, and byte-for-byte rebuild pass.
- Two independent final reviews report zero Critical and zero Important findings. Concrete findings
  for retained snapshot replay, named enumeration cases, safety obligations/variants, deep
  immutability/round-trip identity, stale-instance revalidation, acceptance eligibility, and entity
  cross-reference closure were fixed and replayed. Two Minor/YAGNI items remain nonblocking: cross-
  case validation stays in the artifact validator, and pending representative coverage numbers stay
  unset for S2C3 review.
- Reference prose/key points remain `review_only`; the known-bad founder/Product example was not
  copied into the corpus. No runtime/provider/database/index state, Commit, Push, PR, archive, or
  Cutover changed.

## Rollback note

Remove the new S2C version/tooling and revert evidence. Historical S2 is unchanged.
