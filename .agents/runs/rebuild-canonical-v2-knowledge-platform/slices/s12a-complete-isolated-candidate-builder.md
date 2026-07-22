# Slice Contract: S12A Complete Isolated Candidate Builder

## Status

Specified at `2026-07-20T11:17:04Z`; repaired into a reviewable Specified contract at
`2026-07-21T19:24:16Z`. S10O and aggregate S11C are Accepted, S11C receipt SHA-256 is
`281b28244a9fb5043a10df4e7eaa8f4e9e9385825babdae6204a461661a99717`, and the formal ledger is
`70/80`. This slice is still not Ready: no production/test/source-manifest implementation may start
until the remaining live migration/source/ownership gates pass and one independent lean Ready
review reports zero open Critical/Important findings. The preceding audit's `C3/I4` findings are
repaired in these three Specified artifacts; open Critical/Important is `0` pending that independent
review. Minor/YAGNI is recorded and nonblocking.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`.
- OpenSpec task to close after acceptance: `12.1` only.
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
content-addressed receipt. The method returns only after all stages agree and does not change or
discover an active release.

## Non-goals

- No Task `12.2` claim-level/multidimensional acceptance execution and no closure of Task `12.3`.
  Recovery/unresolved-gap/rollback/benchmark aggregation remains S12B after S2C/S8.8/S9.8.
- No Task `12.5` user acceptance and no Task `12.6` production-like Cutover, archive, promotion,
  alias/pointer movement, destructive cleanup, or source retirement.
- No live Web/LLM/embedding/reranking provider gate, latency/cost benchmark, new targeted
  recollection request, automatic recollection, or online-to-canonical write.
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
- Generate one S12A complete-candidate receipt only after a successful real isolated run.
- Update this contract, S12A audit/plan/receipt, and existing status/verification artifacts allowed
  by AGENTS.md after Candidate evidence. Check exactly Task `12.1` only after acceptance.

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
- Calling/exposing `promote` or `rollback`, checking Tasks `12.2`-`12.6`, Commit, Push, PR, archive,
  Cutover, or destructive cleanup.

## External interface and internal seams

The only external interface remains
`KnowledgeBuild.build(BuildCandidateRequest) -> CandidateRelease`. The isolated factory may accept
explicit target/source configuration and adapters, but callers do not receive or sequence internal
stages. Tests exercise the same build interface as the runner. `CompleteCandidateConsumerHandoff`
is a success artifact, not a second build interface: the injected receipt sink emits and reads it
back only after every private stage and the complete receipt succeed. It binds the exact
`CandidateRelease`, `IsolatedReleaseBundle`, `IndexProjectionRequest`, `InstitutionCatalog`, and
`ReleaseVerification` consumed by S11. The runner calls `build` exactly once, reads this sink-owned
handoff, and must not reconstruct or call a private build stage.

Internal seams are limited to dependencies that genuinely vary:

- fresh real local PostgreSQL, filesystem, and Milvus Lite adapters;
- recorded versus production offline decision/embedding adapters;
- deterministic versus real clock and receipt sinks.

The runner parses explicit configuration, creates adapters, calls `build` once, validates receipt
and handoff readback, and prints secret-free identities. In `--serve` mode it composes only the
existing Accepted S11 query-planner, release-read, answer, aggregate-runtime, and candidate-app
factories from the handoff. It uses recorded proposal, answer-selection, Web, sufficiency, and
supplemental adapters. It must not import/call landing, SQL, identity, build projection, index,
audit, verification, promotion, or rollback helpers directly.

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
  -> existing-schema durable candidate registry, typed projection persistence, and unresolved gaps
  -> fresh isolated full index materialization
  -> independent audit_isolated_index_snapshot complete physical inventory
  -> package-private ephemeral ReleasePublication.verify only
  -> content-addressed receipt readback
  -> return CandidateRelease
```

Every stage binds one release/build run/as-of/source/version/evidence graph. Caller-supplied stage
results are not trusted as authority: Accepted stage owners replay them. Exactly four public-domain
and three internal-auxiliary projection owners are retained. Internal Person/Technology remain
auxiliary, unresolved Person references do not become identities, and Product capability remains
answer-scoped.

The existing database schema is used without migration. After the pure candidate graph and expected
manifest are known, release/build-manifest/manifest-section identities are inserted atomically;
typed stage results use their Accepted stores, and gap drafts are persisted only after the candidate
registry exists. Equal replay is idempotent; same identity/different content fails. A failed later
stage may leave an isolated inspectable/retryable candidate, but no success receipt is emitted,
`build` raises, no active pointer changes, and retry uses a new fresh owned physical target instead
of overwriting the failed one.

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

`CompleteCandidateConsumerHandoff` and `CompleteCandidateBuildReceipt` round-trip the exact typed
`CandidateRelease`, `IsolatedReleaseBundle`, `IndexProjectionRequest`, `InstitutionCatalog`, and
accepted `ReleaseVerification`; all five share one release/manifest/projection/evidence graph. The
receipt binds each full canonical payload or its canonical content hash, and its candidate is
exactly the object returned by `KnowledgeBuild.build`. The sink emits no handoff on any failed
stage, failed receipt write, or failed receipt readback.

