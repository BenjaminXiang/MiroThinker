# Slice Contract: s5f-review-history-acceptance

## Status

Accepted at `2026-07-12T15:04:36Z` against Accepted Task 5.5 commit `17b1269`. The generic S5
review/current-history seam and aggregate S5 acceptance are complete. The focused migration/safety
review and the single merged specification/code-quality review both ended with zero open Critical
or Important findings, and the complete commit-checkpoint gate passed. This acceptance does not
authorize S6 typed domain catalogs/projections, S7 release orchestration, S10 operator UI/gap
workflow, any durable-candidate write, or production-like cutover.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `5.6`
- Depends on: Accepted Task 5.5 at commit `17b1269`

## Lean execution

- This slice contract and OpenSpec Task 5.6 are the only implementation-plan sources.
- Implement one observable vertical RED/GREEN increment at a time and run only its nearest checks.
- Perform one merged specification/code-quality review for Task 5.6. Because C2_0007 changes a
  migration and canonical-write boundary, perform one additional focused migration/safety review.
- Run complete regression and frozen source/target safety checks only at the Task 5.6 commit
  checkpoint.

## Goal

Make every material unresolved field, relationship, or identity ambiguity visible and safely
reviewable without flattening evidence or mutating history. A human review must be an immutable,
evidence-bound offline build input that creates a new canonical decision and leaves the original
unresolved decision/verdict intact. Across release lineage, only the latest non-superseded,
as-of-valid decision head may appear in current projections; every prior, future, rejected,
unresolved, withdrawn, and replaced decision remains auditable.

At completion, S5 as a whole proves deterministic and recorded-fake LLM replay, retained competing
evidence, review queues, reversible identity decisions, proportional time, current/history
projection, durable restart, and query/answer write isolation through the two existing deep engines.

## Product-effect decisions frozen by this slice

- Every unresolved field/relationship decision with material conflicting evidence and every
  unresolved multi-source identity verdict produces exactly one immutable review case. This slice
  does not hide cases behind a high-impact gate; later operations may prioritize them without
  changing admission.
- An unresolved field/relationship decision with no admissible evidence remains retained but does
  not enter human review: a reviewer cannot establish a fact without evidence, so enrichment/gap
  handling remains S10 work.
- Review is complete only when reviewer identity, review policy/version, reviewed time, rationale,
  typed outcome, exact originating case/content hash, and exact evidence are retained. Reviewer
  authentication, signatures, assignment, locks, SLA, escalation, and multi-person approval are
  deferred operational concerns.
- Review never edits or deletes the originating case, assertion, decision, verdict, identity, or
  lineage. It produces a new `human_review` decision/verdict in a later offline build, bound to the
  original review case and decision/verdict.
- A replacement fact uses a new `selected`/`accepted` decision that supersedes the old head. A
  withdrawal without a replacement uses a new `superseded` decision with no selected evidence,
  role bindings, validity interval, or current projection. The old selected/accepted decision is
  never rewritten to `superseded`.
- Queue state is derived from immutable cases and later bound resolutions. No mutable
  `unreviewed/in_review` claim/lock workflow is introduced in S5.

## Non-goals

- Define review severity, high-impact scoring, prioritization, assignee, permissions, signatures,
  double approval, SLA, or Admin UI behavior.
- Carry unresolved work across partial/incomplete release builds; S7 owns complete candidate build
  composition and manifests.
- Implement typed Professor/Company/Paper/Patent fields, relationship types, inclusion, eligibility,
  or materialized current domain projections.
- Add online review, query-time canonical mutation, Web-to-canonical writes, publication, Milvus,
  query, answer, or knowledge-gap orchestration.
- Support arbitrary branching release graphs. The projection follows the single accepted
  `previous_release_id` lineage and rejects cycles, forks, cross-subject supersession, or duplicate
  heads.

## Allowed scope

- Deepen `CanonicalDecisionEngine.decide(request) -> result` and
  `CanonicalIdentityResolutionEngine.resolve(request) -> result` with typed immutable review cases
  and optional evidence-bound human-review resolutions; do not create a caller-orchestrated review
  decision builder.
- Add a generic read-only decision-history projection and deepen the existing explicit-target
  PostgreSQL store to reconstruct it across release lineage.
- Add C2_0007 only for durable human-review provenance required by the RED scenarios; keep review
  cases derived from immutable unresolved history rather than duplicating them in a mutable queue
  table.
- Freeze `superseded` shape and exact current-head semantics in shared contracts and engines.
- Repair the discovered raw-`AwareDatetime` sibling defect by using shared UTC-canonical datetime
  semantics in identity resolution and EvidenceLanding request/result hash seams; this is an
  explicit accepted-predecessor systemic repair, not unrelated S4 feature work.
- Focused pure and real-disposable PostgreSQL tests, this slice, OpenSpec task/change log, and
  verification evidence.

## Forbidden changes

- Original/recovery/durable-candidate database write, original Milvus open, live provider call,
  release/index mutation, or production-like cutover.
- Generic `DATABASE_URL` fallback, inferred target identity, weakened backup/append-only/rollback
  gates, or migration against anything except an explicitly marked owned disposable.
- Mutable review-case state, deletion/overwrite of prior decisions, reviewer authorization design,
  high-impact admission gates, or silent conflict resolution.
- A separate shallow review service that lets callers assemble canonical decisions or current
  projections outside the existing engines.
