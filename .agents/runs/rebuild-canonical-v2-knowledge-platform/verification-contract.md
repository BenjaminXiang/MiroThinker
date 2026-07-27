# Verification Contract: rebuild-canonical-v2-knowledge-platform

## Change

- Change ID: `rebuild-canonical-v2-knowledge-platform`
- OpenSpec path: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Run workspace: `.agents/runs/rebuild-canonical-v2-knowledge-platform/`

## Change Type

- `data_contract_or_storage`

## Superpowers Mode

- `lean_vertical`

## Current final-milestone contract (2026-07-26)

This section supersedes conflicting verification requirements below for open Tasks 2.8, 8.1, 8.8,
9.8, and 12.2-12.6. The detailed historical sections remain evidence for already Accepted work; they
do not add gates to the remaining milestone.

### Goal

Serve a source-grounded isolated Candidate over the real chat API/UI with non-zero Professor,
Company, Paper, and Patent populations, the customer-required relationship paths, and semantic
alignment with all 17 conversations/25 turns in `docs/测试集答案.xlsx`.

### Normative oracle

- Each workbook query, answer, and key-point row is interpreted together as case-specific Ground
  Truth. Explicit key-point corrections override inaccurate historical answer fragments.
- Alignment is semantic, not lexical. Newer official evidence is allowed only with source/as-of
  disclosure. Missing evidence is a product gap, not an exclusion decision.
- Automated or LLM comparison is advisory. The user owns final acceptance through the running chat
  system.

### Required checks

1. Changed-module tests for the code actually modified.
2. One Candidate smoke proving four non-zero public-domain populations, required relationship reach,
   serving-bundle identity, lookup/vector parity, original-source isolation, and unchanged active
   pointers.
3. Approximately eight representative real-chat cases during development.
4. One final real-runtime replay of all 17 workbook conversations/25 turns, producing a readable
   Ground Truth/actual-answer/source/limitation report.
5. Focused Ruff and Pyright for changed Python files, strict OpenSpec validation, and
   `git diff --check`.

### Explicitly retired checks

- Task 2.8 contract review, exclusion review, blind calibration, human-label quotas, LLM-judge
  agreement, and review-workbench acceptance.
- Separate Tasks 8.1, 8.8, and 9.8 aggregate claim-level gates.
- Independent review for each remaining task, repeated complete test-suite runs, and duplicate
  evidence-envelope production without a concrete regression or safety reason.

### Unchanged safety boundary

The original PostgreSQL remains paused, original Milvus remains unopened, original sources remain
read-only, Candidate targets remain explicit and isolated, active release pointers remain unchanged,
and production-like cutover or cleanup requires separate user authorization.

## RED Artifact

- Type: contract test and PostgreSQL integration test
- Path: `apps/miroflow-agent/tests/canonical_v2/test_canonical_identity_resolution_contract.py` and `apps/miroflow-agent/tests/canonical_v2/test_canonical_identity_postgres.py`
- Expected failing reason: the Accepted Task 5.3 deep module was absent, then Task 5.4 storage and cross-row release invariants were absent
- Behavior class covered: offline multi-domain identity resolution, reversible lifecycle topology, exact evidence binding, append-only persistence, replay, and rollback safety

## Oracle Strength

- Observable behavior checked: exact typed request/result equality, mutation-sensitive hashes, source-to-output partitions, lifecycle lineage, restart load, invalid-row rejection, idempotency, concurrency, and reversible migration behavior
- Why this is stronger than a single string, DOM node, snapshot, or visible example: the tests exercise complete multi-component releases and database transactions across create, link, merge, split, reverse, reject, unresolved, and no-op outcomes
- For web/UI changes, browser/API/state workflow to verify: not applicable to this offline Task 5.4 storage slice; query and answer paths remain unchanged and read-only
- For LLM/agentic changes, scenario/eval/trace contract to verify: recorded structured-LLM verdicts bind exact raw bytes, validated content, evidence IDs, model/prompt/schema versions, and confidence thresholds without a live provider call

## Diagnosis / Anti-Overfit Check

- Root-cause hypothesis: the Accepted pair-only RED seam and C2_0005 identity tables could not represent release batches, decision-time context, output-specific source allocation, or exact reversible lifecycle replay
- Sibling patterns searched: all identity actions and entity domains, decision/source/assertion tables, current and terminal ownership, structured-LLM trace families, migration preflight/downgrade locks, replay conflicts, and query/runtime writer imports
- Why this RED covers a behavior class rather than one visible example: the matrix crosses four domains, multiple components, every lifecycle action, deterministic and recorded-LLM paths, tampering, replay, and concurrent migration/store boundaries
- Why the implementation cannot pass by hardcoding or bypassing the case: IDs and hashes are recomputed from complete canonical content, relational projections must round-trip to the same typed result, and deferred database validators reject incomplete topology independently of Python

## Context / Dependency Surface

- Source OpenSpec requirement(s): Task 5.4 and the approved canonical identity, trusted data, immutable landing, backup, and operational-safety requirements under `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/`
- Legacy/source-of-truth docs consulted: `docs/Data-Agent-Shared-Spec.md`, the four-domain PRDs, and the accepted Canonical V2 outcome requirements in this run workspace
- Affected modules: canonical identity resolution, explicit-disposable PostgreSQL persistence, C2_0006, C2_0005 decision-store compatibility, and their contract/integration tests
- Existing tests/evals likely affected: Canonical V2 shared storage, decision persistence, landing compatibility, database target safety, S2/S2B backup admission, and S4 checkpoint tests
- Regression surface: migration upgrade/downgrade, append-only evidence and identity history, exact replay/load, current ownership, decision-time context, wheel packaging, and forbidden query/runtime writes
- External/provider/browser/storage dependencies: an Accepted S2B backup gate and a network-none/no-port/tmpfs disposable PostgreSQL system; no live provider, browser, original source, Milvus client, or durable-candidate write

