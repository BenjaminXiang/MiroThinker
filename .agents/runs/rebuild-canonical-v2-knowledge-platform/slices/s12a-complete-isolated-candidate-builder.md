# Slice Contract: S12A Complete Isolated Candidate Builder

## Status

Accepted at `2026-07-23` after the fresh isolated r12 build, complete system checks, two independent
source/safety reviews, and an independent envelope/PostgreSQL/physical-index evidence audit. The
final implementation, test, runner, and runner-test SHA-256 values are
`85b4ca8b89bb1e9c8870957933002e270e59916b8367f443d3ee267932298efa`,
`d8c8174f31d226468c8b7fe85fd543c022ea74f7cb88a461d1b33dd98753dff4`,
`0279b2428c11bd07fa7debbed81705712fc25b5938ec1f0c2aa35eaab82fa682`, and
`a85ea8da306b665550f668a6aaeec83db5cff1f4701919f4492044ac62b59403`. The focused
builder/runner matrix reports `104 passed`; the Task 12.1 owner matrix reports `169 passed, 2
skipped`; complete no-external Canonical V2 reports `542 passed, 148 skipped, 3 warnings`; and the
identity/domain prerequisite matrix reports `87 passed`. Task `12.1` is checked and the task ledger
is `71/80`; acceptance remains `49/97` because no aggregate S12 acceptance item is satisfied by the
build-only slice. Tasks `12.2`-`12.6`, active state, original sources, production resources, and
local Git history remain unchanged. The required local checkpoint commit is not authorized by the
current user instruction and therefore remains uncreated.

## Current Candidate evidence

- Release/run: `candidate-s12a-20260723-r12` / `s12a-build-20260723-r12`.
- Envelope raw SHA-256: `a2684f9b9bd42c8727625fa7e057f654c6539a6e97924eccfdfb913fdfef9cbc`;
  canonical envelope/receipt/handoff hashes:
  `77cde16c037aec888e07a677b3f96effd27a75f3eeb68a4f38c5fdb2a6a88383`,
  `5ae974b6af80980864bac751812b12fb7c468a4449331db4a85b47c4453437a8`, and
  `f18af1854a92ef2d76816a8f3f3a9a724fb5ab233de6020f9c161c5100cf00bc`.
- Source outcome: 5,561 landing records; 1,037 Company projections; zero Paper, Patent, Professor,
  and relationship projections; 5,561 evidence-bound typed gaps. The 580 historical
  `professor_paper_link` rows lacked accepted endpoint authority and therefore remain gaps rather
  than fabricated relationships.
- Independent physical readback on a byte-exact temporary copy: 1,037 Milvus points and 1,037
  lookup documents, 8 vector and 7 lookup manifests, physical snapshot SHA-256
  `20cc5fd309056f714e09038465d3cec805e239752f1b709e0e92ba269f46cabe`, and accepted release parity
  with zero missing, extra, stale, or cross-release points. The durable registry SHA-256 is
  `5092f40fb0759dd69a297fa505b8cb50ab09fbac39d7209e602c69cffea3732f`.
- `publish.active_release` is absent before and after. Original PostgreSQL remains paused and
  original Milvus was not opened or rehashed.
- Evidence copy:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-envelope-r12.json`.
  r10 and r11 are retained historical evidence and are not current authority; the unsuffixed r6
  envelope was restored byte-for-byte.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`.
- OpenSpec task closed by this acceptance: `12.1` only.
- Requirements: immutable verified source copies and landing, offline identity/canonical authority,
  typed four-domain plus internal projections, one immutable candidate manifest, full isolated
  index, deterministic parity, frozen originals, and no active-release effect.
- Depends on: Accepted S2B/S3-S7, Accepted S10O, and Accepted aggregate S11C.
- Does not depend on: S2C/Task `2.8` or aggregate Tasks `8.1`, `8.8`, and `9.8`.
- Audit: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/dependency-audit.md`.
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/implementation-plan.md`.

## Goal

Provide one deep isolated implementation of the existing interface:

```python
builder: KnowledgeBuild = create_isolated_knowledge_build(...)
candidate: CandidateRelease = builder.build(
    BuildCandidateRequest(
        run_id=run_id,
        candidate_release_id=release_id,
        source_batch_ids=source_batch_ids,
        parser_versions=parser_versions,
        policy_versions=policy_versions,
        model_versions=model_versions,
    )
)
```