- S6+, legacy chat/query/admin/runtime changes, dependency additions, unrelated refactors, test
  weakening, or changing accepted threshold/corpus/ground-truth policy.

## Review contracts and invariants

- `ReviewCase` has a deterministic ID and content hash over family, release/run, subject/path,
  originating decision or verdict, exact candidate/conflicting evidence, policy/method, confidence,
  rationale/uncertainty, decision trace identity when present, and creation time.
- Reordering or exact replay produces byte-identical case IDs, case content, queue order, reviewed
  decisions, projections, and result hashes. Changed evidence, case bytes, family, subject/path,
  reviewer, review policy, outcome, or selected allocation changes the bound resolution/decision;
  cross-wired or tampered input fails before any write.
- Field review may select only strictly equal candidate values with one exact validity pair, or
  reject all candidates. Relationship review may accept only selected candidate evidence with
  explicit role bindings and one exact validity pair, or reject all candidates. Identity review
  must choose `same_entity` or `different_entities` and partition the exact component sources.
- A `human_review` decision/verdict requires its exact typed review resolution. Non-human methods
  cannot carry one. Structured-LLM trace and human-review resolution are distinct provenance.
- Query and answer modules cannot import or invoke decision/identity writers or review-resolution
  mutation paths.

## History and supersession invariants

- `supersedes_decision_id` is carried only by the new decision and must point to the prior head for
  the exact field or canonical relationship. Self, missing, cross-family, cross-subject/path, branch,
  cycle, and multiple-head lineage fail closed.
- `selected`/`accepted` heads may carry selected evidence and exact validity. `rejected` and
  `unresolved` heads carry no selected evidence/current projection. A `superseded` withdrawal carries
  no selected evidence, role bindings, validity, or current projection.
- History retains all decisions and assertions. Current contains only the unique lineage head whose
  state is `selected`/`accepted` and whose half-open interval contains the projection `as_of`.
  Future/ended heads remain history; prior heads never leak back into current when the latest head is
  unresolved, rejected, withdrawn, or out of validity.
- PostgreSQL reconstruction uses the exact `knowledge.release.previous_release_id` lineage and
  immutable decision records; restart/session timezone cannot change hashes or head selection.

## Vertical increments

1. **Review queue RED/GREEN:** add typed stable cases for material unresolved field, relationship,
   and identity outcomes; cover deterministic/recorded-fake replay, deduplication, no-case outcomes,
   and tamper/family/evidence mismatch.
2. **Human review RED/GREEN:** apply bound field, relationship, and identity resolutions through the
   existing engines; prove new human decisions, exact provenance, safe current effects, original
   history retention, and cross-wired/unsupported resolution rejection.
3. **History/supersession RED/GREEN:** freeze replacement versus withdrawal shape and derive one
   as-of-valid current head across ordered release lineage while retaining every historical state.
4. **C2_0007/restart RED/GREEN:** persist/load review provenance and lineage projection against a
   real disposable; prove append-only replay, migration preflight/downgrade refusal with retained
   review data, transaction rollback, and exact restart.
5. **UTC sibling RED/GREEN:** prove `+08:00`/`Asia/Shanghai` identity and EvidenceLanding replay hashes
   reconstruct identically through the shared `CanonicalDatetime` seam.

## Required checks

- Every new production behavior has an observed failing test before implementation.
- L1 uses only the nearest pure or PostgreSQL scenario for the active vertical increment.
- L2 covers Task 5.6 review/history/UTC siblings plus directly affected decision, identity, landing,
  store, and migration tests.
- The focused migration/safety review must have zero open Critical/Important findings before the
  merged Task 5.6 review begins.
- At the commit checkpoint: complete Canonical V2/S1/S2/S2B/S4/S5 regression required by the
  verification contract, C2_0001->C2_0007 upgrade/downgrade safety, Ruff, Pyright, wheel contents,
  strict OpenSpec, diff/secret/formal gate, source pause/hash/isolation, forced-read-only durable-
  candidate audit, and owned disposable cleanup pass.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`

## Stop conditions

- Correct behavior requires reviewer authentication/signatures/permissions, mutable claim/lock
  state, prioritization/SLA, dual approval, Admin UI, or incomplete-case migration between releases.
- Correct behavior requires typed S6 field/relationship semantics, public KnowledgeBuild/release
  orchestration, or a branching release graph.
- C2_0007 cannot preserve append-only history, exact rollback refusal, or restart reconstruction
  without rewriting an accepted historical migration.
- A command resolves to an original/recovery/durable-candidate/ambiguous target, or accepted source/
  backup-gate identity changes.

## Done means

- The three unresolved families expose exact, deterministic, durable review cases; admissible human
  resolutions create new evidence-bound decisions through the existing deep engines and cannot
  mutate prior history.
- Replacement, withdrawal, unresolved, rejected, future, ended, and accepted lineage scenarios
  derive exactly one valid current head and complete immutable history in memory and after a fresh
  PostgreSQL process.
- Identity merge/split/reversal remains exact, reviewed identity outcomes preserve source allocation,
  and all Canonical V2 hash-bearing datetime seams are UTC-canonical.
- The focused migration/safety review and the single merged Task 5.6 spec/code-quality review have
  zero open Critical/Important findings; checkpoint evidence is current; Task 5.6 is Accepted and
  committed alone; Task 6.1 implementation files are not mixed into this commit.