## Mock Policy

- Mocks used: none for the identity engine or real PostgreSQL acceptance paths; boundary spies are limited to proving fail-before-connect and fail-before-write ordering
- Behavior not mocked away: target identity, Alembic migrations, PostgreSQL constraints/triggers/locks, transaction rollback, restart load, replay, and concurrent downgrade behavior
- Complementary real interaction / contract / trace / browser check: the complete contract matrix runs with real code and the storage matrix runs against an owned isolated PostgreSQL system with exact marker, gate, revision, and cleanup checks

## GREEN Criteria

- The Accepted Task 5.3 scenarios and all Task 5.4 integrity siblings pass through one deep module.
- A fresh process persists and loads the exact typed result; invalid or conflicting writes leave no partial identity history.
- C2_0006 is append-only, reversible only when safe, fail-closed on unreconstructable history, and serialized with the offline writer through one parent-first lock order.
- Query/answer/runtime code cannot invoke the identity writer; all writes require offline authority, an Accepted backup gate, and an explicit disposable target.
- Complete checkpoint regression, static, packaging, OpenSpec, source/candidate, and cleanup gates pass without weakening prior tests or acceptance.

## Forbidden Shortcuts

- No visible-case entity mapping, institution list, legacy-ID compatibility rule, or test-only production branch.
- No inferred historical context, partial output allocation, mutable-evidence replay, generic DSN fallback, or bypass of backup/target checks.
- No live Web/LLM write, query/answer identity mutation, durable-candidate migration, original-source connection, or Milvus open.

## Verification Plan

- RED command: `uv run pytest -n0 tests/canonical_v2/test_canonical_identity_resolution_contract.py -q --no-cov --runxfail`
- Focused GREEN command: `uv run pytest -n0 tests/canonical_v2/test_canonical_identity_resolution_contract.py tests/canonical_v2/test_canonical_identity_postgres.py tests/canonical_v2/test_canonical_decision_postgres.py -q`
- Regression command: run the complete Canonical V2 suite on explicit no-database and isolated S5D/S4C targets, then the frozen S1, S2/S2B, and S4E harnesses
- Browser/API/state workflow command: verify by repository-wide import search that query, answer, admin, and runtime paths do not import the offline identity writer; no browser workflow belongs to Task 5.4
- Real interaction / contract / trace command: run C2_0006 migration, persistence, replay, conflict, concurrency, rollback, and downgrade tests against the named network-none/no-port/tmpfs disposable PostgreSQL target
- OpenSpec validation command: `openspec validate rebuild-canonical-v2-knowledge-platform --strict`

## Task 5.5 temporal extension

- RED paths: `tests/canonical_v2/test_canonical_decision_engine_contract.py` and
  `tests/canonical_v2/test_canonical_decision_postgres.py`.
- Observed REDs: relationship decisions dropped selected validity; all accepted/selected decisions
  were projected as current; equal evidence with different intervals auto-merged; PostgreSQL load
  reconstructed current selections without validity; equal non-UTC instants changed assertion and
  batch hashes; validation-time interval disagreement leaked an engine-private exception.
- Observable GREEN: Professor affiliation-like episodes retain old/new evidence and decisions while
  only the episode valid at `as_of` is current; fields and relationships use half-open intervals,
  preserve unknown endpoints, keep future/ended decisions as history, and retain source event time
  without synthesizing validity.
- Integrity GREEN: selected evidence has one exact validity pair, relationship decisions/current
  selections copy it exactly, rehashed current/interval tampering fails closed, all Canonical V2
  datetimes canonicalize to UTC, and corrupt restart remains behind the storage error abstraction.
- Real interaction: a marked network-none/no-port/read-only-rootfs/tmpfs PostgreSQL disposable ran
  the complete decision restart matrix, including `+08:00` input under an `Asia/Shanghai` database
  session, replay conflict rollback, append-only siblings, and owned cleanup. No C2_0007 migration
  was needed because C2_0002/C2_0005 already retain the required assertion and decision time fields.
- Review policy: one merged specification/code-quality review for Task 5.5; it closed two Important
  findings and ended `APPROVED` with zero open Critical/Important findings. Relationship
  `superseded` interval semantics are explicitly deferred to Task 5.6 rather than invented here.

## Task 5.6 review/history extension

- RED paths: `tests/canonical_v2/test_canonical_decision_engine_contract.py`,
  `tests/canonical_v2/test_canonical_identity_resolution_contract.py`,
  `tests/canonical_v2/test_canonical_decision_postgres.py`, and
  `tests/canonical_v2/test_canonical_identity_postgres.py`.
- Observable GREEN: unresolved field, relationship, and identity outcomes yield deterministic
  immutable review cases; an exact evidence-bound human resolution creates a new offline decision
  or verdict and cannot mutate the originating decision, assertions, or review case. Stale,
  unsupported, cross-wired, or invented resolutions fail closed.
- History GREEN: replacement, withdrawal, unresolved, rejected, future, ended, and accepted
  lineages retain complete history and derive only the unique as-of-valid unsuperseded head as
  current. Exact replay/reordering is byte-identical, and identity review preserves complete
  merge/split/reversal source allocation.