That single call must own verified accepted-copy staging, immutable landing, retained source
authority and typed unresolved gaps, canonical/identity/domain/internal-reference/relationship/
eligibility projection, immutable candidate/manifest construction, durable registry, fresh full
lookup/Milvus build, complete physical audit, exact `ReleasePublication.verify`, and one
content-addressed receipt/handoff envelope. The method returns only after all stages agree and does
not change or discover an active release.

## Non-goals

- No Task `12.2` claim-level/multidimensional acceptance execution and no closure of Task `12.3`.
  Recovery/unresolved-gap/rollback/benchmark aggregation remains S12B after S2C/S8.8/S9.8.
- No Task `12.5` user acceptance and no Task `12.6` production-like Cutover, archive, promotion,
  alias/pointer movement, destructive cleanup, or source retirement.
- No live Web/LLM/embedding/reranking provider gate, latency/cost benchmark, new targeted
  recollection request, automatic recollection, or online-to-canonical write.
- No production serving bundle or live query/answer/Web gate. Those are Task `12.2`; production
  `--serve` fails closed before builder construction until that bundle exists. The injected serving
  test verifies only the composition interface and does not claim a production serving artifact.
- No new migration/schema, workflow engine, distributed transaction coordinator, resumable generic
  DAG, plugin registry, scheduler, queue, automatic retry/cleanup/retirement framework, or generic
  release manager.
- No second public build interface, per-stage caller methods, direct runner orchestration, legacy
  compatibility layer, V042 IDs/tables/collection names, or fifth public domain.

## Allowed scope

- Create `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py`.
- Create `apps/miroflow-agent/tests/canonical_v2/test_knowledge_build_isolated.py`.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/source-build-manifest-v1.json`
  only after this slice becomes Ready.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py`
  and its adjacent `test_complete_candidate_runner.py` only after Ready.
- Generate one S12A complete-candidate receipt/handoff envelope only after a successful real
  isolated run.
- Update this contract, S12A audit/plan/envelope, and existing status/verification artifacts allowed
  by AGENTS.md after Candidate evidence. Check exactly Task `12.1` only after acceptance.
- After Task `12.1` is Accepted, create exactly one local task commit on the S12A branch. No Push or
  PR is authorized.

## Forbidden changes

- `knowledge_build.py`, shared `contracts.py`, Accepted landing/identity/decision/domain/internal-
  reference/relationship/eligibility/index/release/gap modules or their behavior-owning tests.
- Any historical or new Alembic migration; the builder uses the live existing single head on a fresh
  disposable database.
- S2/S2B evidence, source inventory, backup/restore/acceptance bytes, original PostgreSQL/Milvus,
  forensic sources, S7 acceptance targets, active aliases/pointers, or production-like resources.
- Generic `DATABASE_URL`, `DATABASE_URL_TEST`, `MILVUS_URI`, latest/active release discovery,
  relative/network/unmarked/reused targets, original/protected source paths, symlinks, or implicit
  environment fallback.
- Treating PRD/spec/test/corpus prose as factual source rows; inventing parent records, identities,
  facts, relationships, content, eligibility, points, evidence, or recovered bytes.
- Calling/exposing `promote` or `rollback`, checking Tasks `12.2`-`12.6`, Push, PR, archive, Cutover,
  or destructive cleanup. A local commit is permitted only for the Accepted Task `12.1` checkpoint.

## External interface and internal seams

The only external interface remains
`KnowledgeBuild.build(BuildCandidateRequest) -> CandidateRelease`. The isolated factory may accept
explicit target/source configuration and adapters, but callers do not receive or sequence internal
stages. Tests exercise the same build interface as the runner. `CompleteCandidateConsumerHandoff`
is a success artifact, not a second build interface. `CompleteCandidateBuildEnvelope` is the only
durable success file: it contains the typed receipt and handoff, has one canonical content hash, and
is published once without replacement and read back by the injected sink only after every private
stage succeeds.
The handoff binds the exact `CandidateRelease`, `IsolatedReleaseBundle`, `IndexProjectionRequest`,
`InstitutionCatalog`, and `ReleaseVerification` consumed by S11. The runner calls `build` exactly
once, reads this sink-owned handoff, and must not reconstruct or call a private build stage.

Internal seams are limited to dependencies that genuinely vary:

