# Change Log

## 2026-07-13

- The user selected Canonical V2 as the implementation mainline and froze overlapping legacy
  retrieval/Web changes as implementation authorities pending evidence/obligation mapping.
- Code-grounded audit found the V2 integration line at 30/74 tasks before this correction, with
  S1-S5 plus Tasks 6.1/6.2/6.6 Accepted and Task 6.3 In Progress.
- Accepted ADR-012: preserve date-only versus instant temporal precision; never invent UTC midnight.
- Added and Accepted Task 5.7/S5G as a narrow shared-contract correction. The shared contract,
  decision/history engine, C2_0008 storage, identity/decision adapters, restart reconstruction, and
  typed-projection consumer preserve date-only versus instant validity without UTC-midnight
  fabrication. The task count is now 31/75 and Task 6.3 may resume.
- Selected `explicit-calendar-v1`: cross-precision comparison requires caller-supplied Gregorian
  calendar/timezone context and returns `indeterminate` without it. S5G was Accepted at
  `2026-07-13T09:19:45Z` after pure, real-disposable PostgreSQL, static, strict OpenSpec, scope, and
  merged specification/code-quality review evidence reached zero open Critical/Important findings.
- Selected aggregate S6 acceptance as the Git `main` fast-forward checkpoint. Promotion is
  fast-forward-only, requires clean/integrated worktrees and side branches plus current verification,
  and does not authorize push or product/data/index cutover.

## 2026-07-11

- Created the breaking pre-launch Canonical V2 Epic from the user-confirmed PRD/effect grill.
- Selected a clean typed platform over V042 sidecars and a fully generic knowledge graph.
- Added six new capability specs and modified Paper identity and Professor split-index behavior.
- Added staged tasks, acceptance gates, source/agent links, and the verification contract.
- Implemented and accepted S1 database-target safety: dedicated destructive target inputs,
  server-side database identity marker, fail-closed Alembic enforcement, direct seed-loader sibling
  protection, RED/GREEN coverage, and a real isolated upgrade/downgrade cycle.
- Original Postgres and Milvus remained frozen; no recovery replay, Canonical V2 schema, broad
  migration suite, or cutover was performed.
- Completed S2 task 2.1 at the S1 checkpoint: deterministic read-only inventory covers authoritative
  PRDs, workbook/backfills, ignored historical SQLite/JSONL/XLSX/cache/release/PDF families,
  forensic recovery artifacts, and recovery-database counts. Original Milvus remains hash-only
  because no verified copy exists.
- Completed S2 task 2.2: the reviewed source-to-PRD matrix maps four domains, typed sub-objects,
  relationship families, retrieval/answer paths, and all six north-star effects to inventoried
  evidence, explicit ceilings, and future owning slices.
- Completed S2 task 2.3: froze deterministic 40-case regression and 12-case challenge corpora with
  source/protected-slot/A-G metadata. User-confirmed workbook answers/key points are case-specific
  reference ground truth, including an explicitly marked known-bad historical response; generated
  PRD/challenge expectations remain pending review and are not treated as factual gold.
- Added the user-confirmed pre-rebuild safety gate: task 2.6/S2B must back up and independently
  restore-verify original PostgreSQL, Milvus, WAL/FPI, salvage, and every inventoried historical
  source family before task 3.2 or any Canonical V2/landing write. Also made offline data builds the
  sole canonical-identity mutation authority; query/answer paths are identity-read-only.
- Completed S2 task 2.4: the deterministic nine-dimension report separates current measurements,
  legacy evidence, and unavailable metrics. Current offline intent fallback is 100/100; current
  retrieval/answer/Web/provider metrics remain unavailable, and legacy precision is explicitly
  unscored rather than treated as zero-false-positive acceptance.
- Completed and accepted S2 task 2.5: froze 24 PRD minima, 25 hard invariants, and 34 calibrated
  product-effect gates. The Accepted registry is cryptographically bound to the exact reviewed
  Candidate; the user also accepted the corpus ground-truth policy and S2 tasks 2.1–2.5. Task 2.6
  remains the mandatory backup/independent-restore gate before any rebuild write.