- Storage GREEN: C2_0007 retains reviewer/policy/outcome/rationale/time provenance and enforces one
  logical root, one child per predecessor, strict release ancestry, subject/relationship continuity,
  cycle refusal, append-only replay, atomic rollback, restart reconstruction, populated-upgrade
  preflight, and retained-review downgrade refusal. Both adapter and direct-SQL paths are covered.
- Review policy: one merged specification/code-quality review plus the migration/write-boundary
  safety exception permitted by lean execution. Both reviews ended with zero open Critical or
  Important findings.
- Commit checkpoint: complete no-database and real-disposable Canonical V2 regressions, fixed-name
  S4C compatibility, S1/S2/S2B/S4E gates, C2_0001 through C2_0007 migration safety, Ruff, Pyright,
  wheel contents, strict OpenSpec, diff/formal/secret/import checks, frozen source and forced-read-
  only candidate audits, and owned-resource cleanup must all pass before acceptance.

## Task 5.7 temporal-precision correction

- Decision owner: ADR-012 and the `Temporal precision` term in root `CONTEXT.md`.
- RED paths: affected shared-contract, decision/history, persistence, typed-subobject, and domain-
  projection temporal matrices. The current Professor affiliation date-only reproduction must remain
  RED until the shared precision-bearing contract exists.
- Observable GREEN: date-only validity remains a calendar date, instant validity canonicalizes to an
  equivalent UTC instant, precision changes content identity, and both forms persist/restart without
  coercion or loss.
- Exact lineage GREEN: assertion, current selection, and typed projection equality bind precision
  plus value. A date and instant on the same lexical day are not exact equality.
- Comparison GREEN: cross-precision ordering/overlap is owned by one named versioned fail-closed
  policy. `explicit-calendar-v1` requires caller-supplied Gregorian calendar/timezone context,
  interprets dates as half-open civil-day intervals for comparison only, returns `indeterminate`
  without context, and never reads ambient defaults or reports cross-precision exact equality.
- Storage GREEN: any representation change uses only an explicit owned disposable target, has
  reversible migration/restart evidence, and leaves the durable candidate and C2_0004 landing
  checkpoint unchanged.
- Review policy: one merged specification/code-quality review, plus a focused migration/write-safety
  review if persistence changes; both end with zero open Critical/Important findings.
- Downstream gate: Task 6.3 stays stopped and its dirty worktree is not Candidate evidence until
  Task 5.7 is Accepted and the affected S5 regression surface is GREEN.

## Task 6.1 PRD domain/relationship catalog extension

- Artifact/source RED/GREEN: the checked-in canonical JSON binds every authority file to one exact
  repository-confined path, full-file SHA-256, authority tier, citation range, and required source
  terms. Duplicate keys, source drift, path escape, unknown fields, nondeterministic bytes, or a
  self-hash mismatch fail closed.
- Domain RED/GREEN: one shared envelope plus exactly four domain catalogs freeze 9 shared fields,
  101 domain fields, and 28 typed sub-objects. Locked precedence requires Paper title/year/venue/
  authors and Professor `patent_ids`; Paper summaries are conditional for canonical inclusion and
  required only by the quality-ready policy. `last_updated` is observation metadata, and each
  sub-object names its parent domain.
- Relationship RED/GREEN: 34 exact source-cited types cover seven canonical families and round-trip
  through the Accepted `RelationshipType` contract. Identity/evidence lineage is immutable and
  persistence-deferred; business facts retain proportional decision states. Role ownership,
  same-domain identity lineage, decision/assertion family-subject compatibility, Professor-Paper
  attribution evidence, Professor-Company role exclusivity, and conditional Company/Professor
  cross-domain endpoints are validator-enforced.
- Layer/scenario GREEN: canonical evidence-bearing types are separated from deferred release-derived
  and session relations. Forty-two accounting scenarios cover every type/family plus all eight
  Professor↔Paper, Professor↔Company, Professor↔Patent, and Company↔Patent directions with explicit
  `supported`, `absent`, or `insufficient_evidence` outcomes. These outcomes describe S2 source
  potential, not built or accepted edges.
- Builder safety: output is confined to the approved S6 root, symlinks/escapes fail before write,
  rendered bytes validate in a same-filesystem temporary file, and only then atomically replace the
  prior artifact. Validation failure preserves the prior file.
- Review policy: the one merged Task 6.1 specification/code-quality review closed five Important
  findings and ended `Ready: Yes` with zero open Critical/Important findings. No migration or safety
  exception review applies because the slice changes no production/storage boundary.
- Commit checkpoint: deterministic build/check, the Task 6.1 plus Accepted shared-contract tests,
  Ruff format/check, app-environment Pyright, strict OpenSpec, the formal S2B gate, diff/secret/
  source-drift/scope checks, and generated-cache cleanup must pass before acceptance. No database,
  Milvus, provider, runtime, or candidate write is permitted or required.

## Historical Task 2.8 review-workbench contract (retired)

The `single-human-global-stratified-v2` contract and its 29 contract decisions, 23 exclusions, 60
blind calibration labels, judge authorization, exports, validators, and review-workbench state were
never completed as product acceptance. The user retired this workflow on 2026-07-26 after direct
evaluation showed that it did not express the intended product question. Its immutable artifacts are
retained for history only and SHALL NOT gate or feed Tasks 8.1, 8.8, 9.8, or 12.2-12.6.