- fresh real local PostgreSQL, filesystem, and Milvus Lite adapters;
- recorded versus production offline decision/embedding adapters;
- deterministic versus real clock and single-envelope sinks.

The runner parses explicit configuration, creates adapters, calls `build` once, validates the one
envelope readback, and prints secret-free receipt/handoff identities. Its injected `--serve` seam
proves that a later Task `12.2` serving bundle can consume the exact handoff without a second build.
The production CLI rejects `--serve` during dependency preflight because Task `12.1` does not own
the recorded proposal/answer/Web/sufficiency/supplemental bundle or live query/answer gates. It must
not import/call landing, SQL, identity, build projection, index, audit, verification, promotion, or
rollback helpers directly.

## Source-build manifest contract

`source-build-manifest-v1.json` must:

1. bind these exact accepted S2B hashes: source inventory
   `83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09`, backup manifest
   `a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8`, restore verification
   `98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231`, and acceptance record
   `3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b`;
2. treat the Accepted backup manifest's exact 50 `sources` records as source authority: its first 48
   `inventory:*` records plus `original_postgresql_volume` and `forensic_recovery_tree`. The
   48-entry inventory is a bound input, not the complete source-ID authority;
3. contain exactly one sorted unique disposition for all 50 source IDs, with exact counts
   `requirements_only=7`, `acceptance_only=7`, `evidence_input=1`, `protection_only=5`,
   `registered_unprojected=30`, and `unrecoverable=0`. The exact source-ID mapping is the table in
   the S12A dependency audit;
4. admit only
   `inventory:ffe87de3fe5cefe929194235d43fe7bcf09be406976a81cea23efb464d4d34a0`
   as `evidence_input`. It binds restore member
   `workspace/logs/data_agents/released_objects.db`, size `20267008`, SHA-256
   `7637d808559685f1bcf0316cd22cfeac4e50bd0850c53652ec95b3dbb5e43bce`, backup member manifest
   `manifests/inventory/027-ffe87de3fe5cefe929194235d43fe7bcf09be406976a81cea23efb464d4d34a0.jsonl`
   at SHA-256 `6820786a2e055def2828c82de60f3b90cad9ac5dcc8f1477943a9f46a02777ae`,
   and source-member-manifest SHA-256
   `4c91d1d7dce88e5c9d9924b2c21d6f3111292eb3e5c30a60e688fd40ccf8b594`;
5. bind that evidence input to a new S12A full-batch `released_objects` table declaration with no
   row limit: exactly 5,561 rows — `company=1037`, `paper=574`, `patent=1931`, `professor=1439`,
   `professor_paper_link=580`. S4D's five-row bounded replay and P1's five-row preview are evidence
   patterns only and cannot be reused as S12A batch authority;
6. freeze the versioned released-objects assertion/projection/gap mapper policy described below;
7. hold targeted recollection in a separate collection, require an approval reference and immutable
   staging-member identity for every entry, and allow none when no recollection has been approved;
8. name a durable typed gap and exact limitation for each unrecoverable input; the Accepted 50-source
   set has exactly zero such entries; and
9. carry a canonical-JSON content hash over the complete document.

Missing/extra/duplicate Accepted backup-manifest source IDs, duplicate source/recollection/member/
batch identity, any disposition-count or exact-mapping mismatch, unsupported parser/source kind,
tampered hash/size/lineage, ambiguous roots, original/protected/symlink/hard-link input, or
request/manifest batch/version disagreement fails before landing or downstream effects.
`requirements_only`, `acceptance_only`, `protection_only`, and `registered_unprojected` never enter
landing or become source assertions. Protection-only bytes are never opened by S12A.

## Released-objects mapper policy

The manifest freezes one content-addressed mapper policy version for the sole evidence input. The
implementation uses an S12A-private full-table reader on a candidate-owned verified copy in SQLite
read-only immutable mode. It reuses the Accepted schema-introspection rules, requires the exact
`released_objects` table and one stable single-column primary key, quotes the introspected table and
primary-key identifiers, and executes a deterministic primary-key `ORDER BY` with no `LIMIT`. It
must not use the Accepted `HistoricalSqliteAdapter` unordered no-limit path, must not assume an `id`
column, and must not modify that Accepted adapter. Missing/ambiguous/composite primary-key or schema
drift fails before landing; exact row/type-count drift fails before projection.

