# Slice Contract: s2c3b-claim-level-oracle-green

## Status

Accepted at `2026-07-14T18:27:07Z`. S2C3A is Accepted at 47/80; Task 2.8 remains unchecked. S2C3C
owns real human review/calibration and aggregate acceptance.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `2.8` (mechanical evaluator/recorded-fake GREEN increment only)
- Parent Slice: `s2c3-claim-level-oracle-review`
- Depends on: exact Accepted S2C2 artifacts and Accepted S2C3A RED

## Goal

Implement the one frozen run-local `evaluate_oracle_run(...)` deep seam so all five Accepted S2C3A
groups turn GREEN through deterministic artifact admission, atomic evaluation, recorded-fake judge
validation, and fail-closed human/calibration gating.

## Non-goals

- No real human review, live/model provider call, corpus eligibility mutation, mixed non-empty
  exclusion package, Task 2.8 completion, aggregate S2C acceptance, S8/S9 execution, runtime/product
  integration, database/index write, or threshold/design expansion.

## Allowed scope

- Add only
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/claim_level_oracle_evaluation.py` for the
  GREEN implementation, plus this Slice/evidence state.
- Preserve exactly one public seam in `__all__`:
  `evaluate_oracle_run(manifest_path, run_input, *, judge_adapter=None)`.
- The Accepted RED may change only if it contains an independently proven contradiction or fixture
  defect; no weakening, xfail broadening, group removal, or acceptance shortcut is allowed.

## Forbidden changes

- Accepted S2C2 artifacts/schema/builder/tests, S2C3A semantics, historical S2, reference prose
  truth, human labels, live providers, runtime/package code, databases, indexes, S8/S9, Task 2.8, or
  aggregate acceptance checkboxes.

## Required behavior

- Validate exact manifest/file/output/row/content/cross-reference identities before evaluation or
  judge invocation; emit the frozen artifact identity and current corpus summary.
- Derive every hard outcome in contract order from structured observations, localize failed or
  unresolved stages, and refuse caller-supplied hard results/private execution semantics.
- Invoke the injected recorded judge only for a structurally non-exact required claim; send only its
  exact contract, candidate, `as_of`, policy, and named snapshot records. Strictly validate and hash
  the response; any timeout, extra/memory, or identity mismatch becomes unresolved without erasing
  deterministic outcomes.
- Admit the one-case synthetic acceptance reachability fixture only when exact eligible selection,
  human review, family/hard-ID/snapshot binding, judge calibration, and all hard outcomes pass. Emit
  a content-addressed acceptance record binding artifact/review/calibration/outcome/reviewer/
  exclusion identities. Current zero-eligible artifacts remain not ready.

## Required checks

- Accepted S2C3A target changes from exact five xfails to exactly five passes with no skip/xfail.
- Combined S2C2/S2C3 is `16 passed`; historical S2 remains `20 passed`; deterministic builder
  `--check` stays byte-identical.
- Ruff format/check, targeted Pyright, strict OpenSpec, diff/source/scope/secret/cache checks.
- Independent implementation/spec review with zero open Critical/Important findings.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- This Slice and parent status; `change-log.md`, `agent-links.md`, and `.agents/portfolio.md`.
- Task 2.8 and the 47/80 ledger remain unchanged.

## Stop conditions

- GREEN needs reference prose, model memory, a live provider, invented human approval, threshold
  lowering, Accepted artifact mutation, or an interface beyond the frozen deep seam.
- The Accepted RED is internally contradictory or cannot turn GREEN without weakening a hard gate.

## Done means

- The exact five groups are GREEN through the one target module; regression/static/source/review
  gates pass with zero Critical/Important findings. S2C3B is Accepted while S2C3C/Task 2.8 remains
  pending real human review/calibration and aggregate acceptance.

## Acceptance evidence

- The one run-local target exposes only `evaluate_oracle_run(...)`. Final implementation SHA-256 is
  `63c33ef3832855a6a02bf0cc03d1036e7c919c5c4fdd4bf166328b7822e626fd`; final test SHA-256 is
  `0235c3306412acd96aad28177fb4f52745486b831f213a4b57707bbdec9cc3e9`; this contract's
  pre-acceptance SHA-256 is `57068a163989b9f5685261d99b4edab95af7dc7a88d74fec7f1c09e7ab5d852a`.
- The exact five owner groups are GREEN (`5 passed`); combined S2C is `16 passed`; historical S2 is
  `20 passed`. Deleting the target under one bounded recovery check restores exactly `5 xfailed`
  and forced execution restores exactly five direct missing-target failures, after which the target
  returned byte-identical.
- A mechanical RED-marker contradiction was corrected without changing assertions: each strict
  xfail now applies only while the exact target is absent, so Accepted RED remains recoverable and
  real GREEN is not misclassified as XPASS.
- Admission content-binds manifest/output/row/schema/source identities and refuses coherent account,
  contract, snapshot, source-corpus, review/family/eligibility cross-wires before judge invocation.
  Atomic outcomes use canonical JSON typing, contract order, complete stage localization, allowed
  variants, and semantic forbidden-claim matching independent of caller IDs/evidence labels.
- Recorded judge requests contain only exact structured inputs/named evidence. Malformed, mutated,
  unbound, memory-bearing, or failed responses degrade only the judged requirement to unresolved.
  The returned result and acceptance identities are deeply immutable and canonically hashed.
- Only an exact one-case synthetic fixture can demonstrate acceptance-gate reachability; no real
  corpus can be accepted in S2C3B. Exact human/calibration identities and every eligible case remain
  required. S2C3C owns real provenance, mixed exclusions, and Task 2.8.
- Deterministic builder `--check`, Ruff format/check, targeted Pyright (`0 errors, 0 warnings, 0
  informations`), strict OpenSpec, `git diff --check`, source-hash, focused secret, and cache gates
  pass. Two independent final reviews report zero Critical/Important findings.
- Three Minor/YAGNI notes are recorded and nonblocking: synthetic review/calibration provenance is
  self-declared by design until S2C3C; `failure_stage` selects the first non-pass in hard-ID order
  while complete stage outcomes remain available; calibration agreement is not capped above 1.0.
- Accepted S2C2 artifacts remain byte-identical. No runtime/provider/database/index/source state,
  Commit, Push, PR, archive, or Cutover changed; Task 2.8 and the ledger remain 47/80.

## Rollback note

Delete the one evaluator module and revert S2C3B evidence; Accepted S2C2/S2C3A bytes and all external
state remain unchanged.