## Status

As of the user-confirmed 2026-07-26 rebaseline, Tasks 2.8, 8.1, 8.8, and 9.8 are retired and the
ledger is `75/80`. Exactly Tasks 12.2-12.6 remain. Any older status text below is historical evidence
and does not restore retired dependencies.

S1 database-target safety, S2 tasks 2.1–2.5 and corpus/ground-truth/threshold policy, and S2B/task
2.6 backup/independent-restore gate are Accepted. Tasks 3.1–3.5 and the complete S3
interface/database foundation are Accepted. Tasks 4.1–4.5 and all S4 Immutable Evidence Landing are
Accepted at `2026-07-11T22:07:12Z`. The isolated candidate is C2_0004 with the exact bounded
six-family landing state and zero non-landing business rows. Checkpoint manifest
`ab091aac…966b1`, restore verification `caf789ae…f0acc`, and frozen external tree
`4ae5f2ce…b05012` prove full 26-table logical parity across distinct PostgreSQL systems. Task 5.1's
five assertion/decision strict RED scenarios are Accepted at `2026-07-11T22:58:11Z`. Task 5.2 is
Accepted at `2026-07-12T04:32:46Z`: C2_0005, the reproducible decision core, and disposable-only
PostgreSQL history retain complete assertion/outcome/decision/context evidence. Task 5.3's five
strict offline identity-resolution RED scenarios are Accepted at `2026-07-12T05:21:29Z`; they define
strong-ID merge, content-bound cross-format LLM judgment, same-name separation, named merge reversal
with exact split allocation, and recovered-source linkage through one deep seam. Task 5.4 is
Accepted at `2026-07-12T08:40:35Z`: one complete-release identity module plus C2_0006 and an
offline/disposable-only store retain exact decision-time evidence, output allocation, current
ownership, terminal history, replay, rollback, and reversible migration safety. Task 5.5 is
Accepted at `2026-07-12T09:58:35Z`: proportional UTC-canonical temporal semantics now retain exact
observation/source-event/validity evidence and derive only the as-of-valid generic current subset.
Task 5.6 is Accepted at `2026-07-12T15:04:36Z`: immutable review provenance, exact human resolution,
and generic current/history reconstruction are closed through C2_0007 on owned disposable targets.
The durable candidate remains C2_0004 with zero canonical/non-landing rows. Task 6.1 is Accepted at
`2026-07-12T16:40:08Z`; no database, Milvus, provider, runtime, or candidate write occurred. On
2026-07-13 ADR-012 added Task 5.7/S5G to preserve date-only versus instant precision across the
shared temporal interface. The user selected `explicit-calendar-v1`; S5G was Accepted at
`2026-07-13T09:19:45Z` with zero open Critical/Important review findings. Task 6.3 was Accepted at
`2026-07-13T09:56:27Z` with the complete typed/inclusion/C2_0009 evidence recorded in
`verification.md`. Task 6.4 relationship RED was integrated and Accepted at
`2026-07-13T10:12:13Z` after its side-branch contract was rebound to the Accepted Task 6.3 typed
projection registry; Task 6.5 owns GREEN implementation.
An S6A2 prerequisite rebind was Accepted at `2026-07-13T10:49:49Z` after S5G changed two catalog
authority files without refreshing their full-file source hashes. The catalog semantics are
unchanged; the current content/file identities are `8ad9e719…41d7` and `b227285f…83c0`. Every later
S6 acceptance and the mainline promotion gate must run the deterministic catalog check plus the
24-test catalog/shared baseline so authority drift cannot escape again.
Task 6.5's pure projection sub-slice S6E was Accepted at `2026-07-13T12:35:08Z`: the package-internal
`RelationshipProjection.project(...)` interface validates the installed 34-type catalog, exact S6c
roots/subobjects, retained evidence, source assignments, assertions, decisions, roles, state, time,
layers, and all eight directions. Date-only currentness requires the explicit S5G calendar context
and otherwise reports `indeterminate`. Task 6.5's persistence sub-slice S6E2 was Accepted at
`2026-07-13T13:54:12Z`: C2_0010 and the guarded PostgreSQL adapter retain content-bound run/outcome,
typed assertion/decision, shared-ledger membership, and unified current surfaces while reusing rather
than duplicating existing shared relationship rows. Exact replay/restart, candidate/append-only,
endpoint/evidence lineage, backup/target identity, atomic rollback, and safe downgrade gates pass on
owned disposable sibling databases. Task 6.5 is Accepted. Task 6.7 was Accepted at
`2026-07-13T14:18:02Z`: one deterministic package-internal path-policy seam produces one
content-bound shared `PolicyDecision` for each of the six published paths, keeps inclusion separate,
retains ordinary quality as evidence-bound limitations/gaps, applies named hard exclusions only to
their affected paths, validates all eight catalog traversal orientations, and redirects a merged
predecessor only to one current survivor.

Task 6.8/Aggregate S6 was Accepted at `2026-07-13T14:48:01Z`. The review accounts for all four
domain roots, 101 domain fields, 28 typed subobjects, 34 relationship types/seven families, eight
cross-domain directions, and six independently evaluated paths. Its first full real-PostgreSQL run
found four historical relationship-integrity fixtures that inserted decisions after a release was
already accepted: three failed early and one was a false positive. The fixtures now follow the
candidate→accepted→next-candidate lifecycle; focused GREEN is 4/4 and the complete corrected real
matrix is 348 passed with only the four future public-module xfails. No production implementation or
migration was weakened. The aggregate review has zero open Critical/Important findings, all owned
databases were removed, and the durable candidate remains C2_0004.

