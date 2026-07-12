# Verification Contract: rebuild-canonical-v2-knowledge-platform

## Change

- Change ID: `rebuild-canonical-v2-knowledge-platform`
- OpenSpec path: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Run workspace: `.agents/runs/rebuild-canonical-v2-knowledge-platform/`

## Change Type

- `data_contract_or_storage`

## Superpowers Mode

- `contract_first`

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

## Status

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
The durable candidate remains C2_0004 with zero canonical/non-landing rows; Task 6.1 has not started.

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

### S8–S10 — Query, answer, and feedback

- Scenario eval and trace replay are mandatory RED/GREEN evidence; unit-only evidence is insufficient.
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
- for S2B, source/backup/restore identities, family completeness, copy independence, format-specific
  recovery probes, and the accepted backup-manifest hash;
- reviewer/acceptance status without claiming later-slice closure.

## Verification order

1. Static/OpenSpec validation.
2. Nearest pure/interface tests.
3. Complete backup manifest and independent recovery verification; accept S2B before any rebuild
   write.
4. Real isolated Postgres migration/integration tests.
5. Recorded adapter/trace replay scenarios.
6. Bounded isolated source/candidate replay.
7. Full versioned Milvus candidate and parity.
8. API/session/admin integration.
9. Frozen regression then challenge evaluation.
10. Named real-provider acceptance.
11. Rollback rehearsal and final evidence review.

## Stop conditions

- Original source pause/hash/identity changes unexpectedly.
- Any command resolves to a forbidden or ambiguous target.
- A hard invariant fails.
- A slice requires behavior absent from the OpenSpec capability.
- A later slice depends on a predecessor not marked Accepted.
- Threshold, corpus, schema, policy, or model version changes without a new versioned baseline.
- Verification evidence cannot distinguish local, current-Web, LLM inference, or release identity.
- A task 3.2+ or other rebuild-write command is proposed before complete S2B backup/restore evidence
  is reviewed and Accepted.
- Query/answer code attempts to create, merge, split, relink, or update canonical identities or
  source-identity mappings instead of emitting an offline review gap.

## Completion rule

The Epic reaches Candidate only when all slices are independently Accepted, every acceptance item is
evidenced, strict OpenSpec validation passes, and the complete isolated candidate passes the frozen
gates. Candidate does not authorize production-like cutover.
