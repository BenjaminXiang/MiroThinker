# Slice Contract: s2c1-claim-level-case-contract-red

## Status

Accepted at `2026-07-14T15:46:46Z`. The ADR reconciliation gate, historical S2/S2B, S6R, and
aggregate S7 are Accepted at 46/80. Task 2.7 remains unchecked; S2C2 owns the validator
implementation and corpus migration.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `2.7` (RED schema/validator increment)
- Depends on: historical S2/S2B Accepted and the ADR reconciliation gate

## Goal

Freeze a machine-readable claim-level case-contract interface and deterministic validator covering
required/forbidden claims/entities, allowed variants, source snapshots/as-of, enumeration policy,
observable stage oracles, hard per-case outcomes, and non-normative reference prose.

## Non-goals

- No corpus migration, human acceptance, runtime query/answer code, provider judging, database/index
  write, or reinterpretation of historical S2 evidence.

## Allowed scope

- Exactly six strict-xfail schema/validator groups under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/test_claim_level_case_contract.py`.
- Freeze the future local target
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/claim_level_case_contract.py` with only
  `ClaimLevelCaseContract` and `validate_case_contracts`; implementation remains S2C2 ownership.
- This slice plus verification/change-log evidence; no historical S2 artifact mutation.

## Forbidden changes

- Existing S2 corpus/threshold/manifest bytes, reference prose, production Python, databases,
  indexes, providers, S8/S9 behavior, or aggregate thresholds.
- Model memory/reference wording as external truth or averaged hard failures.

## Expected unchanged behavior

- Historical S2 remains Accepted at its original contract.
- S8/S9 still cannot use the corpus as an acceptance oracle before S2C acceptance.

## Required RED groups

- Strict schema/version/content identity and duplicate/unknown-field rejection.
- Claim subject/predicate/object/materiality/evidence-obligation validation.
- Required/forbidden entity and allowed-variant behavior.
- Snapshot/as-of and enumeration-universe/member/coverage validation.
- Observable stage-oracle contracts without private call-order coupling.
- Hard per-case failure independence and reference-prose non-normativity.

## Required checks

- Normal execution reports exactly six strict xfails. Forced `--runxfail` reports exactly six
  `_MissingClaimLevelCaseContractModule` failures for the exact absent target file; nested imports,
  unrelated fixture failures, or environment skips are not accepted RED.
- Ruff/Pyright for validator test code, deterministic fixture serialization, strict OpenSpec,
  diff/scope/secret/cache checks.
- Independent spec/test-design review with zero open Critical/Important findings.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- This slice status and exact RED outputs.
- `change-log.md`; Task 2.7 remains unchecked.

## Stop conditions

- Schema requires implementation-private order/calls, a prose gold answer, live external truth, or
  S8/S9 behavior.
- Correctness requires modifying historical S2 artifacts rather than creating a new version.

## Done means

- All observable RED groups fail for exact absent contract behavior and review/static checks pass.
- This test-only slice is Accepted; corpus migration and Task 2.7 completion remain pending.

## Acceptance evidence

- Normal focused RED: exactly `6 xfailed in 0.11s`.
- Forced `--runxfail`: exactly six `_MissingClaimLevelCaseContractModule` failures for the absent
  `claim_level_case_contract.py`; no skip, nested import, fixture, or environment failure masked RED.
- Ruff check and format check passed; Pyright reported `0 errors, 0 warnings, 0 informations`.
- Strict OpenSpec and `git diff --check` passed. The future target is absent and the current Slice
  contains only this six-group test contract plus its Slice/evidence records.
- Historical S2 challenge/regression/manifest/threshold SHA-256 values remain respectively
  `ee46c677af668131fb8da568fabd6386659f3287d0bdb0fd740f7069497f6f9f`,
  `f2656e8c2f0803452af18fa0d478eec1b1e1b94eaa97ef48d06d0828401297da`,
  `dc7cc10ba08db341a38cc08da1edd2449594120a3861735edfd514b29be46088`, and
  `bce20bf959ba8a2b0997fe2bc1d71e5f727b857a2e374990cf76085c1e13b5cc`.
- Independent final review of test SHA-256
  `8253c84efe0e86a1dad15afb8097f1b3577dc720c4e35fe86894af33991d0b0a` reported zero Critical,
  zero Important, and zero Minor findings. Corpus-family migration, judge calibration, and human
  review remain explicitly owned by S2C2/S2C3 and are not blockers for this RED Slice.
- Task 2.7 and the ledger remain unchanged at 46/80. No production/runtime/data/index state,
  Commit, Push, PR, archive, or Cutover changed.

## Rollback note

Delete the new RED fixtures/tests and revert evidence. No runtime/data/index rollback is required.
