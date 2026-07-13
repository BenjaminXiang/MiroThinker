# Canonical V2 Code-Grounded Mainline Plan — 2026-07-13

## Execution status

Completed through the selected Aggregate S6 checkpoint at `2026-07-13T14:48:01Z`.

- Task 5.7/S5G and Tasks 6.1-6.8 are Accepted at 36/75 OpenSpec tasks.
- Accepted implementation commits now cover temporal precision, typed domain projection,
  relationship RED/GREEN/persistence, catalog source rebind, and path eligibility through
  `9b300222338e24e8faac661cf7154ef7f7fb19b8`; the Aggregate S6 acceptance commit is the commit that
  contains this execution record.
- Full corrected real-PostgreSQL evidence is 348 passed with only four expected future-public-module
  xfails; no-external evidence is 211 passed, 137 skipped, and the same four xfails.
- All Canonical V2 side patches are accounted for. The Task 6.1 preparation-only untracked artifacts
  remain intentionally untouched and abandoned in their owner worktree.
- The separate `mainline-promotion-gate.md` is Ready. S7-S12, product/data/index cutover, push, PR,
  and OpenSpec archive remain unstarted/forbidden.

The sections below preserve the code-grounded pre-execution snapshot and the order that was
followed. Where their Task 6.3-in-progress wording conflicts with this status, this execution status
and the current `verification.md` are authoritative.

## Task contract

- Goal: move the implementation mainline to the existing Canonical V2 code line without erasing
  accepted evidence, mixing incomplete slices, or replaying stale root-worktree planning.
- Expected invariant: only Accepted predecessors may be dependencies; original PostgreSQL/Milvus
  remain frozen; all writes stay on explicit disposable or isolated-candidate targets.
- Context: the root worktree is at legacy commit `c0f3db2`, while the Canonical V2 integration
  worktree contains 27 later V2 commits plus an active uncommitted Task 6.3 implementation.
- Constraints: do not merge, rebase, archive, commit, or mutate databases/indexes as part of this
  planning audit; preserve every dirty worktree.
- Done when: the actual code state, module seams, current failures, branch topology, and next
  independently reviewable slices are explicit.
- Out of scope: implementing or repairing Task 6.3, executing real-Postgres suites, moving Git
  `main`, or starting S7-S12.

## Evidence-based current state

- Git `main` (`191ed923`) is an ancestor of `canonical-v2-s2-baseline` (`ef3cd2f`); the V2 line is
  142 commits ahead and can eventually fast-forward without a history merge.
- `feat/professor-retrievability` (`c0f3db2`) is also an ancestor; the V2 line is 27 commits ahead.
- OpenSpec on the V2 integration worktree reports **30/74 tasks complete**, not the stale root
  worktree's 5/73.
- Accepted evidence covers S1, S2 including backup/restore, S3, S4, S5, Task 6.1, Task 6.2 RED, and
  Task 6.6 RED.
- Task 6.3 is In Progress in the integration worktree. It contains an uncommitted typed-domain
  projection Module, inclusion Module, packaged catalog, PostgreSQL Adapter, `C2_0008`, and focused
  tests.
- The relationship RED contract exists separately on `codex/canonical-v2-s6d-red`; it is not yet in
  the integration line. A separate path-eligibility RED branch also exists, while the integration
  line contains its own non-patch-equivalent Task 6.6 checkpoint.
- S7-S12 have not started. KnowledgeBuild, KnowledgeRead, KnowledgeAnswer, ReleasePublication, and
  path eligibility remain strict expected REDs.

## Module and seam audit

| Module | Interface / seam | State | Planning consequence |
|---|---|---|---|
| EvidenceLanding | `ingest`, artifact registration, replay through ephemeral/Postgres Adapters | Accepted through S4 | Reuse as the landing seam; no replacement layer. |
| CanonicalDecision | batch decision plus immutable history; ephemeral/Postgres Adapters | Accepted through S5 | Package-internal build seam; S6 consumes it without widening the external interface. |
| CanonicalIdentityResolution | offline resolution/review/history; ephemeral/Postgres Adapters | Accepted through S5 | Keep query/answer read-only; no query-time canonical writes. |
| DomainInclusion | one batch `evaluate` interface with four internal policies | GREEN in active S6c work | Finish and review inside Task 6.3. |
| DomainProjection | one `project` interface plus PostgreSQL Adapter | In Progress | Current implementation owner; no S6d/S6f implementation may be mixed into it. |
| KnowledgeBuild | one candidate-build interface | Expected RED | S7 owner after aggregate S6 acceptance. |
| ReleasePublication | verify/promote/rollback | Expected RED | S7 owner; promotion remains separately authorized. |
| KnowledgeRead | one retrieval-plan execution interface | Expected RED | S8 owner after accepted release substrate. |
| KnowledgeAnswer | one turn-answer interface | Expected RED | S9 owner after KnowledgeRead acceptance. |

The five public deep modules remain the intended external seams. Decision, identity, inclusion, and
projection are internal build modules; they should not become extra consumer-facing interfaces.
Production and deterministic/test Adapters make the external-provider or persistence seams real.

## Current verification truth

Read-only/no-external-database Canonical V2 suite on the active integration worktree:

```text
178 passed, 118 skipped, 9 xfailed, 2 failed
```

Expected REDs:

