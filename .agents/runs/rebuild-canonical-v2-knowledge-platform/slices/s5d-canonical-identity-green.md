# Slice Contract: s5d-canonical-identity-green

## Status

Accepted at `2026-07-12T08:40:35Z`. This slice implements OpenSpec Task 5.4 against Accepted Task
5.3 commit `b14e33c`. It does not authorize Task 5.5 temporal policy, Task 5.6 aggregate S5
acceptance, or any durable-candidate/source/index write.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `5.4`
- Depends on: Accepted Task 5.3 at commit `b14e33c`

## Lean execution

- This slice contract and OpenSpec Task 5.4 are the only implementation-plan sources.
- Implement one observable vertical RED/GREEN increment at a time and run only its nearest checks.
- Perform one combined specification/code-quality review for Task 5.4. Because this task adds a
  migration and write adapter, perform one additional focused migration/database-safety review.
- Run complete regression, source isolation, backup gate, real-disposable lifecycle, and safety
  verification only at the Task 5.4 commit checkpoint.

## Goal

Build a reproducible offline canonical identity module and durable source-identity mapping so each
real-world object has one unambiguous current owner, mistaken merges can be reversed without erasing
history, recovered source IDs remain traceable, and downstream facts/relationships cannot silently
attach to the wrong object. One request/result is a complete release build input/projection, not one
pair: normalization, policy-versioned candidate recall/composite matching, deterministic rules, and
recorded structured adjudication must resolve every recalled component across all four domains while
leaving unrelated source identities as independently owned objects.

## Non-goals

- Implement general event/publication/validity intervals (Task 5.5).
- Implement human-review queues or aggregate current/history acceptance (Task 5.6), except typed
  unresolved output needed for safe engine degradation.
- Build typed Professor/Company/Paper/Patent projections, Paper verification status, relationship
  catalogs, inclusion/eligibility, publication, Milvus, query, answer, or Web behavior.
- Preserve V042/pre-launch canonical IDs or mutate identity from query/answer paths.
- Call a live LLM/provider or write the accepted durable candidate.

## Allowed scope

- One package-internal `canonical_identity_resolution` deep module satisfying the Accepted Task 5.3
  interface through retained shared contracts plus narrowly scoped result/manifest/assignment types.
- Content-bound recorded structured-LLM adapter and deterministic policy implementation for the
  approved strong-ID, candidate-separation, merge/link/reverse, and unresolved effects.
- Focused pure contract/negative tests extending the Accepted Task 5.3 test module.
- One forward Alembic revision after C2_0005 plus an explicit-target offline PostgreSQL adapter and
  real-disposable tests for identity decisions, evidence, lifecycle, assignments, replay, and
  rollback.
- Minimal shared contract/storage-helper reconciliation proven necessary by Task 5.3.
- This slice, OpenSpec task/change log, and verification evidence.

## Forbidden changes

- Original/recovery/durable-candidate database write, original Milvus client, source replay, live
  provider call, active release/index pointer mutation, or production-like cutover.
- Generic `DATABASE_URL` fallback, implicit database identity, non-disposable identity writer, or
  any write before exact Accepted S2B admission and target verification.
- Historical migration rewrite, inferred/backfilled identity context, weakening append-only or
  downgrade safety, or a mutable overwrite presented as reversal history.
- Legacy chat/query/admin/runtime/API changes, including direct online use of the identity writer.
- Treating `different_entities` as terminal `reject`, mixing terminal history with current owners,
  or using decision-wide membership as a heuristic split allocation.
- Task 5.5/5.6, S6+, unrelated refactors, dependency additions, or test weakening.

## Expected unchanged behavior

- Accepted S1-S4 and Tasks 5.1-5.3 remain GREEN/strict RED as specified.
- Task 5.2 field/relationship decisions continue to operate at C2_0005 and known compatible linear
  descendants.
- The four Task 3.1 future deep modules remain strict RED.
- Durable candidate remains C2_0004 with exact landing state and zero non-landing rows.

## Vertical increments

1. **Pure release-batch identity engine:** turn all five Accepted Task 5.3 scenarios GREEN, then prove
   one deterministically ordered request can normalize and recall several independent, multi-source,
   multi-domain components. Apply policy-versioned strong/composite/recorded-LLM decisions, stable
   already-resolved no-ops, merge/create/link/reverse topology, generation-safe successor IDs,
   unique current ownership, terminal history, output-specific assignments, retained evidence, and
   request-bound verdict/decision/output hashes.
2. **Integrity negatives and safe degradation:** add RED/GREEN coverage for incomplete/cross-wired
   mappings, evidence/trace/hash tampering (including rehashed decision/action/output changes),
   contradictory structured-LLM groups, below-policy auto-action confidence, entity-type or terminal-
   state hard conflicts, unknown lineage, and unresolved ambiguity without canonical flattening or
   terminal rejection. Candidate verdicts and applied decisions use an explicit evidence-bound link;
   pair-wide adjudication evidence is not relabeled as source-local decision evidence.