- Completed and accepted task 2.6/S2B under the user's objective-verification self-approval
  authorization. Content-addressed backup and independent restore cover 48 frozen inventory records
  plus original PostgreSQL and the forensic/WAL/FPI tree; PostgreSQL, Milvus, and forensic probes
  passed. A shared mount-policy repair also removed seven attributable empty anonymous volumes and
  prevents Postgres-image implicit volumes in S2B tool containers.
- Completed and accepted task 3.1 as a test-only RED slice: five strict-xfail contracts freeze the
  typed public seams and observable outcomes for EvidenceLanding, KnowledgeBuild, KnowledgeRead,
  KnowledgeAnswer, and ReleasePublication. Normal pytest stays green while `--runxfail` proves five
  genuine missing-module RED failures; no production module or database write was added.
- Completed and accepted task 3.2: an independent `C2_0001` Alembic history verifies the exact S2B
  admission before engine creation and target identity before DDL, then creates eight empty
  Canonical V2 namespaces without replaying V001–V042. A new network-none/no-port, marked candidate
  passed upgrade/downgrade/re-upgrade and remains at the clean baseline with no business rows.
- Completed and accepted task 3.3: one storage-independent Pydantic seam now defines strict artifact,
  record/assertion, decision, identity, canonical/derived/session relationship, policy, gap,
  release, and manifest values. It rejects hard semantic contradictions while preserving partial
  evidence, unresolved conflict, soft limitations, extensible catalogs, and opaque IDs.
- Completed and accepted task 3.4: C2_0002 adds the constraint-backed shared landing/knowledge/
  publish foundation and passes real disposable FK, uniqueness, append-only, reversal, release-
  scope, pointer, transaction, and downgrade/re-upgrade tests. The empty durable candidate was
  forward-upgraded only; a deterministic pg_dump fingerprint repair also replaced volatile raw
  schema hashes and made destructive baseline tests disposable-only.
- Completed and accepted task 3.5/S3 after independent review. C2_0003 repairs hash-bound parent
  lineage, record/identity provenance, bulk and mutable-history erasure, cross-release/self/wrong-
  subject decision lineage, and persisted structured-LLM traces; strict RED interfaces now reuse
  shared types, and the Canonical V2 test subtree prevents default xdist migration races. The empty
  durable candidate matches the reviewed disposable fingerprint and remains isolated at C2_0003.
- Completed and accepted task 4.1 as a test-only RED slice. Four strict scenarios freeze exact byte/
  copy lineage, parser-version replay without mutation, typed partial/corrupt preservation, and zero
  placeholder/canonical invention through the `EvidenceLanding.ingest/stream` seam. Forced RED is
  exactly four absent-module failures; no landing implementation or source/database write began.
- Completed and accepted task 4.2. A storage-independent `EvidenceLanding` core now verifies exact
  bytes and parent/copy lineage before atomically exposing deterministic replay records. Offline
  adapters cover verified WAL/FPI salvage envelopes, historical JSONL/JSON/CSV/XLSX/SQLite bytes,
  verified Milvus copy exports, and already-collected response envelopes while preserving readable
  partial evidence and typed failures. Two self-review RED/GREEN passes closed complete-run
  idempotency, detached snapshot immutability, duplicate/misaligned structured fields, strict JSON,
  source-identifier, and response-provenance defect classes across sibling paths. No durable landing
  row, source, Milvus client, provider, canonical, publication, index, or runtime consumer was
  touched; task 4.3 remains the persistence boundary.
- Completed and accepted task 4.3. C2_0004 adds an immutable ingest-run identity, parser options,
  ordered record positions, and fail-closed nonempty-C2_0003 admission; a PostgreSQL repository now
  verifies the Accepted backup gate, explicit target marker, and revision before transactionally
  retaining artifact/parser/record/error/run state. Restart, exact/conflicting/concurrent runs,
  shared-artifact races, parent/parser replay, append-only guards, forced rollback, relative-gate
  rejection, and invalid-JSON degradation passed on a new disposable database. The disposable was
  deleted; the durable candidate remains untouched at C2_0003/zero rows, and task 4.4 remains the
  actual-source replay boundary.