ADR-013 through ADR-022 later clarified requirements that were not part of the historical S2/S6
acceptance contracts. S2C2/Task 2.7 and S6R/Tasks 6.9-6.11 are Accepted. At that historical point,
S2C3/Task 2.8 gated Task 8.1 calibration and Tasks 8.8/9.8. The 2026-07-26 rebaseline above later
retired all four gates without relabeling their historical implementation evidence as accepted
product behavior.

Git `main` promotion is separately gated after aggregate S6 acceptance. The execution session must
re-prove a clean V2 integration worktree, complete side-branch accounting, preservation of root dirty
state, strict-ancestor topology, and all aggregate checks before a fast-forward-only ref move. This
gate never authorizes merge/rebase, push, or database/index cutover.

## Behavior owner

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Acceptance: `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md`
- Effect baseline: `.agents/runs/canonical-v2-logical-rebuild/outcome-requirements.md`

## Verification objective

Prove that a clean isolated Canonical V2 platform can be reconstructed from immutable evidence,
serve broad and precise four-domain/relationship retrieval with universal current-Web augmentation,
produce claim-grounded progressive answers, and publish canonical/index releases consistently and
reversibly without touching original forensic sources. Prove first that every required source family
has a content-addressed backup and independently verified recovery path, and that online query paths
cannot mutate offline canonical identity decisions.

## Environment and forbidden targets

- Original Postgres container: `pgtest`, last checked `paused=true`, exposed host port `15432`.
  It MUST remain paused and is never a connection, migration, repair, replay, or write target.
- Original Postgres volume:
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`. The paused
  source container still has its historical read-write mount, so no command may unpause or enter it;
  only the Accepted S2B copy run mounted it `rw=false`, and implementation tests may not mount it.
- Forensic checkpoint root:
  `/home/longxiang/.mirothinker_recovery/20260711T022932Z-pgtest-forensic-freeze/`;
  canonical source/copy manifest SHA-256:
  `bce14dce8fe2da4d053ac9cd930e1532f4abb436c5d03fff07aa69fd180e9e91`.
- Verified FPI salvage dump SHA-256:
  `cef8eb6ba18ebd23fde3e47023222ecb82bc8f27582040efe5a212a7f9fdfbb7`.
- Original repository Milvus file:
  `apps/miroflow-agent/milvus.db`, SHA-256
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
  No Milvus client may open it; hash-only checks are allowed.
- Recovery lab: `pgtest-recovery-lab-01`, network `none`, no exposed ports. Approved existing
  isolated databases are `miroflow_recovery_candidate` and
  `miroflow_recovery_candidate_verify`; S1 tests must use newly created disposable targets, not these
  evidence checkpoints.
- Candidate and disposable database DSNs: explicit full DSNs only; target database name/identity
  must be asserted before any destructive command.
- The durable candidate is not persistently configured with
  `default_transaction_read_only=on`. Read-only inspections therefore MUST force a read-only session
  and transaction. Task 5.2 writers additionally reject every non-`disposable` target; no evidence
  claims that the candidate has database-level immutable enforcement.
- A generic `DATABASE_URL` is never accepted as fallback for migration/test/rebuild targets.
- Real provider calls are allowed only in named acceptance runs with secrets from the approved
  environment and no credential values in logs/evidence.
- Backup/restore gate: Accepted S2B evidence is in
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2b/`. Every future rebuild-write entry point
  must verify the exact acceptance record before its first write; changed/missing evidence fails
  closed.
- S2B backup coverage MUST include original PostgreSQL, original Milvus, WAL/FPI, salvage, and all
  inventoried historical SQLite/JSONL/XLSX/PDF/cache/raw-source families. Restore targets must be
  distinct from original and backup locations; original volumes/files remain read-only.

Last identity/hash check recorded in `verification.md`: `2026-07-12T08:40:35Z`.

## Hard invariants

1. Original Postgres/Milvus write attempts: zero.
2. Destructive target-identity ambiguity: fail before writes.
3. Wrong-identity canonical merge or cross-domain join in reviewed gold: zero.
4. Invented placeholder entity/fact/evidence from partial recovery: zero.
5. Unsupported material answer claims in accepted samples: zero.
6. Unsourced material current-Web claims: zero.
7. Broken canonical relationship references: zero.
8. Mixed canonical/published/Milvus release IDs: zero.
9. Unexplained missing/extra/stale/cross-release index points: zero.
10. Direct online Web/LLM write to active canonical/index: zero.
11. Canonical V2/landing write before accepted complete backup and restore verification: zero.
12. Query/answer-path canonical identity or source-identity mapping mutation: zero.
13. False exhaustive list claim or hidden required-member omission: zero.
14. URL used as a Professor/Company/Paper/Patent identity, or Web snapshot replaced after binding:
    zero.
15. Company or Technology capability propagated to a named Product without direct Product evidence:
    zero.
16. Safety-guidance venue allegation, discovery/evasion assistance, or unrequested general-Web call:
    zero.
17. Continuation option without an accepted trigger, executable binding, or supported wording: zero.
18. Ambiguous entity auto-selection that fails the accepted evidence/confidence/margin/protected-slot
    gate, or dominant interpretation rendered without notice: zero.
19. Unresolved Person reference materialized as a Person identity, or Person/Technology admitted as a
    fifth public domain: zero.

## RED artifacts by slice

