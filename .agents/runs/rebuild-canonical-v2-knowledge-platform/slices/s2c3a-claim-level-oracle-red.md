# Slice Contract: s2c3a-claim-level-oracle-red

## Status

Accepted at `2026-07-14T17:36:19Z`. S2C1/S2C2 and Task 2.7 are Accepted at 47/80. Task 2.8 remains
unchecked; S2C3B owns the GREEN successor.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `2.8` (RED evaluation/gate increment only)
- Parent Slice: `s2c3-claim-level-oracle-review`
- Depends on: exact Accepted S2C2 corpus/manifest/snapshot version

## Goal

Freeze one minimal, observable, run-local RED interface for exact artifact admission, atomic hard-
case evaluation, stage localization, evidence-bounded recorded judging, and human-reviewed aggregate
acceptance without implementing any evaluator or claiming human review.

## Non-goals

- No human review, LLM/provider call, oracle GREEN, Task 2.8 completion, S2C acceptance, runtime S8/S9
  behavior, threshold change, database/index write, or acceptance of current pending/blocked cases.
- The mixed eligible-plus-explicitly-excluded human corpus and its non-empty exclusion record remain
  S2C3C ownership; S2C3A freezes only single-case gate reachability and fail-closed omission.

## Allowed scope

- Exactly five strict-xfail groups under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/test_claim_level_oracle_evaluation.py`.
- Freeze only the future local target
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/claim_level_oracle_evaluation.py` with one
  public `evaluate_oracle_run(manifest_path, run_input, *, judge_adapter=None)` seam; implementation
  remains S2C3B ownership.
- This Slice plus verification/change-log evidence; Accepted S2C2 artifact bytes stay unchanged.

## Forbidden changes

- S2C2 schema/corpus/accounting/snapshot/manifest bytes, reference prose truth, recorded or live LLM
  acceptance, human-review labels, production/runtime code, providers, databases, indexes, S8/S9,
  Task 2.8, or aggregate acceptance checkboxes.

## Required RED groups

- Exact manifest/contract/accounting/snapshot/schema/version/as-of identity; current-corpus
  ineligibility and any byte/cross-wire drift are refused before judging.
- One evaluator-derived result for every atomic hard requirement across structured claims/entities,
  stage expectations, enumeration/false-exhaustiveness, protected slots, and session transitions;
  any failed/unresolved result fails the case and soft scores cannot mask it.
- Recorded-fake judge requests contain only the exact structured requirement and its named evidence;
  request/response identities are content-addressed and reference prose is absent.
- Invalid/unbound/memory-based/failed judge responses degrade to explicit unresolved outcomes while
  retaining already-completed deterministic results.
- Aggregate eligibility requires exact human-reviewed contracts/snapshots/review records and per-
  family judge calibration; agent/model review cannot substitute, and the current 0-eligible corpus
  reports `acceptance_ready=false` while a synthetic positive fixture only proves gate reachability.

## Required checks

- Normal execution reports exactly five strict xfails. Forced `--runxfail` reports exactly five
  `_MissingClaimLevelOracleEvaluationModule` failures for the exact absent target; nested imports, S2C2
  validation failures, unrelated fixtures, or environment skips are not accepted RED.
- Accepted S2C2 `11 passed`, deterministic builder `--check`, historical S2 `20 passed`, Ruff,
  Pyright, strict OpenSpec, diff/source/scope/secret/cache checks.
- Independent spec/test-design review with zero open Critical/Important findings.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- This Slice status and exact RED outputs.
- `change-log.md`; Task 2.8 and the 47/80 ledger remain unchanged.

## Stop conditions

- RED needs a prose gold answer, model memory, live provider truth, private helper order, invented
  human approval, or mutation of the Accepted S2C2 version.
- A scenario cannot isolate the missing oracle target from an unrelated dependency.

## Done means

- All five groups fail only for the exact absent oracle module and review/static/source gates pass.
- This test-only Slice is Accepted; S2C3B GREEN and S2C3C human acceptance remain pending.

## Acceptance evidence

- The final test SHA-256 is
  `185e39e5770b51733cf6deece435e5f49d7827ff6cc521eef4aa8aaa4f4ff0ca`; the Slice Contract
  SHA-256 is `a765d98871572cdaf131fae11a5367f65770d0a27988cabb72fdf5dbcd59c58b` before this
  status/evidence update.
- Normal execution is exactly `5 xfailed`; forced `--runxfail` is exactly five direct
  `_MissingClaimLevelOracleEvaluationModule` failures for the absent target. Combined Accepted S2C
  verification is `11 passed, 5 xfailed`; historical S2 remains `20 passed`.
- The deterministic corpus builder `--check` retained `52` contracts, `29` pending reviews, `23`
  blocked cases, zero human-reviewed/eligible cases, and manifest content SHA-256
  `df3a7b09a4f049ac6b34bfd1f128329dc9e7effb3ec61398317026778dc0c8ff`.
- Accepted corpus/accounting/snapshot/manifest file SHA-256 values remain respectively
  `75ff02e0610b93274eba530994a3b04c2bc2a427df9db2ae6d07aaee690a6668`,
  `e953c2fcf64daf66614e26831f0d1263f087263bcdb9771fc20b6123e34fbc48`,
  `85c1e4c1660e151526d54f9b1416917782f961b318091550bb3ef8042d16e253`, and
  `fbc95a25fc662ac9b3c32491a45ef40953a50643888759ee1d438529f00d682f`.
- Ruff format/check, targeted Pyright (`0 errors, 0 warnings, 0 informations`), strict OpenSpec,
  `git diff --check`, exact absent-target, focused secret, source-hash, and generated-cache gates
  pass. Two final targeted independent reviews report `0 Critical / 0 Important / 0 Minor`.
- No provider, runtime, database, index, source, accepted S2C2 artifact, Commit, Push, PR, archive, or
  Cutover changed. Task 2.8 and the OpenSpec ledger remain unchanged at 47/80.

## Rollback note

Delete the new RED test/contract and revert evidence. No runtime/data/index rollback is required.