- Completed task 4.4 as a reviewable Candidate. The exact Accepted S2B backup/restore checkpoint now
  drives a bounded six-family WAL/FPI, SQLite, JSONL, XLSX, verified-Milvus-copy, and recorded-
  response matrix through the public landing interface. Streaming file-manifest registration and
  explicit backup -> restore -> derived lineage avoid loading the 1.3 GB Milvus copy as parser
  bytes; deterministic selectors retain 21 records and six typed errors in 15 immutable artifacts.
  The isolated candidate was forward-upgraded only to C2_0004 and idempotent replay produced the
  same checkpoint bytes without canonical/release rows. Task 4.5 still owns independent landing
  review, acceptance, and the candidate dump/manifest checkpoint.
- Completed and accepted task 4.5/S4 after two independent read-only `Ready` reviews and repair of
  replay target/source binding, immutable output separation, complete table/integrity snapshots,
  and owned disposable-restore lifecycle safety. A fresh guarded six-family replay remained
  byte-identical to `a88b44fa...e80b5`; checkpoint manifest `ab091aac...966b1` and restore evidence
  `caf789ae...f0acc` prove exact C2_0004 schema/26-table/logical parity across distinct PostgreSQL
  system identifiers. The external dump tree `4ae5f2ce...b05012` is frozen read-only, all temporary
  containers/sockets are absent, and Docker volumes are unchanged.
- Accepted the response-family requirement through two complementary observable paths: the Task 4.2
  complete `newly_collected_response` contract and the Task 4.4 real degraded
  `recorded_collected_response` evidence. No live Web/provider call or unknown HTTP provenance was
  invented. All five Evidence Landing acceptance checks are now closed; task 5.1 has not started,
  and no canonical/release/index or production-like state was created.
- Completed and accepted task 5.1 as a test-only RED slice. Five strict scenarios define retained
  field/relationship assertions, deterministic constraint outcomes before LLM evidence, content-
  bound structured adjudication, unresolved no-projection behavior, order-independent decisions,
  and evidence-backed generic current selections through one package-internal decision-module seam.
  Two review passes closed exact missing-module masking, policy/config binding, structured-output
  hash binding, relationship-unresolved coverage, and explicit Task 5.2 contract/schema handoff.
  No production module, shared contract, migration, database row, source, provider, typed domain,
  candidate release, publication, index, or runtime behavior changed.
- Clarified the future S8 institution-query invariant after identifying the legacy Tsinghua topic-
  stopword case as a systemic single-case patch. S8 must resolve a typed, release-scoped
  institution slot from one canonical/alias catalog before span-aware pure-topic rewriting and must
  cover multi-institution full-name/alias, ambiguous/unknown/absent, and overlap scenarios. Task 5.2
  and legacy `chat.py` remain unchanged.
- Completed and accepted task 5.2. A storage-independent decision engine now retains every field and
  relationship assertion, applies deterministic identity/type/path/time constraints before optional
  recorded structured adjudication, emits explicit outcomes/conflicts, and derives only evidence-
  backed current selections. Decision IDs bind the complete decision, assertion-group manifest,
  deterministic outcomes, policy/model/trace data, and decision-time identity context.
- Added C2_0005 and an explicit disposable-only PostgreSQL store. Structured LLM bytes and validated
  JSON are content-bound; selected/conflicting roles are disjoint; outcome and per-family identity-
  context snapshot ledgers are FK-linked, hash-checked by the adapter, append-only, transactionally
  replayable, and protected by downgrade locks/refusal. C2_0005 fails with SQLSTATE `55000` rather
  than inventing snapshots when C2_0004 already contains field or relationship decisions.
- Closed the systemic Alembic URL interpolation defect with one boundary helper used by all affected
  tests, including encoded Unix-socket and reserved-character URLs. Final review found zero open
  Critical/Important findings. Disposable databases/container/socket/wheel artifacts were removed;
  the accepted C2_0004 candidate and all original sources remained unchanged. Task 5.3 has not
  started.

## 2026-07-12

- Completed and accepted task 5.3 as a strict test-only RED slice. Five scenarios now define a deep
  offline identity-resolution seam for deterministic Paper strong-ID merge, content-bound
  cross-format Professor LLM adjudication, same-name Professor separation, named Company merge
  reversal with exact 1-to-N assignments, and recovered Patent linkage without legacy-ID
  compatibility.