- Every admitted row is historical published evidence, never canonical truth. Its payload and
  evidence locators may create retained historical assertions, but only Accepted canonical decision
  and identity owners may create current canonical selections or assignments.
- A manifest-pinned allowlist maps only `company`, `paper`, `patent`, `professor`, and
  `professor_paper_link` fields into the Accepted four public-domain, identity, decision,
  relationship, eligibility, and index-projection owners. The mapper cannot construct a public
  projection directly or pass unallowlisted/private/local-path fields.
- A relationship exists only when a policy-listed source field names both explicit typed endpoint
  IDs and both endpoints resolve through the same release's Accepted identity/domain results.
  Display names, co-occurrence, summary prose, arrays without an allowed relationship mapping, or
  inferred parents cannot supply endpoints.
- Product capability remains answer-scoped. The mapper creates no Product entity/capability
  projection and no placeholder identity, parent, fact, relationship, evidence, or point.
- Duplicate identity, malformed JSON/schema/time/evidence, unsupported object type, disallowed
  field, missing or cross-release endpoint, unresolved identity, and otherwise unmapped row/field
  produce retained readable evidence where safe plus a typed S10O gap with the exact row/field/path
  reason. They cannot be silently dropped, coerced into a different domain, or counted as a valid
  projection.

## Build and durable-registry contract

The implementation owns this exact sequence:

```text
gate/request/manifest/target validation
  -> verified candidate-owned copies
  -> EvidenceLanding ingest and exact stream replay
  -> source assertions/decisions/identity and typed gap drafts
  -> public/internal/relationship/eligibility projections
  -> pure full-index expectation
  -> existing KnowledgeBuild manifest/candidate construction
  -> existing-schema durable candidate registry, available typed-store persistence, and unresolved gaps
  -> fresh isolated full index materialization
  -> independent audit_isolated_index_snapshot complete physical inventory
  -> package-private ephemeral ReleasePublication.verify only
  -> exact five-artifact consumer handoff construction
  -> one no-overwrite content-addressed receipt/handoff envelope publication/readback
  -> return CandidateRelease
```

Every stage binds one release/build run/as-of/source/version/evidence graph. Caller-supplied stage
results are not trusted as authority: Accepted stage owners replay them. Exactly four public-domain
and three internal-auxiliary projection owners are retained. Internal Person/Technology remain
auxiliary, unresolved Person references do not become identities, and Product capability remains
answer-scoped.

The existing database schema is used without migration. After the pure candidate graph and expected
manifest are known, release/build-manifest/manifest-section identities are inserted atomically.
Identity, decision, domain, and relationship results use their Accepted PostgreSQL stores. No
Accepted PostgreSQL store exists for `InternalReferenceProjectionResult` or
`PathEligibilityResult`; S12A therefore persists their complete content hashes in manifest sections
and retains their exact typed payloads only in the final envelope/handoff. It must not invent tables,
serialize them into unrelated columns, or claim full PostgreSQL persistence. Gap drafts are
persisted only after the candidate registry exists. Accepted store-level equal replay remains
idempotent and conflicting content identity fails inside one build, but the top-level `build` call
is single-use for one fresh physical target set. A second top-level call against the same database,
staging root, or index root fails the freshness gate before input or write. A failed later stage may
leave an isolated inspectable candidate, but no success envelope is emitted, `build` raises, no
active pointer changes, and retry uses a new release/run identity and new fresh owned physical
targets instead of overwriting the failed one.

## Failure and gap contract

- Gate, target, path, content, lineage, release, manifest, registry, point, or receipt mismatch stops
  before the next effect and cannot be converted into success by aggregate hashes.
- Partial/quarantined parser output retains readable evidence plus typed errors. No placeholder fact
  or relationship may satisfy a downstream projection.
- `unrecoverable` or materially insufficient evidence creates/persists an unresolved S10O gap bound
  to source/release/run/domain/path evidence. S12A cannot close it.
- Recorded decision/embedding failure leaves the candidate unpublished and retryable; provider/model
  output cannot create evidence or mutate active canonical state.
- Physical verification first uses `audit_isolated_index_snapshot` to enumerate actual lookup
  documents and Milvus points independently of the claimed receipt, then uses the Accepted
  package-private `create_ephemeral_release_publication(...).verify(candidate_release_id)` for exact
  S7F reconciliation. The fresh absent-active target must not use the isolated publication wrapper,
  which requires prior/candidate registries and exactly one active release. Any missing/extra/stale/
  cross-release item produces a rejected verification and blocks the final receipt. The ephemeral
  publication object is not exposed and neither `promote` nor `rollback` is called.

