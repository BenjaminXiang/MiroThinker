# Plan: Task 5.1 Assertion Decision RED

## Task contract

- Goal: freeze executable RED behavior for retained competing field/relationship assertions,
  deterministic constraint ordering, structured LLM adjudication, unresolved conflicts, and generic
  current selections before implementing the decision core.
- Expected behavior / invariant: one package-internal deep module accepts a versioned offline
  decision batch and returns retained assertions, auditable decisions, constraint outcomes, and
  generic current selections; unsupported ambiguity never becomes a current fact.
- Context: OpenSpec task 5.1 after complete S4 acceptance at commit `cf9691d` and immutable landing
  checkpoint `4ae5f2ce…b05012`.
- Constraints: test/docs only; no production module, shared-contract edit, migration, database,
  source, Milvus, provider call, candidate release, or typed-domain projection.
- Done when: focused normal pytest reports exactly five strict xfails; forced RED reports exactly
  five missing-module failures with no collection/setup failure; existing Canonical V2/S1/S2/S2B,
  static, OpenSpec, and source-safety checks remain green; task 5.1 is Accepted and committed alone.
- Out of scope: Task 5.2 implementation/persistence, identity merge/split, full temporal policy,
  review/reversal, typed domain/relationship catalogs, `KnowledgeBuild`, publication, and retrieval.

## Approved RED design

- Add the package-internal deep module seam
  `CanonicalDecisionEngine.decide(DecisionBatchRequest) -> DecisionBatchResult`. The future public
  `KnowledgeBuild.build` hides this module; Task 5.1 does not awaken the Task 7.2 interface.
- Exercise a future concrete ephemeral composition. Only the true-external structured-LLM port may
  use a recorded fake; tests must not fabricate decision-engine results or inspect SQL/repository
  calls.
- A decision batch carries release/run/as-of context, already-resolved source/canonical identities,
  versioned policies, and field/relationship assertion groups. Identity construction remains Task
  5.3–5.4.
- The result carries every retained assertion, deterministic constraint outcomes, release-scoped
  field/relationship batch decisions, unresolved conflicts, and generic current selections.
  Generic selections are not S6 typed domain projections or S7 published projections.
- Deterministic candidate constraints cover only stable build invariants in this RED contract:
  canonical identity membership, active source identity, matching entity/field, and evidence not
  observed after build-as-of. Full validity/history policy remains Task 5.5.
- Keep five independent cases so partial implementations cannot hide a failed invariant behind one
  aggregate scenario.

## Task 5.2 GREEN handoff

The RED scenarios deliberately expose four foundation mismatches that Task 5.2 must reconcile under
the already-approved release-scoped, reproducible-decision requirements:

- add release scope to the shared field-decision value, matching the existing release-scoped
  PostgreSQL decision key;
- add `relationship_type_version` to shared relationship assertion/decision values, matching the
  existing PostgreSQL columns;
- retain canonical raw output bytes or equivalent artifact identity, verify their SHA-256, and bind
  the schema-validated structured LLM output to that content in typed and persisted traces;
- enforce disjoint selected/conflicting assertion roles in shared validation and durable storage.

These are Task 5.2 typed-contract/persistence repairs, not Task 5.1 production edits or a new product
choice. If GREEN needs a different observable shape, stop and revise this approved RED contract
rather than hiding the mismatch in an adapter.

## Alternatives considered

1. Extend `CandidateRelease` with assertion history/current facts: rejected because it leaks a large
   diagnostic surface into the Task 7 release summary and prematurely couples S5 to S7.
2. Add CRUD/inspection methods to `KnowledgeBuild`: rejected because it makes the public module
   shallow and starts Task 7.2 before its predecessors.
3. Use direct C2_0004 SQL assertions: rejected because Task 5.1 is RED-only, leaks storage, and could
   prove table shape without proving decision behavior.
4. Package-internal one-method decision module with a recorded LLM adapter: selected for leverage,
   locality, and later composition behind `KnowledgeBuild`.

## Implementation slices

- [x] Add five strict RED scenarios for retained/current field selection, deterministic constraint
      ordering, structured LLM trace/replay, unresolved no-projection behavior, and retained/current
      relationship selection.
- [x] Run normal focused pytest and prove exactly five strict xfails.
- [x] Run focused `--runxfail` and prove exactly five `ModuleNotFoundError` failures for the absent
      decision module, not syntax, fixture, assertion, or collection errors.
- [x] Run Canonical V2 no-DB regression, S1/S2/S2B, Ruff, Pyright, strict OpenSpec, diff/secret, and
      final read-only source/candidate invariants.
- [x] Record evidence, mark task 5.1 Accepted, stage only this task, and make one task-level commit.
      Do not start task 5.2 in the same commit.

## Invariants

- Every supplied assertion remains visible even when deterministically excluded or not selected.
- Deterministic rejects never enter the recorded LLM evidence set.
- Selected and conflicting assertion roles are disjoint and evidence-bound.
- Structured LLM decisions retain provider/model/prompt/schema/output identity and validated output;
  raw-output hash mismatch is rejected and model memory is never evidence.
- Unresolved field/relationship decisions do not create generic current selections.
- Same versioned logical batch is order-independent and replay-stable.
- Original `pgtest` stays paused; original Milvus remains unopened and hash-only.
- The candidate remains C2_0004 with the accepted S4 landing state and zero non-landing business
  rows; S4 checkpoint evidence remains immutable.

## Rollback note

- Revert the Task 5.1 test/docs commit. No runtime, schema, database, source, provider, or index state
  needs rollback.