- Candidate comparison verdicts are separate from applied identity actions; `different_entities`
  never terminally rejects valid objects. Current active identities, terminal history, exact source
  assignments, decision provenance, assertion/record evidence, recorded LLM bytes, manifests, and
  mutation-sensitive hashes are independently checked. One merged review closed all Important
  findings and returned `APPROVED`.
- Checkpoint regression and frozen-source audits passed without a database write or provider/index
  call. The durable candidate remains C2_0004 with its accepted landing checkpoint and zero
  knowledge/publish rows. Task 5.4 production/storage work has not started.
- Completed and accepted task 5.4. One package-internal offline identity module now resolves complete
  multi-component releases across Professor, Company, Paper, and Patent through versioned
  normalization, strong/composite candidate recall, deterministic rules, and content-bound recorded
  structured adjudication. Candidate verdicts remain distinct from applied create/link/merge/split/
  reverse/reject actions; low-confidence or ambiguous evidence degrades without flattening valid
  identities or relabeling component-wide LLM evidence as decision-local evidence.
- Added C2_0006 and an explicit offline/disposable-only PostgreSQL store for identity runs, verdicts,
  immutable decision-time contexts, assertion/source/record evidence, output-specific source
  allocation, current membership, terminal history, and lineage. Deferred constraints enforce exact
  action shapes, evidence/context sets, allocation partitions, current ownership, state transitions,
  and lineage. Store, upgrade, and downgrade share one parent-first lock order; unsafe populated
  downgrade or unreconstructable pre-existing history fails closed without inferred backfill.
- Exact restart load, idempotent/concurrent replay, same-ID content conflicts, mid-transaction
  rollback, structured-trace binding, create-to-merge-to-reverse lifecycle, and migration races pass
  on a real network-none/no-port/tmpfs PostgreSQL disposable. C2_0005 decision persistence remains
  compatible and now refuses ambiguous legacy multi-output ownership rather than smearing sources.
- The single merged specification/code-quality review and focused migration-safety review findings
  were closed with zero open Critical/Important items. Complete Canonical V2, S1, S2/S2B, and S4
  checkpoints plus Ruff, Pyright, wheel contents, strict OpenSpec, formal gate, source/candidate
  read-only audits, and cleanup checks passed. Original sources and the C2_0004 durable candidate are
  unchanged; task 5.5 has not started.
- Completed and accepted task 5.5 without a new migration. The existing decision seam now retains
  exact observation/source-event/validity times, copies one exact selected evidence interval into
  relationship decisions and generic current selections, and derives `current_fields` and
  `current_relationships` as the half-open `[valid_from, valid_to)` subset at the offline build's
  `as_of`. Prior and future selected decisions remain immutable history; unknown validity is not a
  hard gate; equal values or attributes with different intervals do not auto-merge.
- Canonical V2 aware datetimes are normalized to UTC before IDs, JSON hashes, fingerprints, or
  persistence. Equivalent `+08:00` input and an `Asia/Shanghai` PostgreSQL session restart now
  produce byte-identical decisions and content hashes. Validation-time interval disagreement uses
  `ValueError`, structured generation maps it to a typed adjudication error, and corrupt durable
  replay remains behind the store persistence-error abstraction.
- A real network-none/no-port/tmpfs disposable proved affiliation-like history/current restart,
  exact time retention, replay, tamper rejection, and atomic rollback. The one merged review closed
  both Important findings and returned `APPROVED`; complete Canonical V2, S1, S2/S2B, and S4
  checkpoints plus static, packaging, strict OpenSpec, formal gate, frozen-source/candidate audits,
  and owned cleanup passed. Original sources and the C2_0004 durable candidate are unchanged; task
  5.6 owns aggregate S5 review queues and superseded-decision history semantics.
- Completed and accepted task 5.6. Deterministic unresolved field, relationship, and identity
  outcomes now expose immutable evidence-bound review cases; admissible human resolutions create a
  new offline `human_review` decision or verdict without mutating the originating history. Review
  IDs and resolution content bind the logical subject, exact candidates/conflicts, policy/method,
  reviewer, outcome, rationale, and reviewed time; unsupported, stale, cross-wired, or invented
  resolutions fail closed.