## Consumer handoff and run-local serving

`CompleteCandidateConsumerHandoff` and `CompleteCandidateBuildReceipt` are fields of one
`CompleteCandidateBuildEnvelope`. Together they round-trip the exact typed
`CandidateRelease`, `IsolatedReleaseBundle`, `IndexProjectionRequest`, `InstitutionCatalog`, and
accepted `ReleaseVerification`; all five share one release/manifest/projection/evidence graph. The
exact internal-reference and path-eligibility results are nested in `IndexProjectionRequest`; the
handoff therefore retains both typed payloads without a new store. The receipt binds the handoff
content hash. The envelope carries both complete typed values and its own canonical hash. One sink
operation writes and fsyncs one temporary envelope, then publishes it with a same-filesystem
no-overwrite hard link, fsyncs the directory, reads that same file back, and rejects any collision
or cross-wire before `build` returns the exact candidate. No success envelope exists after a failed
stage, failed no-overwrite publication, or failed readback.

`complete_candidate_runner.py` accepts the `--serve --host 0.0.0.0 --port 18188` interface for
dependency-injected wiring tests, but production dependency resolution intentionally fails closed
before builder construction. Task `12.2` owns the content-addressed serving bundle and the real
query/answer/Web gates. Neither path persists a `PublishedRelease`, calls promotion, changes
`publish.active_release`, or permits a request/startup hook to rebuild the candidate.

## Target and receipt contract

- Database target: explicit URL and identity, exact `disposable` marker, fresh at build start, live
  existing migration head, no generic environment fallback.
- Index target: absolute marked `isolated-candidate` root, same release ID, fresh/no pre-existing
  lookup or Milvus file, non-network, non-symlink, distinct from original and retained targets.
- Candidate staging: absolute, fresh, explicitly owned, outside original/backup roots; inputs come
  only from the accepted restore root or an approved recollection root.
- Candidate staging contains a machine-validated marker with exactly marker schema/version,
  `run_id`, `candidate_release_id`, and `source_manifest_sha256`; all copies remain beneath that
  marked root. Failure retains a durable target, and later cleanup requires the same exact marker.
- The evidence copy resolves only the manifest-bound member beneath the Accepted restore root and
  verifies its Accepted backup member-manifest path/size/hash record. It uses `O_NOFOLLOW`, stable
  pre/post `fstat` identity, streaming hash/copy, and distinct restore/staging inode identity.
  Production code must not import `.agents` S2B/S4D helpers; the S4D helper opens original source
  paths and is forbidden here.
- Gate checks occur before any input read, before the first database write, and immediately before
  the first index write.
- Receipt binds exact gate/source/landing/gap/authority/projection/registry/index/physical-audit/
  verification/consumer-handoff/active-state/frozen-original-Milvus identities. The receipt and
  handoff are contained by one canonical envelope that validates its own content hash. The
  original-Milvus identity is copied only from the Accepted S2/S2B content-addressed records; S12A
  never reopens or rehashes the original bytes. Envelope output/readback is one-file,
  no-overwrite, exact-typed, and secret-free.
- A failed build cleans up only not-yet-registered, explicitly S12A-owned scratch copies. A durable
  failed candidate, successful candidate, envelope, database, staging root, or index is retained for
  inspection/user testing until a separately recorded exact-owner cleanup. Serving shutdown never
  promotes, rolls back, drops, overwrites, or implicitly cleans a candidate.

## Expected unchanged behavior

- Accepted S1-S11 behavior and all existing deep module interfaces remain unchanged.
- Candidate construction cannot mutate active canonical/published/index state. `publish.active_release`
  is identical before/after (including absent/absent on a fresh target).
- Original PostgreSQL remains paused; original Milvus is never opened or rehashed by S12A. Its
  frozen hash identity comes only from Accepted S2/S2B evidence. Restore/backup/source bytes are
  immutable.
- S2C and Tasks `8.1`, `8.8`, `9.8`, and `12.2`-`12.6` remain open.

## Required checks

- Exact normal/forced RED has eight groups: six build-interface groups plus two runner groups. Both
  owners import their absent target before external target setup; normal RED is exactly eight strict
  xfails and forced RED is exactly eight target-missing sentinel failures. Final owners have no
  xfail/XPASS.