3. **C2_0006 and offline PostgreSQL store:** add RED then implement append-only identity run/context,
   exact prior/new decision-time context, assertion source/record evidence, complete decision
   topology, per-output allocation, canonical membership/lineage, unique current assignments, exact
   source/assertion conflict comparison, persist/load/restart/replay, and atomic rollback. Deferred
   database invariants enforce exact context/evidence sets, action shape, source partition, active
   membership/assignment equality, result-run attachment, and lineage/state consistency.
4. **Offline-only enforcement:** prove the writer requires explicit offline build authority, Accepted
   backup evidence, a verified disposable target, and the minimum known revision before its first
   write; query/answer packages cannot use it as an online mutation path.

## Migration and persistence invariants

- C2_0006 must fail closed if pre-existing identity decision/canonical history cannot receive an
  exact decision-time context; no inferred context or placeholder allocation is allowed.
- Every applied identity decision has exact release/run/policy/method/evidence/input-content
  identity, an explicit optional candidate-verdict link, complete input/output/source topology, and
  one immutable decision-time context. Supplied prior decisions require their exact retained context;
  the store never infers or invents it from current state.
- Every decision output has explicit source allocation; every current source identity has exactly
  one active canonical owner. Historical memberships may overlap only in the separate terminal
  history graph.
- Canonical source membership, predecessor/successor lineage, candidate verdicts, manifests, and
  assignments are append-only or immutable within an accepted candidate release.
- Exact replay is idempotent; changed content under the same run conflicts; load revalidates all
  hashes and relational projections against the immutable context.
- Upgrade/downgrade preflight and destructive steps take the required locks so concurrent inserts
  cannot bypass populated-history refusal. Upgrade, downgrade, and the writer use one compatible
  parent-to-child order; downgrade refuses nonempty Task 5.4 history without a deadlock victim.

## Required checks

- Each new production behavior has an observed failing test before implementation.
- Accepted Task 5.3 forced RED is observed before the pure module exists; after GREEN, all five run
  normally with zero xfail/skip and the exact-target sentinel cannot hide nested failures.
- Focused pure tests cover all five scenarios plus integrity/degradation siblings.
- A fresh network-none/no-port/tmpfs disposable proves C2_0006 upgrade/downgrade/re-upgrade,
  nonempty preflight refusal, constraint/trigger integrity, exact restart readback, idempotency,
  conflict, concurrent/late rollback, and owned cleanup. No durable candidate is upgraded.
- At the commit checkpoint: complete Canonical V2/S1/S2/S2B/S4, Ruff, Pyright, wheel contents,
  strict OpenSpec, diff/secret, formal gate, source hash/pause/isolation, candidate read-only, and
  disposable cleanup/volume-set checks pass.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`

## Stop conditions

- A correct identity effect requires a product choice absent from approved OpenSpec/Accepted RED.
- The deep module cannot keep candidate verdict, applied decision, current assignment, and terminal
  history distinct without changing the approved user effect.
- A migration/store cannot be atomic, append-only, content-bound, exact-replayable, reversible, and
  safe on a proven disposable within the allowed scope.
- Any command resolves to an original/recovery/durable-candidate/ambiguous target, or source/gate
  identity changes unexpectedly.
- Task 5.5+, live provider, domain projection, publication, query, answer, or legacy runtime work is
  required to make the focused Task 5.4 checks pass.

## Done means

- Five Accepted identity scenarios plus a complete multi-component/multi-domain release batch,
  normalization/composite recall, lifecycle round-trip, stable no-op, LLM threshold, and integrity
  siblings are GREEN through one deep module.
- A fresh process can persist and load the exact typed identity result with complete evidence,
  topology, lifecycle, and source assignments; all invalid/replayed/concurrent mutations fail
  closed without partial rows.
- The writer is offline-only and explicit-disposable-only; original sources and durable candidate
  remain unchanged.
- Both required reviews have zero open Critical/Important findings, checkpoint evidence is current,
  Task 5.4 is Accepted and committed alone, and Task 5.5 has not started in the same commit.

## Acceptance checkpoint

- The five Accepted scenarios and integrity siblings are GREEN through one complete-release deep
  module; focused pure, PostgreSQL, decision-compatibility, and head-inventory verification is
  `75 passed`.
- Real S5D integration excluding the separately named S4C target is `193 passed, 4 approved xfails`;
  S4C landing compatibility is `10 passed`. Explicit no-database Canonical V2 is `124 passed, 79
  explicit integration skips, 4 approved xfails`.
- S1 target/gate safety is `17 passed`; S2/S2B is `32 passed`; S4E checkpoint is `23 passed`. Ruff,
  Pyright, wheel contents through C2_0006, strict OpenSpec, formal gate, diff, and secret checks pass.
- The merged review's one Critical and five Important findings and the focused migration review's
  five Important findings are closed; its one Minor maintainability note is also addressed. No
  second merged review was added under lean execution.
- Accepted S2B remains `accepted/50`. Original Postgres is paused on its exact volume; original and
  restored Milvus and FPI-salvage hashes match. The durable candidate remains forced-read-only at
  C2_0004 with landing counts `15/6/6/21/6` and zero knowledge/publish rows.
- The owned container `ef1768e1…c6b501`, its two empty base databases, host socket, and wheel-check
  directory were removed. Docker volume-set SHA-256 remains `8314a2b0…ec896c`.