- A generic decision-history projection now retains every assertion, review case, and decision while
  deriving only the unique as-of-valid unsuperseded head as current. Replacement, withdrawal,
  rejected/unresolved, future, ended, and accepted lineages reconstruct identically after restart;
  reviewed identity merge/split/reversal preserves exact source allocation. C2_0007 durably retains
  human-review provenance and enforces one logical root, one child per predecessor, strict release
  ancestry, subject continuity, cycle refusal, append-only replay, and safe downgrade refusal in
  adapter and direct-SQL paths.
- The focused migration/safety review and the single merged task review ended with zero open
  Critical/Important findings. Final checkpoint regression passed in no-database and real
  disposable modes, including C2_0001 through C2_0007 upgrade/downgrade, S4C compatibility, prior
  S1/S2/S2B/S4 gates, static typing/lint, wheel contents, strict OpenSpec, formal admission,
  frozen-source/read-only-candidate audit, and owned cleanup. Original sources and the C2_0004
  durable candidate remain unchanged; task 6.1 has not started.
- Completed and accepted Task 6.1 as an evidence-only PRD catalog freeze. A deterministic,
  content-hashed artifact binds 14 authority files and 27 exact citations to 9 shared fields,
  101 four-domain fields, 28 typed sub-objects, 34 canonical relationship types across all seven
  required families, three relationship-layer boundaries, 42 source-accounting scenarios, and all
  eight approved cross-domain traversal directions. Supported/absent/insufficient-evidence labels
  describe source potential and never claim a built or accepted edge.
- The systemic review repair removed an unsupported canonical alias edge, replaced broad family
  citations with exact lineage/business/multi-turn evidence, made identity endpoint bindings and
  business-role ownership proportional, separated Professor-Paper evidence from business roles,
  constrained union endpoints against cross-domain identity mistakes, reconciled locked Paper/
  Professor requiredness without a global completeness gate, and confined builder output to
  validated atomic replacement inside the S6 root.
- The single merged specification/code-quality review closed five Important findings and returned
  final `Ready: Yes`. Deterministic build/check, 24 Task 6.1/shared-contract tests, Ruff,
  app-environment Pyright, strict source/hash validation, and the formal Accepted S2B gate passed.
  No production code, migration, database/Milvus/provider/candidate write, runtime/query change,
  push, PR, or cutover occurred; Tasks 6.2–6.7 retain their declared ownership.
- Completed and accepted Task 6.2 as a strict test-only RED slice. Five scenarios freeze versioned,
  evidence-bound inclusion for approved/unapproved Professor seeds, roster/global Paper discovery,
  approved/unapproved Patent exports, Company skeleton/incremental/review/contrary scope, and
  query-time Web-only Companies through one future `DomainInclusionEngine` seam.
- Approved source scope is deterministic and content-bound to retained artifact hashes; results bind
  the manifest hash and tampering fails closed. Professor evaluation uses operator-approved seed
  membership without a runtime institution whitelist; Paper existence is independent of authorship;
  Patent export membership is not narrowed by topic/linkage/completeness; Company incremental
  admission requires four offline evidence dimensions while ambiguous evidence remains reviewable.
- The single merged review closed two Important evidence-binding findings. Focused normal/forced RED,
  no-database contract checks, Ruff, Pyright, strict OpenSpec, and diff/scope checks passed. No
  production code, migration, database/source/Candidate/Milvus/provider/runtime state changed;
  Task 6.3 owns GREEN implementation.
- Completed and accepted Task 6.6 in its independent worktree as a strict test-only RED slice. Five
  scenario families freeze four-domain partial exact reach, all eight cross-domain traversal
  directions, ordinary soft-quality behavior, path-scoped hard exclusions/merge redirect, and six
  published path decisions independent of global `ready`.
- The merged review repaired lifecycle/domain-status conflation, reversed canonical edge fixtures,
  global broken-reference poisoning, a false merged predecessor projection, and rejected
  Professor-Paper attribution leaking into Paper identity. Final tests consume future Task 6.3/6.5
  outputs as typed inputs without implementing or fabricating them.
- Focused normal/forced RED, 24 Accepted catalog/shared tests, Ruff, Pyright, strict OpenSpec, and
  diff/scope checks passed. No production/shared/migration/database/source/Candidate/Milvus/provider
  state changed; Tasks 6.3, 6.5, and 6.7 retain GREEN ownership.