- One fresh real PostgreSQL plus one fresh real Milvus Lite/lookup run proves the complete interface
  path, exact 50-source disposition, full 5,561-row batch, landing/authority/projection/registry/
  index/verification/single-envelope receipt/handoff, and zero active/original effect.
- Runner owners prove one build call in the normal path, fail-closed production serving preflight,
  injected handoff-to-runtime wiring at `0.0.0.0:18188`, one worker/no reload, and zero promotion,
  pointer, or private-stage calls. They do not claim the Task `12.2` serving bundle or live gates.
- Hostile source, target, lineage, cross-release, replay/collision, stage-failure, physical-drift,
  and envelope-tamper cases fail at the named stage with no later effect.
- Unrecoverable/partial evidence remains explicit and creates typed gaps without fabricated rows or
  points.
- Existing KnowledgeBuild, projection, physical-audit, ReleasePublication, durable-gap, and consumer
  acceptance owners remain GREEN. Complete no-external Canonical V2 has no unexpected failure.
- Ruff check/format, `py_compile`, complete applicable Pyright, strict OpenSpec, `git diff --check`,
  fresh locked-offline wheel/source parity, scope/secret/cache, migration-head, source-manifest, and
  frozen-target checks pass.
- One merged final implementation/test-integrity review reports zero open Critical/Important
  findings. Minor/YAGNI is recorded and nonblocking.

## Evidence to update

- This Slice Contract, S12A audit/plan, source-build manifest, and complete-candidate envelope.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md` with exact commands/results,
  live target identities, source/gap/projection/registry/index hashes, active-state snapshots,
  original-source checks, package hash, and reviewer conclusion.
- After acceptance only: check exactly Task `12.1`; update matching OpenSpec/current status artifacts
  with a live `+1` ledger delta.
- Task `12.3` remains S12B-owned even though the envelope receipt is an input to its aggregate evidence.
  Task `12.4` may record pre-run checks but remains unchecked; Task `12.5` requires user acceptance;
  Task `12.6` requires separate explicit Cutover authorization.

## Stop conditions

- S10O or S11C is not Accepted, the migration graph is not one head, a planned file has another
  writer, or accepted source/gate/frozen-target identity changed.
- Correct construction requires a shared/OpenSpec behavior change, new schema/migration, unapproved
  recollection, original/protected source read, live provider authority, legacy consumer path,
  promotion/pointer change, or production-like target.
- The source manifest cannot account exactly for Accepted source authority, the fixed
  `7/7/1/5/30/0` disposition, or the full 5,561-row table; a non-evidence input would enter landing;
  a historical row would become canonical truth without Accepted owners; an unresolved row cannot
  remain an explicit gap; or a placeholder is required to satisfy a typed projection.
- Builder success can occur without durable registry readback, complete physical inventory, accepted
  zero-deviation verification, content-valid envelope, unchanged active state, or frozen originals.
- A runner/test must sequence private stages, hide RED behind skip/xfail, weaken an Accepted owner,
  delete/overwrite an owned failed target, or leave a Critical/Important finding open.

## Candidate and acceptance gate

- The exact Accepted 50-source authority is dispositioned, every admitted input is copied/landed
  with verified lineage, the complete released-objects batch is mapped under the frozen policy, and
  every malformed/unmapped input remains a typed unresolved gap.
- One call to the real deep `KnowledgeBuild.build` returns a complete isolated candidate whose
  typed projections, durable registry, fresh physical indexes, exact verification, and content
  receipt/handoff envelope all agree.
- Original/active state is unchanged, failure/replay behavior is inspectable and safe, all Required
  Task `12.1` checks pass, and the exact success handoff is ready for Task `12.2` without a second
  build or publication.
- The r12 independent/system review supplied that separate decision on `2026-07-23`. S12A and
  exactly Task `12.1` are Accepted; Tasks `12.2`-`12.6` remain open for S12B/user/Cutover.

## Rollback note

Before acceptance, delete only the five S12A implementation/run files and the S12A-owned generated
envelope; drop/remove only explicitly named S12A-owned disposable database, staging, and index
resources. After acceptance, also restore exactly Task `12.1` and its status/evidence entries. Never
rewrite migrations, delete nonempty predecessor/source evidence, open original Milvus, start
original PostgreSQL, move a release pointer, or perform production-like cleanup.