### S1 — Database target safety

- Integration tests invoke Alembic/test helpers with conflicting generic and explicit DSNs.
- RED proves current code can select/fall back to the wrong target or lacks identity assertion.
- GREEN proves only the explicit disposable target changes and ambiguous/missing targets fail closed.

### S2 — Baseline and thresholds

- Read-only inventory manifests and reviewed corpus manifests.
- Baseline reports for data/relationship coverage, path reach, recall, precision, ranking, answer
  support, Web behavior, latency, and cost.
- `acceptance-thresholds.json` approved before later slices become Ready.

### S2B — Complete source backup and independent restore gate

- A reviewed source-to-backup manifest proves family completeness, source/backup identities, byte
  sizes, SHA-256, copy run/time, storage location, and no hard-link dependence.
- A second isolated restore/materialization target proves PostgreSQL database/revision/schema/count,
  Milvus copy schema/collection/count, and file/recovery-family hash plus bounded readability/replay.
- RED gate tests prove missing families, hash mismatch, source-path use, absent restore evidence, or
  failed probes reject task 3.2 and all Canonical V2/landing writes before their first write.
- Original Postgres remains quiesced; any dedicated backup mount is read-only. Original Milvus is
  copied without opening a client; only the verified copy may be inspected.
- Accepted evidence covers 50/50 source records and passed PostgreSQL, Milvus, forensic/WAL/FPI,
  mount-policy, independent-materialization, and source-invariant probes.

### S2C — Claim-level acceptance-oracle reconciliation

- Task 2.7 RED defines one versioned public case-contract schema and observable failure reasons for
  missing/invalid required or forbidden claims/entities, allowed variants, source snapshots/as-of,
  enumeration policy, stage oracles, and content identity. Reference prose remains review context.
- GREEN migrates applicable regression/challenge turns without converting known-bad prose or model
  memory into truth. Dynamic cases bind immutable snapshots; unsupported evidence produces an
  explicit unavailable-evidence outcome rather than an invented expectation.
- Task 2.8 validates per-case hard failures independently of aggregate metrics, snapshot/version
  tamper detection, evidence-bounded LLM judging, and one attributable human under the versioned
  five-stratum global calibration policy.