`complete_candidate_runner.py` supports `--serve --host 0.0.0.0 --port 18188`. After its sole
successful `build` call and sink readback, it creates a run-local, in-process `PublishedRelease`
view solely to satisfy the Accepted S11 read/runtime factories. That view is not persisted and is
not produced by `ReleasePublication.promote`; `publish.active_release`, aliases, and pointers remain
unchanged. The runner composes the existing isolated release planner/read factories,
`compose_canonical_v2_consumer_runtime`, and `create_canonical_v2_candidate_app` with recorded
proposal/answer/Web/sufficiency/supplemental adapters. It passes the app object to Uvicorn with
exactly one worker and reload disabled. It must not use an import string, child worker, startup
hook, or request path that can rebuild the candidate.

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
  verification/consumer-handoff/active-state/original-Milvus hashes and validates its own canonical
  content hash. Receipt output and sink readback are atomic, exact-typed, and secret-free.
- A failed build cleans up only not-yet-registered, explicitly S12A-owned scratch copies. A durable
  failed candidate, successful candidate, receipt, database, staging root, or index is retained for
  inspection/user testing until a separately recorded exact-owner cleanup. Serving shutdown never
  promotes, rolls back, drops, overwrites, or implicitly cleans a candidate.

## Expected unchanged behavior

- Accepted S1-S11 behavior and all existing deep module interfaces remain unchanged.
- Candidate construction cannot mutate active canonical/published/index state. `publish.active_release`
  is identical before/after (including absent/absent on a fresh target).
- Original PostgreSQL remains paused; original Milvus is never client-opened and retains its frozen
  hash. Restore/backup/source bytes are immutable.
- S2C and Tasks `8.1`, `8.8`, `9.8`, and `12.2`-`12.6` remain open.

## Required checks

- Exact normal/forced RED has eight groups: six build-interface groups plus two runner groups. Both
  owners import their absent target before external target setup; normal RED is exactly eight strict
  xfails and forced RED is exactly eight target-missing sentinel failures. Final owners have no
  xfail/XPASS.
- One fresh real PostgreSQL plus one fresh real Milvus Lite/lookup run proves the complete interface
  path, exact 50-source disposition, full 5,561-row batch, landing/authority/projection/registry/
  index/verification/receipt/handoff, and zero active/original effect.
- Runner owners prove one build call in both non-serving and serving paths, exact handoff-to-runtime
  wiring, the run-local-only PublishedRelease view, recorded Web-capable question answering, app
  object serving at `0.0.0.0:18188`, one worker/no reload, and zero promotion/pointer/private-stage
  calls.
- Hostile source, target, lineage, cross-release, replay/collision, stage-failure, physical-drift,
  and receipt-tamper cases fail at the named stage with no later effect.
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

- This Slice Contract, S12A audit/plan, source-build manifest, and complete-candidate receipt.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md` with exact commands/results,
  live target identities, source/gap/projection/registry/index hashes, active-state snapshots,
  original-source checks, package hash, and reviewer conclusion.
- After acceptance only: check exactly Task `12.1`; update matching OpenSpec/current status artifacts
  with a live `+1` ledger delta.
- Task `12.3` remains S12B-owned even though the receipt is an input to its aggregate evidence.
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
  zero-deviation verification, content-valid receipt, unchanged active state, or frozen originals.
- A runner/test must sequence private stages, hide RED behind skip/xfail, weaken an Accepted owner,
  delete/overwrite an owned failed target, or leave a Critical/Important finding open.

## Done means

- The exact Accepted 50-source authority is dispositioned, every admitted input is copied/landed
  with verified lineage, the complete released-objects batch is mapped under the frozen policy, and
  every malformed/unmapped input remains a typed unresolved gap.
- One call to the real deep `KnowledgeBuild.build` returns a complete isolated candidate whose
  typed projections, durable registry, fresh physical indexes, exact verification, and content
  receipt all agree.
- Original/active state is unchanged, failure/replay behavior is inspectable and safe, all Required
  checks pass, the exact success handoff can serve the candidate on the run-local S11 app without a
  second build or publication, and final review has zero open Critical/Important findings.
- S12A and exactly Task `12.1` are Accepted. Tasks `12.2`-`12.6` remain open for S12B/user/Cutover.

## Rollback note

Before acceptance, delete only the five S12A implementation/run files and the S12A-owned generated
receipt; drop/remove only explicitly named S12A-owned disposable database, staging, and index
resources. After acceptance, also restore exactly Task `12.1` and its status/evidence entries. Never
rewrite migrations, delete nonempty predecessor/source evidence, open original Milvus, start
original PostgreSQL, move a release pointer, or perform production-like cleanup.