- 4 public modules: KnowledgeBuild, KnowledgeRead, KnowledgeAnswer, ReleasePublication.
- 5 path-eligibility scenarios owned by Task 6.7.

Actual Task 6.3 failures:

1. A historical S5 test asserts `C2_0007` is the permanent Alembic head. The active Task 6.3
   migration correctly introduces descendant `C2_0008`, exposing a test coupled to an internal
   implementation checkpoint instead of the accepted minimum-revision interface.
2. Professor `affiliation_history` carries date-only validity while S5 assertion/current-selection
   contracts carry timezone-aware instants. ADR-012 now requires preservation of both precision
   kinds; Task 5.7/S5G owns the shared-contract correction before S6c resumes.

Real-Postgres Task 6.3 checks were not run in this audit because their four explicit target settings
were not provided. The 118 skips therefore are not current GREEN evidence.

## Revised implementation order

### Checkpoint 0 — protect and name the integration line

1. Treat `canonical-v2-s2-baseline` as the current V2 integration line despite its stale name.
2. Preserve the active Task 6.3 dirty worktree; do not fast-forward Git `main` or move root-worktree
   changes into it while tests are red.
3. Keep a durable V2 integration branch through aggregate S6. After Tasks 5.7 and 6.1-6.8 are
   Accepted, run the recorded mainline-promotion preflight and fast-forward Git `main` only if it
   remains a strict ancestor and every worktree/side-branch change is accounted for.
4. Reconcile root portfolio/ledger/OpenSpec copies from the accepted integration line, not the other
   way around.

### Checkpoint 1 — finish Task 6.3 only

1. Complete and accept Task 5.7/S5G precision-preserving temporal contracts; do not modify S6c
   around the shared-interface defect.
2. Replace exact-head coupling in prior-slice tests with the already implemented linear-history /
   minimum-revision contract while retaining exact tests for the migration that owns each revision.
3. Finish the four-domain typed projections, all 28 subobjects, packaged catalog parity, and exact
   assertion/decision lineage.
4. Run focused pure tests, then explicit disposable-Postgres `C2_0008` upgrade/downgrade/restart,
   direct-SQL, idempotency/conflict/concurrency checks.
5. Run merged specification/code-quality review plus migration/write-safety review. Only then mark
   Task 6.3 Candidate/Accepted and checkpoint it independently.

### Checkpoint 2 — finish aggregate S6

1. Integrate and re-review the Task 6.4 relationship RED contract against the Accepted Task 6.3
   interface; do not assume the side branch is automatically compatible.
2. Implement Task 6.5 typed relationship projection and persistence as a separate slice.
3. Implement Task 6.7 path eligibility against Accepted domain and relationship projections using
   the existing Task 6.6 RED cases.
4. Run Task 6.8 bounded-candidate coverage, cross-domain sibling invariants, review, and aggregate S6
   acceptance.

### Checkpoint 3 — map frozen legacy obligations before S7

The previously selected “old contract mapping before baseline” policy is retained, but cannot be
inserted retroactively before already Accepted S2-S5. Instead, make it a governance gate before S7:

- map frozen retrieval/index/parity obligations to S7;
- map A-G routing, hybrid retrieval, Universal Web, Type1-Type4, and multi-turn traversal to S8;
- map evidence/citation/synthesis/outcome/timeout obligations to S9;
- map feedback, review, gap, and operational obligations to S10;
- map legacy HTTP/admin/UI compatibility and removal obligations to S11;
- map reusable evaluators, manifests, corpora, and RED cases to the owning verification gates;
- classify each old implementation detail as reuse candidate, evidence only, superseded, or
  incompatible; no old in-flight change becomes an Accepted dependency.

### Checkpoint 4 — continue the accepted V2 chain

1. S7 KnowledgeBuild, candidate release, versioned PostgreSQL projections/Milvus indexes, exact
   parity, publication verification, and rollback.
2. S8 KnowledgeRead with protected slots, typed planning, exact/structured/lexical/vector/relation/
   Web lanes, fusion, rerank, sufficiency retry, traceability, latency, and cost gates.
3. S9 KnowledgeAnswer and release-aware sessions with material claim/evidence mapping and grounded
   progressive traversal.
4. S10 knowledge-gap and review operations.
5. S11 consumer migration and V042 quarantine/removal.
6. S12 complete isolated candidate acceptance; production-like cutover remains separately
   authorized.

## Reuse rule

Reuse is contract-first, not file-first. Existing V1 code may be retained only when it can satisfy a
V2 Module's interface and invariants through focused tests without importing V042 table shapes,
global readiness, fixed collection names, direct active-index mutation, or query-time canonical
writes. Otherwise retain it only as evidence/reference and replace the implementation behind the V2
seam.

## Rollback / checkpoint

- No branch or database state changes are authorized by this plan.
- The safe code checkpoint is `ef3cd2f` plus the separately visible side-branch commits.
- The active Task 6.3 working tree is not an accepted checkpoint and must be preserved until its
  owner either completes it or explicitly abandons it.
- Git `main` remains untouched until the integration-line decision and a green accepted checkpoint.
- The selected promotion checkpoint is aggregate S6 Accepted; S5G/S6c acceptance alone is
  insufficient.

## Immediate blocking decision

ADR-012 resolves the representation direction and `explicit-calendar-v1` resolves cross-precision
comparison. S5G is Ready; S6c stays stopped until S5G is Accepted.