- Focused commands are the S2C schema/fixture validator and its tests under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/`, followed by strict OpenSpec,
  deterministic manifest rebuild/check, and diff/source-hash checks. No runtime provider, database,
  Milvus, or canonical write belongs to S2C.
- Done evidence records schema/corpus/policy/workload/export versions and SHA-256, the exact
  29/23/60 accounting, every hard-case outcome, reviewer and judge authorization state, reproduced
  calibration gates, and zero unresolved Critical/Important findings. S2C is not Accepted while any
  case used by S8/S9 remains `pending_user_review` or before a real attributable round passes.

### S3–S7 — Data platform and release

- Real isolated Postgres migration/constraint/transaction tests.
- Chain-of-custody replay and hash fixtures for every source-adapter family.
- Identity/fusion/relationship/eligibility scenario matrices through module interfaces.
- Candidate manifest, full-index build, exact parity, promotion rehearsal, and rollback rehearsal.

### S4 — Immutable evidence landing

- Task 4.1 freezes byte identity/copy lineage, parser replay, typed partial/corrupt preservation, and
  zero placeholder/canonical invention through the public `EvidenceLanding.ingest/stream` seam.
- Task 4.2 GREEN must use verified byte/envelope inputs only, retain prior parser outputs, reject
  unverified original Milvus/source kinds, and expose no durable/canonical/publication/index effect.
- Task 4.3 owns PostgreSQL persistence and transaction tests; task 4.4 owns the bounded actual-source
  replay matrix. The ephemeral Task 4.2 composition is not evidence for either later task.
- Task 4.5 owns independent S4 review plus the landing-only database checkpoint. Acceptance requires
  exact gate/source/implementation/policy binding, byte-identical guarded replay, full user-table
  hashes, normalized schema and integrity summaries, a distinct-system disposable restore, owned-ID
  cleanup, immutable external dump evidence, and zero open Critical/Important review findings.
- Accepted S4 evidence is `s4-landing-review.md` plus `s4e/{checkpoint-manifest,
  restore-verification,checkpoint-freeze-receipt,acceptance-record}.json`. Later slices consume S4
  immutably and create new versioned checkpoints rather than rewriting it.

### S5 — Assertions, decisions, identity, and temporal semantics

- Task 5.1 freezes retained competing field/relationship assertions, deterministic candidate
  constraints before LLM evidence, content-bound structured adjudication, explicit unresolved
  conflicts, and decision-backed generic current selections through one package-internal deep
  module. These selections are not S6 typed domain projections or S7 published projections.
- Normal execution must report exactly five strict xfails; forced RED must report exactly five
  failures for the exact absent `canonical_decision_engine` module. Nested missing dependencies are
  not an accepted xfail reason.
- Task 5.2 GREEN must reconcile release-scoped shared field decisions, relationship type versions,
  raw/validated LLM output binding, and disjoint selected/conflicting evidence roles with the
  existing storage foundation. Accepted GREEN additionally binds exact deterministic outcomes and
  identity ownership into every decision seed, validates current authoritative mappings before the
  first write, and loads historical decisions from immutable decision-time context snapshots rather
  than mutable current identity state. Task 5.1 itself changes no production contract or storage.
- Task 5.3 freezes one offline identity-resolution request/result seam. Candidate verdicts are
  `same_entity`, `different_entities`, or `unresolved` and are not terminal identity actions. The
  result separates unique active current identities, terminal identity history, output-specific
  source assignments, applied decisions, and release-scoped assertion-bound manifests.
- A named prior mistaken merge is corrected by one `reverse` action with 1-to-N replacement
  topology and exact source partition; standalone `split` remains available for 1-to-N correction
  without a named prior decision. Recovered historical IDs remain source lookup lineage and need not
  become canonical IDs.
- Task 5.4 must close the exposed shared/storage gaps without inference: release/content-bound
  identity decisions, exact supporting assertions/records, immutable decision-time inputs, explicit
  per-output source allocation, append-only current/history semantics, and offline-only writes. Any
  new migration must fail closed on nonempty history it cannot reconstruct and receive the migration
  safety checks exempted from ordinary lean review reduction.

### S6 — Typed domains, relationships, inclusion, and eligibility

- Task 6.2 freezes one package-internal `DomainInclusionEngine.evaluate(...)` behavior seam without
  implementing it. Normal execution reports exactly five strict xfails; forced RED reports exactly
  five failures caused directly by absence of
  `src.data_agents.canonical_v2.domain_inclusion`. Nested missing dependencies fail normally.
- The inclusion request binds four shared versioned inclusion policies, active resolved identities,
  retained artifacts/records/assertions, included Professor anchors, offline incremental-Company
  validation decisions, and one deterministic content-bound approved-source-scope manifest.
- Professor evaluation uses approved seed membership, not a runtime institution whitelist. Paper
  evaluation requires approved Professor-roster discovery without conflating discovery/existence
  with authorship. Patent evaluation admits identity-resolved approved-export rows without topic,
  linkage, type, inventor, IPC, or enrichment prefilters.
- Company skeleton membership admits without a completeness gate. Incremental Company automatic
  admission requires retained offline support for basic identity, Shenzhen geography,
  innovation/business relevance, and source validation; incomplete/ambiguous evidence produces a
  visible review result, explicit contrary scope is excluded, and query-time Web alone never
  promotes canonical inclusion.
- Every admitted/review/excluded result binds the exact policy, release, manifest hash, and retained
  assertions. Inclusion has `path=None`, consumes no global `ready`, and performs no provider,
  storage, publication, index, query-time identity, or canonical write.
- Task 6.6 freezes one package-internal `PathEligibilityEngine.evaluate(...)` behavior seam without
  implementing Task 6.3 projections, Task 6.5 relationship construction, or Task 6.7 policies.
  Normal execution reports exactly five strict xfails; forced RED reports exactly five failures
  caused directly by absence of `src.data_agents.canonical_v2.path_eligibility`.
- Published user paths are exactly `exact_lookup`, `structured_filter`,
  `verified_relationship_traversal`, `semantic_recall`, `recommendation`, and `ranking`; internal
  audit/identity paths do not satisfy this registry. Each result contains one unique named decision
  carrying the applicable path-policy version.
- Task 6.6 inputs explicitly consume a future typed current projection plus inclusion decision and
  accepted shared relationship/identity decisions. Canonical lifecycle state remains distinct from
  Paper domain identity status; inverse user traversal never reverses the registered canonical edge.
- Ordinary quality gaps remain visible soft signals. Hard exclusions are named, evidence-bound, and
  path-scoped: a broken relation reference does not poison unrelated exact/semantic paths, a rejected
  attribution does not reject Paper existence, and a merged predecessor resolves to exactly one
  survivor without gaining its own current projection or admitted inclusion.
- Task 6.7 implements the frozen seam without a global `ready` input/output. Path decision identity
  binds the complete path policy and observable outcome; primary and traversal-target field lineage,
  relationship evidence, inclusion evidence, hard-invariant evidence, release, subject, and time
  continuity fail closed. Inclusion `review` cannot promote an identity without a current projection.
- Test-only Tasks 6.2, 6.4, and 6.6 use focused contract/static/OpenSpec/diff checks. They reference
  Accepted backup/source/Candidate evidence without replaying database, source, Candidate, Milvus,
  or provider safety totals because those tasks touch none of those boundaries.

### S6R — Internal Person/Technology reconciliation

- Task 6.9 RED first proves the Accepted S6 catalog is stale against the reconciled authority, then
  freezes catalog/interface scenarios for resolved and unresolved Person references, internal
  Technology concept/route aliases/definitions/hierarchy, distinct non-adoption discussion-or-
  mention/claimed-adoption/demonstrated-use relations, exact relationship-type versioning, and the
  four-public-domain plus answer-scoped Product-capability boundaries.
- RED exercises a new package-internal `InternalReferenceProjectionBuilder.project(...)` interface.
  It remains separate from four-domain `DomainProjectionBuilder`, inclusion, public path-domain, S7
  publication/index persistence, and query/answer behavior. Normal RED must fail for the exact absent
  interface/contract behavior rather than a typo or unrelated dependency.
- Task 6.10 GREEN accepts only resolved Person/Technology identities and retained evidence anchored
  to Professor, Company, Paper, or Patent; unresolved names/terms remain evidence-bearing references.
  Relationship projection consumes an explicit internal-reference registry instead of accepting
  unchecked `registry_entity` endpoints. Product capability remains non-canonical.
- Focused commands include deterministic catalog build/check, catalog/shared-contract tests,
  identity-resolution scenarios, `test_internal_reference_projection_contract.py`, relationship
  projection tests, and four-domain/path negative invariants. If persistence changes, a new reversible
  migration and explicit disposable Postgres matrix are mandatory; historical migrations are never
  rewritten. Pure S6R reference projections otherwise remain persistence-free until S7.
- Task 6.11 reruns the complete S6 catalog/domain/relationship/identity/path and applicable Postgres
  matrix, source-hash binding, Ruff, Pyright, strict OpenSpec, diff/scope/secret checks, and independent
  review. Done evidence records four public domains, internal reference counts/hashes, unresolved-
  reference outcomes, relationship versions, zero `product_has_capability`, and zero open Critical/
  Important findings before S7 becomes Ready.

### S8–S10 — Query, answer, and feedback

- Scenario eval and trace replay are mandatory RED/GREEN evidence; unit-only evidence is insufficient.
- S8/S9 acceptance consumes only an Accepted S2C claim-level contract version. Required/forbidden
  claims/entities, source snapshots/as-of, enumeration policy, and stage outcomes are reported per
  case; hard case failures cannot be averaged away.
- S7 consumes only an Accepted S6R reconciliation. Internal Person/Technology projections remain
  release-scoped auxiliaries over the four public domains, unresolved Person references are not
  forced into identity, and Product capability remains answer-scoped.
- S8 institution-query replay records the original query, matched institution span, resolution
  state, canonical candidate IDs/names or unresolved raw text, catalog and accepted-release
  versions, pure topic, protected slots, and every lane query/filter.
- The S8 institution matrix covers several institutions in canonical and alias forms, an ambiguous
  alias where supported, an unknown institution, no institution, and repeated/overlapping
  institution-topic words. Full-name/alias pairs yield the same canonical constraint and topical
  text.
- An S8 catalog-injection contract proves that query resolution and retrieval filtering consume one
  catalog snapshot: a newly supplied fixture alias resolves without editing query-rewrite code.
  Generic topic stopwords contain no institution names or aliases.
- Recorded external-provider adapters cover success, timeout, invalid schema, conflict, duplicate,
  missing evidence, and budget exhaustion.
- Recorded scenarios cover all enumeration modes, false exhaustiveness, Product-capability non-
  propagation, confidence-gated ambiguity, safety guidance/default Web exclusion, Web entity handle/
  snapshot lifecycle, and conditional ContinuationOffer trigger/selection behavior.
- Named real-provider acceptance run covers Universal Web, LLM plan/rerank/sufficiency/synthesis,
  claim citation, progressive multi-turn behavior, latency, and cost.

### S11–S12 — Consumer migration and final candidate

- API/admin/state integration, reviewed regression/challenge eval, and complete isolated rebuild.
- Broad checks run only after S1 Accepted and with explicit disposable/candidate targets.

## Required evidence shape

Every verification run SHALL record:

- run ID, timestamp, git commit/worktree state, OpenSpec hash, corpus/threshold versions;
- explicit sanitized database/index target identities and release IDs;
- command and exit code;
- source/parser/policy/model/prompt/schema/embedding/reranker versions as applicable;
- counts, hashes, per-domain/path metrics, failures, and hard-invariant results;
- provider availability, calls, latency, cost, and degradation path;
- artifact paths and SHA-256 hashes;
- accepted claim-level case-contract/corpus versions, source snapshot hashes/as-of, enumeration mode,
  per-stage outcomes, and every hard per-case result for S2C/S8/S9/S12;
- internal Person/Technology catalog/projection/release identities and the no-fifth-public-domain
  accounting for S6R/S7;
- for S2B, source/backup/restore identities, family completeness, copy independence, format-specific
  recovery probes, and the accepted backup-manifest hash;
- reviewer/acceptance status without claiming later-slice closure.

## Verification order

1. Static/OpenSpec validation.
2. Nearest pure/interface tests.
3. Complete backup manifest and independent recovery verification; accept S2B before any rebuild
   write.
4. Accept S2C claim-level case contracts before S8/S9 acceptance-oracle execution.
5. Real isolated Postgres migration/integration tests.
6. Accept S6R internal Person/Technology reconciliation before S7 publication/index work.
7. Recorded adapter/trace replay scenarios.
8. Bounded isolated source/candidate replay.
9. Full versioned Milvus candidate and parity.
10. API/session/admin integration.
11. Frozen claim-level regression then challenge evaluation.
12. Named real-provider acceptance.
13. Rollback rehearsal and final evidence review.

## Stop conditions

- Original source pause/hash/identity changes unexpectedly.
- Any command resolves to a forbidden or ambiguous target.
- A hard invariant fails.
- A slice requires behavior absent from the OpenSpec capability.
- A later slice depends on a predecessor not marked Accepted.
- Threshold, corpus, schema, policy, or model version changes without a new versioned baseline.
- S8/S9 attempts to use reference prose/free-text key points as the normative oracle before S2C is
  Accepted.
- S7 attempts to build publication/index projections before S6R reconciles internal Person/
  Technology boundaries with the Accepted S6 catalog.
- Verification evidence cannot distinguish local, current-Web, LLM inference, or release identity.
- A task 3.2+ or other rebuild-write command is proposed before complete S2B backup/restore evidence
  is reviewed and Accepted.
- Query/answer code attempts to create, merge, split, relink, or update canonical identities or
  source-identity mappings instead of emitting an offline review gap.

## Completion rule

The Epic reaches Candidate only when all slices are independently Accepted, every acceptance item is
evidenced, strict OpenSpec validation passes, and the complete isolated candidate passes the frozen
gates. Candidate does not authorize production-like cutover.
