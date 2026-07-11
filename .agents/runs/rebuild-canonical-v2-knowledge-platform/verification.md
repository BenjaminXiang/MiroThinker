# Verification: rebuild-canonical-v2-knowledge-platform

## Current status

S1 database-target safety was accepted by the user at 2026-07-11T05:39:19Z. Explicit user acceptance
of S2 tasks 2.1–2.5, including the corpus ground-truth policy and threshold Candidate, was recorded
at 2026-07-11T15:10:32Z. S2B/task 2.6 was objectively verified and Accepted at
2026-07-11T16:11:23Z under the user's self-approval authorization. Task 3.1's RED interface
contracts were Accepted at `2026-07-11T16:31:48Z`. After re-verifying that gate, Task 3.2's empty
Canonical V2 namespace baseline was Accepted at `2026-07-11T16:58:23Z`. Task 3.3's shared typed
contracts were Accepted at `2026-07-11T17:15:42Z`. Task 3.4's C2_0002 shared schema was Accepted at
`2026-07-11T17:48:21Z`. Task 3.5 independently reviewed, repaired, and Accepted the complete S3
foundation at `2026-07-11T18:22:18Z`; the isolated candidate is at reviewed head C2_0003 with zero
business rows. Task 4.1 is next but has not started; no landing evidence, publication projection, or
index write has begun.

## Existing incident/recovery checkpoint used as planning evidence

- Original `pgtest` was last verified paused; recovery work uses an isolated network-none lab.
- Forensic source/copy manifests and a verified partial FPI salvage dump exist outside the repository
  under `/home/longxiang/.mirothinker_recovery/20260711T022932Z-pgtest-forensic-freeze/`.
- A salvage-only isolated candidate checkpoint was restored and hash-checked before this change.
- These facts establish available evidence inputs; they do not accept Canonical V2, source coverage,
  or production parity.

## Spec evidence

- Requirements grill: `.agents/runs/canonical-v2-logical-rebuild/requirements-grill.md`
- Effect baseline: `.agents/runs/canonical-v2-logical-rebuild/outcome-requirements.md`
- Domain glossary: `CONTEXT.md`
- OpenSpec: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`

## S1 evidence checkpoint — 2026-07-11T05:05:30Z

- `docker inspect` reported `pgtest status=paused paused=true running=true`; host port remains
  `15432`, which is forbidden for S1 commands.
- Source volume identity matched
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`.
- `pgtest-recovery-lab-01` reported `network=none` and no ports.
- Original Milvus hash matched
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Verified salvage dump hash matched
  `cef8eb6ba18ebd23fde3e47023222ecb82bc8f27582040efe5a212a7f9fdfbb7`.
- Verification/slice contract and forbidden target rules exist. Tasks 1.1 and 1.2 are documentation
  complete; no implementation acceptance is claimed.
- S1 slice contract:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s1-database-target-safety.md`.

## S1 implementation evidence — 2026-07-11T05:37:16Z

### Candidate implementation

- Isolated code worktree: `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s1`, branch
  `canonical-v2-s1-safety`, based on `c0f3db2`; no commit or push was created.
- `src/data_agents/storage/database_target.py` defines one fail-closed destructive-target resolver.
  It accepts only Alembic config or dedicated `ALEMBIC_*` values for URL, expected database name,
  and target kind. Generic `DATABASE_URL` and `DATABASE_URL_TEST` are not migration inputs.
- The resolver rejects missing or conflicting explicit inputs, URL/name mismatch, unsupported target
  kind, system/real/recovery-checkpoint database identities, and host port `15432` before engine
  creation.
- `alembic/env.py` verifies `SELECT current_database()` after connecting and before configuring or
  running migrations. It also requires the database-side comment marker
  `miroflow:destructive-target:v1:<kind>:<database-name>`, then ends the identity queries' implicit
  read transaction before Alembic begins its migration transaction.
- The repository sibling search found one autocommit destructive test path that bypassed Alembic:
  `tests/postgres_seed_loader/test_seed_loader.py` used generic fallback before `DROP SCHEMA ...
  CASCADE`. It now resolves the same dedicated target and checks database name/marker before any
  schema DDL. Other located TRUNCATE/DELETE migration-test paths first cross the Alembic boundary;
  rollback-only/read-only database tests were not broadened.
- `alembic.ini` documents the explicit invocation contract. Historical migrations and ordinary
  runtime connection behavior were not changed.

### RED evidence

Command:

```text
cd apps/miroflow-agent
uv run pytest tests/storage/test_database_target_safety.py -n0 -q
```

Initial pre-implementation result: exit `1`, seven intended failures. The observed behaviors were generic
real URL precedence, acceptance of generic-only and known-real targets, no ambiguity/name/connected
identity checks, and rejection of an otherwise approved explicit target because the old environment
contract ignored it.

Self-review then identified that caller-provided kind/name was an attestation rather than independent
database-side proof. Two added RED cases (missing marker and wrong-kind marker) both failed because
the candidate still permitted migrations. Both became GREEN only after server-side marker checking
was implemented.

The sibling seed-loader regression also failed RED because a generic-only `DATABASE_URL` was still
accepted for an autocommit schema-drop fixture. It became GREEN after the fixture reused the shared
target resolver and database-side identity proof.

During real-Postgres validation, the first apparent V001→V042 run exited `0` but the target remained
at zero public tables. Read-only TCP/Unix-socket identity checks proved both paths addressed the same
database/OID/data directory. Root cause was the new identity `SELECT` opening a SQLAlchemy implicit
transaction that rolled back the migration transaction when the connection closed. A regression
assertion for ending that read transaction failed `0 == 1` before the one-line transaction-boundary
fix.

### Pure GREEN evidence

```text
uv run pytest tests/storage/test_database_target_safety.py -n0 -q
```

Final focused command in the lab network namespace:

```text
pytest tests/storage/test_database_target_safety.py \
  tests/postgres_seed_loader/test_seed_loader.py -n0 -q
```

Result: exit `0`, `15 passed`. The nine target-contract cases cover conflicting generic URL,
generic-only input, known non-disposable target, conflicting explicit sources, URL/expected-name
mismatch, connected database identity mismatch, missing/wrong database marker, and approved target
transaction cleanup. Six seed-loader cases cover its generic fallback rejection plus real
schema-drop/create cleanup and loader behavior on the proven disposable target.

Fail-closed CLI probes used an unresolvable host to prove no connection was required:

```text
generic_only_fail_closed=yes status=1
forbidden_explicit_fail_closed=yes status=1
wrong_database_marker_fail_closed=yes status=1
```

All probes matched the target-safety error rather than a DNS/connection error.

### Real isolated Postgres GREEN evidence

- Recovery lab: `pgtest-recovery-lab-01`, network `none`, no exposed ports.
- Newly created target: `miroflow_s1_disposable_20260711a`; it did not exist before this run and is
  distinct from both recovery checkpoint databases.
- Connection execution used the lab network namespace and `127.0.0.1:5432`; the explicit expected
  database was the same disposable name, target kind was `disposable`, and the database comment was
  `miroflow:destructive-target:v1:disposable:miroflow_s1_disposable_20260711a`.
- Before provisioning that exact marker, a real `alembic current` probe failed closed. After marker
  provisioning it returned `V042 (head)`; the marker persisted through downgrade and re-upgrade.
- Pre-upgrade: target identity matched, no Alembic revision, zero public tables.
- Upgrade: V001→V042 exited `0`; database state then reported V042, 42 public tables, and zero rows
  in each of `company`, `professor`, `paper`, and `patent`.
- Downgrade: V042→base exited `0`; database state contained only Alembic's empty version table.
- Second upgrade: V001→V042 exited `0`; final database state again reported V042, 42 public tables,
  and zero rows in all four domain tables.
- The real seed-loader suite exited `0` with six passes. Post-suite state remained V042 with 42
  public tables, no `seed_loader_test`/`seed_loader_empty_probe` schemas, and zero rows in the four
  domain tables.
- Final named database inventory still contained the two untouched recovery checkpoints plus the one
  new S1 disposable target.

### Static and source-invariant evidence

```text
uv run ruff check alembic/env.py src/data_agents/storage/database_target.py \
  tests/storage/test_database_target_safety.py \
  tests/postgres_seed_loader/test_seed_loader.py
# All checks passed

uv run pyright alembic/env.py src/data_agents/storage/database_target.py \
  tests/storage/test_database_target_safety.py \
  tests/postgres_seed_loader/test_seed_loader.py
# 0 errors, 0 warnings, 0 informations

git diff --check
# exit 0
```

Post-run read-only checks at `2026-07-11T05:37:16Z`:

- `pgtest`: `status=paused paused=true running=true`, port `15432`, source volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`.
- `pgtest-recovery-lab-01`: `status=running network=none ports={}`.
- Original Milvus SHA-256 remained
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Verified salvage dump SHA-256 remained
  `cef8eb6ba18ebd23fde3e47023222ecb82bc8f27582040efe5a212a7f9fdfbb7`.

### Scope and review state

- No original `pgtest` command, unpause, connection, migration, or write occurred.
- No Milvus client was opened; only the original file hash was read.
- No recovery checkpoint database was a migration or test target.
- No domain schema revision, writer, retrieval/chat behavior, dependency, benchmark, commit, or push
  changed.
- Tasks 1.3 and 1.4 are complete. The user accepted the reviewed Candidate evidence at
  2026-07-11T05:39:19Z, completing task 1.5 and removing the S1 gate for future S2 planning.

## Pending evidence

1. Task 4.1 remains Specified until its own independently testable Ready slice is created.

## S2 task 2.1 source inventory — 2026-07-11T07:11:30Z

- Branch/worktree: `canonical-v2-s2-baseline` at accepted S1 commit
  `a58184cee8d616cbcfc58c942f1b07790fc6ffdb`.
- Builder version: `canonical-v2-s2-source-inventory-builder-v1`; builder SHA-256
  `b94c29d6ec177df0dc43419e486e27eb1f6b55637abe05c868378cc57f85150c`.
- Inventory: `s2/source-inventory.json`, 48 source/family records, SHA-256
  `83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09`.
- Five TDD contract tests passed after observed RED failures. They prove byte hashing without source
  mutation, immutable/read-only SQLite access, Milvus-like hash-only treatment, deterministic family
  manifests, and committed/ignored/recovery/database source merging.
- Repeated full generation with identical inputs was byte-identical (`cmp` exit `0`).
- Recovery sessions used `PGOPTIONS=-c default_transaction_read_only=on` and proved current database,
  `transaction_read_only=on`, and data directory before counts. Both recovery checkpoints are V042
  with 42 empty public-domain tables and four salvage tables.
- Salvage counts: 99,437 distinct Papers; 101,158 distinct Professor-Paper links covering 2,826
  Professor source IDs and 97,285 Paper IDs; 20,773 field errors; 10 metadata rows.
- Large historical families include 11,604 Professor fetch-cache files, 26,185 OpenAlex cache files,
  351 SQLite snapshots, 1,544 data-agent JSONL files, 2,657 PDFs, and 97 Milvus-like files. Family
  records are content-addressed manifests; S4 must register individual artifact lineage.
- Original Milvus SHA-256 remained
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
  No verified copy was found, so S2 did not open any Milvus client or collection.
- Original `pgtest` remained `paused=true` on forbidden port `15432` with source volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`;
  recovery lab remained network-none with no published ports.
- No database/file source write, provider call, replay, migration, recollection, or production-code
  change occurred. Task 2.1 is complete; tasks 2.2–2.5 remain open.

## S2 task 2.2 source-to-PRD coverage matrix — 2026-07-11

- Reviewed `s2/source-coverage-matrix.md` against the task 2.1 inventory checkpoint
  `83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09`.
- The matrix separates four-domain object/sub-object evidence, relationship families, and
  exact/semantic/filter/relation retrieval reach from answer synthesis and operational readiness.
- Every gap records its evidence status, known ceiling, and future owning slice. In particular, the
  recovery public schemas are empty, Paper and Professor-Paper survive only in `salvage`, and no
  verified Milvus copy is available for index inspection or parity claims.
- The matrix covers all six confirmed effects: Knowledge coverage, Trusted data, Retrievability,
  Generation fidelity, Continuous operations, and Scenario acceptance. It treats the workbook as
  25 seed queries rather than a target-answer template.
- A deterministic inventory-to-matrix fact check verified workbook, source-family, published
  snapshot, and salvage counts. Contract checks verified all domain, relationship, outcome, and
  seed-corpus requirements. No database, provider, Milvus client, or source mutation was used.
- Task 2.2 is complete; tasks 2.3–2.5 remain open.

## S2 task 2.3 regression and challenge corpora — 2026-07-11

- Deterministic builder `s2/build_corpora.py` reads `docs/测试集答案.xlsx` without modification and
  emits 40 regression cases: 25 workbook rows across 17 conversation groups plus 15 PRD-derived
  cases. The separately versioned challenge corpus contains 12 cases: one user-reviewed badcase
  derived from workbook row 12 and 11 controlled variations.
- The user confirmed workbook answers/key points as case-specific reference ground truth. Each
  workbook case records row provenance and `user_confirmed_reference_gold`; the workbook remains a
  seed-query set rather than a general answer template or sole acceptance source.
- Workbook row 12 explicitly labels its historical response inaccurate. The corpus preserves it as
  a `known_bad_response`/`reviewed_badcase` and uses the key points as the correction constraint, so
  evaluation cannot reward reproducing the known-wrong response.
- PRD regression families cover exact, semantic, structured filter, relationship, A-G, multi-turn,
  Universal Web, provenance/conflict, partial answer, and evidence-based assessment. Challenges
  cover alias/spelling, time/geography/negation, relation direction, displayed-set/referent,
  topic-switch, provider failure, and insufficient evidence.
- Every case has A-G type, domain/family, source, protected slots, observable behavior, and review
  status. All A/B/C/D/E/G information-retrieval cases require Web augmentation; F refusals do not.
- Four TDD contract tests passed after observed RED failures for parser grouping, manifest hashes,
  required families, source resolution, F refusal/Web policy, and known-bad-response semantics.
  Ruff and Pyright passed with zero findings.
- Repeated full generation was byte-identical. Frozen SHA-256 values: regression
  `f2656e8c2f0803452af18fa0d478eec1b1e1b94eaa97ef48d06d0828401297da`, challenge
  `ee46c677af668131fb8da568fabd6386659f3287d0bdb0fd740f7069497f6f9f`, manifest
  `dc7cc10ba08db341a38cc08da1edd2449594120a3861735edfd514b29be46088`.
- PRD/challenge cases remain `pending_user_review` and the manifest remains
  `pending_user_acceptance`; they define observable behavior, not unreviewed factual gold. Task 2.3
  is complete; tasks 2.4–2.5 and S2 acceptance remain open.

## Backup/restore and offline-identity contract audit — 2026-07-11

- The user confirmed that Canonical V2 is a clean logical rebuild in a new isolated database, not a
  V042 patch. Existing proposal/design already satisfied this direction.
- The audit found that recorded source hashes and the salvage-only recovery proof did not establish
  complete backup coverage or independent recoverability for original PostgreSQL, original Milvus,
  WAL/FPI/salvage, and all inventoried historical SQLite/JSONL/XLSX/PDF/cache/raw-source families.
- OpenSpec now requires a content-addressed source-to-backup manifest and a distinct second-target
  recovery/materialization drill. Hash equality alone is insufficient. Missing families, mismatches,
  failed probes, or unreviewed evidence fail closed before the first rebuild write.
- At this audit checkpoint, task 2.6 and Specified slice
  `slices/s2b-source-backup-restore.md` were added. Task 3.2 and every Canonical V2 schema, landing,
  canonical, publication, or index write were blocked until the later S2B acceptance recorded below.
- Canonical identity authority is now explicit: normalization, candidate recall, deterministic
  rules, structured LLM adjudication, human review, and merge/split publication belong to versioned
  offline builds. Query/answer paths may resolve user references against an accepted release but
  must emit an offline review gap instead of mutating identity/source mappings.
- This audit changed contracts only. At that checkpoint it did not create a backup, run a restore,
  access a database, open Milvus, or authorize any rebuild write; task 2.6 was still incomplete.

## S2 task 2.4 current/legacy/unavailable baseline — 2026-07-11T08:16:49Z

- Added deterministic builders/tests for the offline intent measurement and nine-dimension baseline
  report. Three builder contract tests passed after observed missing-implementation RED failures;
  Ruff and Pyright passed with zero findings.
- Exact offline check command removed `DATABASE_URL`, `DATABASE_URL_TEST`, Alembic, and Milvus
  variables and ran only the 100-case fixture contract plus deterministic rule fallback. Targeted
  pytest result: `2 passed, 1 deselected`; measured fallback intent accuracy: `100/100` overall and
  `100%` for every A-G class. This does not measure the provider-backed classifier, retrieval,
  rewriting, or answer behavior.
- `s2/baseline-report.json` SHA-256 is
  `c31b1c240ecc96661cf0b6c3057f02e631f34fcfae7356bb6f827cb5695352a1`; repeated generation from
  the same inputs was byte-identical. `s2/offline-intent-baseline.json` SHA-256 is
  `c7f68e5111250d84a2c30ab6712349d9d14772f636b021ea6d1e5c45c23624fa`.
- Current source evidence covers all four domains, while both recovery public schemas still have
  zero Professor/Company/Paper/Patent/relationship rows. Salvage retains 99,437 Papers, 101,158
  Professor-Paper links, and 20,773 field errors. Current service reach cannot be measured because
  there is no accepted canonical release or verified Milvus copy.
- Stored legacy evidence is retained without cross-population comparison: entity recall `30/41`
  (`73%`), Paper rollup `16/17` (`94%`), reviewed answer accuracy `10/19` (`53%`), multi-turn
  `1/18` passed with required recall `6/37`, and retrieval p95 `5.7089s`. These used changed V042,
  index, corpus, scorer, and/or provider conditions.
- Legacy precision remains unscored: the 12-row artifact is candidate capture, and its four-case
  label file is explicitly a scaffold. `0` listed unsourced-Web candidates is not Precision@K,
  ranking quality, Universal Web invocation, or claim-provenance acceptance.
- Current Recall@K, Precision@K/rank, answer support/citation, Universal Web, multi-turn, latency,
  provider calls, and cost are `unavailable`, not zero. Task 2.5 must freeze future thresholds and
  decide the evaluation-system replacement/calibration work without re-labeling legacy values.
- Source-invariant check passed with `set -e`: original `pgtest` remains paused on volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; original Milvus and salvage
  dump hashes match. An earlier composite check had an invalid Docker template and was discarded;
  the corrected fail-fast command produced the accepted evidence.
- No database query/write, Milvus client open, provider call, source mutation, backup claim, or
  rebuild write occurred. Task 2.4 is complete; task 2.5 owns the threshold freeze.

## S2 task 2.5 accepted threshold and corpus policy — 2026-07-11T15:10:32Z

- The immutable pending Candidate contains 83 metrics: 24 PRD minima, 25 hard invariants, and 34
  calibrated product-effect gates. Candidate SHA-256:
  `15a99c284861854b98a4bbfb0653700103f7b3b26e58079296f2c24e4c6c81d0`.
- TDD first produced two expected failures because the Candidate still reported
  `pending_user_approval`, then a third expected failure because no candidate-hash approval binding
  existed. GREEN added deterministic acceptance metadata and rejects any content whose SHA-256 does
  not match the reviewed Candidate.
- The Accepted registry SHA-256 is
  `bce20bf959ba8a2b0997fe2bc1d71e5f727b857a2e374990cf76085c1e13b5cc`. All calibrated values are
  `user_approved`; no PRD minimum, hard invariant, numeric threshold, population contract, or legacy
  baseline value changed during acceptance.
- The user explicitly approved the threshold Candidate, corpus ground-truth policy, and S2 tasks
  2.1–2.5. Workbook answers/key points remain case-specific reference ground truth; row 12 remains a
  known bad response with corrective key points. PRD/challenge cases are behavior contracts, not
  generated factual gold. Their immutable manifest retains its generation-time Candidate metadata,
  with this review providing the acceptance overlay.
- The population contract remains honest: the frozen 52 seeds do not materialize every later sample
  bank. Missing versioned/human-reviewed populations block only their owning metric and must be
  supplied by tasks 6.1, 8.1, and 9.1 without rewriting the seed corpus.
- Full S2 verification passed: all four S2 test modules reported `20 passed`; Ruff reported no
  findings; Pyright reported `0 errors, 0 warnings, 0 informations`; every S2 JSON/JSONL parsed;
  committed source/corpus/baseline/threshold hashes matched; regeneration of the Accepted registry
  was byte-identical; and strict OpenSpec validation exited `0`.
- Source invariants were rechecked at `2026-07-11T15:13:44Z`: original `pgtest` was still
  `paused=true` on the frozen volume, the recovery lab remained network-none with no ports, and the
  original Milvus plus verified salvage hashes matched. No database connection or Milvus client was
  opened by Task 2.5.
- Task 2.5 and S2 were Accepted at that checkpoint without authorizing task 2.6 or rebuild writes;
  the independently verified S2B acceptance is recorded below.

## S2B task 2.6 complete backup and independent restore — 2026-07-11T16:11:23Z

- Named targets were physically separated: backup root
  `/md1/mirothinker-backups/canonical-v2-s2b-20260711T152222Z` on device `2305`, independent restore
  root `/var/tmp/mirothinker-restores/canonical-v2-s2b-20260711T152222Z` on device `66306`, and
  primary evidence on device `2049`. Each target remained above the 50 GB capacity floor.
- Backup manifest SHA-256
  `a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8` covers all 48 frozen
  inventory records plus original PostgreSQL and the complete forensic/WAL/FPI recovery tree. The
  inventory expands to 42,556 logical members and 16,447,082,378 bytes; all hashes and copy-
  independence checks passed.
- The original PostgreSQL volume was mounted only `rw=false` while `pgtest` remained paused. Its
  3,762-entry, 418,849,280-byte archive SHA-256 is
  `509cf117eae7ae3069e8d41d247044cd43168086b33b231590d9605546288da9`.
- The 24,230-entry forensic tree archive SHA-256 is
  `59f5901ecae7f612848ce7142031ad1efa1c366ce00a50b99019732b2d4d1055`. It includes retained WAL,
  FPI pages, ext4 journal/inode evidence, salvage and checkpoint dumps, forensic PostgreSQL bytes,
  IDs, plans, tools, and metadata. Only the active derived recovery-lab PGDATA was excluded; its
  immutable dump/checkpoint inputs are included and the original volume is backed separately.
- Restore verification SHA-256
  `98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231` reports 50/50 sources
  passed. The 48 inventory records rematerialized with 42,556 hash checks and 86 bounded format
  probes. The forensic tree manifest matched exactly; both dumps, one WAL record, 20,427 FPI pages,
  and an ext4 journal block passed their format probes.
- PostgreSQL exact materialization matched all 3,762 tree entries. A second labeled probe volume ran
  with network none/no ports/read-only rootfs and proved `miroflow_real`, Alembic `V042`, 42 public
  tables, and zero Company/Professor/Paper/Patent rows. The failed initial `postgres`-role assumption
  was diagnosed as a probe bug; the original non-secret configured role `miroflow` succeeded without
  creating or changing roles.
- Original Milvus was never opened. A third verified probe copy opened six collections with 70,780
  rows; neither original nor first restored copy changed, and the probe copy hash was unchanged.
- A sibling-pattern audit found Postgres-image implicit anonymous volumes in S2B tool containers.
  RED/GREEN mount-policy coverage now requires an exact persistent allowlist and explicit PGDATA
  tmpfs override. Seven volumes attributable by ID/time were proved anonymous, dangling,
  unreferenced, and empty before exact removal; no recent anonymous dangling volume remained.
- Pre-acceptance verification passed 32 tests, Ruff, Pyright, full inventory regeneration, exact
  archive/source hashes, capacity/target isolation, source invariants, strict OpenSpec validation,
  and a temporary exact-hash admission run. Formal acceptance record SHA-256 is
  `3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b`; the formal gate reports
  `state=accepted`, `source_count=50`.
- Final post-acceptance verification at `2026-07-11T16:19:12Z` repeated all 32 tests, Ruff, Pyright,
  formal admission, artifact/control hashes, full inventory regeneration, capacity, target/source
  identities, and strict OpenSpec validation. The backup root is read-only (`dr-x------`); its
  control-evidence manifest SHA-256 is
  `59473d1739a5b072d9118d0fc76f92caa028d754c421d88a0c94e6db25d670f2`.
- No original source write, provider call, recollection, Canonical V2/landing write, or production-
  like cutover occurred. Task 2.6 is complete; the next task is 3.1.

## S3A task 3.1 deep-module RED interfaces — 2026-07-11T16:31:48Z

- Added one public-interface contract for each OpenSpec design seam: `EvidenceLanding.ingest/stream`,
  `KnowledgeBuild.build`, `KnowledgeRead.execute`, `KnowledgeAnswer.answer`, and
  `ReleasePublication.verify/promote/rollback`.
- The tests use typed request/result construction and local recording adapters to assert only
  caller-visible outcomes: evidence byte identity/lineage, isolated candidate manifests, protected
  query/evidence traces, material claim-evidence mapping with local/Web disclosure, and exact
  release parity/promotion/rollback. They do not assert tables, collection names, helper calls,
  execution order, or mock call counts.
- Each test is `xfail(strict=True, raises=ModuleNotFoundError)`. The normal command
  `uv run pytest tests/canonical_v2/test_*_interface.py -n0 -q` exited `0` with exactly five xfails
  and no failure/error/XPASS. The same command with `--runxfail` exited `1` with exactly five
  missing-`canonical_v2` failures and no collection/syntax/setup error.
- The strict marker is temporary executable RED evidence: unexpected failures are not swallowed,
  and a future implementation that satisfies a contract becomes XPASS/failure until the marker is
  intentionally removed by its GREEN task.
- Ruff passed and Pyright reported zero findings for all five files. The existing S2/S2B suite
  remained `32 passed`; formal backup admission remained Accepted for 50 sources; strict OpenSpec,
  original pause, Milvus hash, and salvage hash checks passed.
- No production source file, dependency, schema, database/index, provider, or original evidence was
  touched. Task 3.1 is Accepted under the user's self-approval authorization; task 3.2 must establish
  a separate Ready isolated-write slice before any database change.

## S3B task 3.2 clean database baseline — 2026-07-11T16:58:23Z

- The Ready slice fixed the boundary before writes: a separate Canonical V2 Alembic root, exact
  S2B admission before engine creation, S1 target identity before DDL, eight empty business
  namespaces, and no Task 3.3/3.4 tables or constraints.
- RED first reported `6 failed, 1 skipped`: the gate module was absent in five cases and the
  dedicated Alembic config/root was absent in one. After the isolated empty target was provisioned,
  the opt-in real test also failed at the missing Alembic root while the database remained at zero
  public tables and zero Canonical V2 schemas.
- `rebuild_write_gate.py` now binds the exact source inventory
  `83a9e2c8…0fa09`, backup manifest `a14c1eab…e59c8`, restore verification
  `98826e8d…d231`, and acceptance record `3155d890…fc5b`. Missing, byte-changed, non-accepted,
  coverage-mismatched, or failed-probe evidence rejects before migration engine creation.
- `canonical_v2_alembic` is a one-revision independent history: base/head `C2_0001`, branch
  `canonical_v2`, no V042 ancestry, and a distinct `public.canonical_v2_alembic_version` table. The
  revision creates only `landing`, `knowledge`, `professor`, `company`, `paper`, `patent`, `publish`,
  and `ops`; downgrade uses reverse-order non-cascading drops.
- The new target is `miroflow_canonical_v2_candidate_s3b`, marker
  `miroflow:destructive-target:v1:isolated-candidate:miroflow_canonical_v2_candidate_s3b`, system
  identifier `7661313446684311592`, container `canonical-v2-s3b-pg-20260711`, and named labeled
  volume `canonical-v2-s3b-pgdata-20260711`. It is healthy with network `none`, ports `{}`, restart
  policy `no`, and only a dedicated host-local Unix socket.
- The first socket used mode `0770`, but postgres retained primary GID 999 rather than the requested
  supplemental group, so host connection was denied. No migration ran. Recreating only the
  container over the same empty target volume with a `0777` socket inside a `0770` host directory
  preserved network/port isolation and limited traversal to postgres plus the workspace user.
- The real integration test deliberately set generic `DATABASE_URL` to the forbidden
  `localhost:15432/miroflow_real` value while providing the explicit Unix-socket candidate target.
  It passed base → `C2_0001` → base → `C2_0001`; final inspection found eight schemas, zero business
  tables, and zero legacy/extra public tables. Task 3.4 later invalidated the raw dump SHA because
  PostgreSQL 16 randomizes `\\restrict` control tokens; disposable replay produced deterministic
  normalized C2_0001 fingerprint
  `4c9df650d4f039ca9ba67ff6169ef44c839e0610528c2b27c4338eeeddf454c3` over 3,054 bytes.
- Final checks: Canonical V2 `7 passed, 5 xfailed`; S1 safety `9 passed`; S2/S2B `32 passed`; Ruff
  clean; Pyright `0 errors, 0 warnings, 0 informations`; strict OpenSpec and diff checks passed.
  Formal admission remained `state=accepted`, `source_count=50`; original `pgtest` stayed paused on
  its exact volume, recovery lab stayed network-none/no-port, and original Milvus/salvage hashes
  matched.
- Task 3.2 is Accepted under the user's self-approval authorization. The database is only an empty
  accepted foundation; Task 3.3/3.4 must add typed contracts/tables in separate Ready slices.

## S3C task 3.3 shared typed contracts — 2026-07-11T17:15:42Z

- Domain-model review confirmed the approved glossary already distinguishes Canonical V2,
  canonical/derived relations, relationship exploration, inclusion, and path eligibility. No new
  product term or glossary conflict required a protected `CONTEXT.md` change.
- Focused RED was `15 failed`, all caused solely by the absent
  `src.data_agents.canonical_v2.contracts` module. No test collection, fixture, or syntax failure
  occurred.
- The new single shared seam defines 26 frozen, extra-forbid Pydantic models and 20 workflow enums.
  It covers byte-addressed artifacts; replayable parser records and typed errors; temporal field and
  relationship assertions; selected/unresolved canonical decisions; source/canonical identities and
  merge/split/reversal lineage; canonical/derived/session relationships; versioned policies;
  knowledge gaps; and candidate/publication/manifests.
- Validators target hard contradictions rather than completeness gates: SHA and timezone identity,
  parent lineage, typed non-parsed errors, valid intervals, decision evidence membership,
  merge/split shapes, canonical-vs-derived evidence semantics, named hard exclusions, verified gap
  resolution, one-release manifests, and zero-deviation accepted parity. Partial records, competing
  assertions, unresolved decisions, optional enrichment, soft limitations, open catalogs, and
  opaque non-legacy IDs remain valid.
- Physical table/column/collection/provider contracts and typed domain business facts are absent.
  Build manifests instead retain source/parser/policy/model/decision/object/relationship/
  eligibility/publication/index versions, counts, and hashes through logical projection identities.
- Focused GREEN was `15 passed`. An initial Pyright finding identified the Python enum-member name
  `split` colliding with `str.split`; renaming only the member to `split_identity` retained external
  value `"split"` and produced zero Pyright findings.
- Expanded Canonical V2 checks were `21 passed, 1 skipped, 5 xfailed`: the opt-in real migration
  cycle was deliberately not run because this slice is DB-write-free, while all Task 3.2 gate/static
  checks and Task 3.1 strict RED contracts behaved as expected. S1 was `9 passed`; S2/S2B was
  `32 passed`; Ruff, strict OpenSpec, formal admission, and diff checks passed.
- Read-only candidate inspection preserved database/marker/system identifier
  `7661313446684311592`, revision `C2_0001`, eight schemas, and zero business tables. Original
  `pgtest` remained paused on its exact volume, recovery lab remained network-none/no-port, and
  original Milvus/salvage hashes matched. No database/Milvus/provider/source/runtime/dependency write
  occurred.
- Task 3.3 is Accepted under the user's self-approval authorization. Task 3.4 must map these logical
  values to integrity-tested storage in a separate Ready slice.

## S3D task 3.4 schema integrity migration — 2026-07-11T17:48:21Z

- Task interpretation was effect-first: S3 could not become an adapter-ready foundation with empty
  namespaces plus RED-only storage tests. Task 3.4 therefore used real tests to drive the smallest
  C2_0002 shared evidence/decision/release storage GREEN, without implementing S4–S7 module
  orchestration or typed domain facts.
- The first real disposable run was `7 failed`: two absent-C2_0002 revision failures and five
  undefined-table failures across actual SQL paths. The marked DB was
  `miroflow_canonical_v2_s3d_disposable`, inside the existing network-none/no-port S3B container;
  generic `DATABASE_URL` was deliberately set to forbidden `localhost:15432/miroflow_real` and was
  not used.
- First GREEN was `7 passed`. Self-review then challenged both precision and breadth: exact source
  and verified copy artifacts must coexist with identical bytes; parser-run/source-identity
  operational metadata must progress without rewriting evidence; and a build manifest hash must
  match its release. Those regressions produced the expected `3 failed, 6 passed`; revised DDL then
  produced `9 passed`.
- C2_0002 creates 24 shared tables across `landing`, `knowledge`, and `publish`, 126 named
  constraints, and 19 append-only triggers. It keeps `ops` and all typed domain schemas table-free.
  Named composite FKs prevent cross-release canonical endpoints; logical unique constraints prevent
  parser replay/assertion duplicates; immutable evidence/assertion/decision rows reject update and
  delete while operational parser/source-identity metadata remains updateable.
- Reversible identity decisions use a same-release self-FK and retain original plus reverse rows.
  Build manifests are release/hash-bound. The singleton serving pointer requires canonical,
  published-projection, and index release IDs to equal one manifest-backed active release; nested
  transaction rollback restored the prior pointer without deleting either release manifest.
- Downgrade names objects in reverse dependency order without CASCADE, returns to exactly the eight
  C2_0001 schemas, and re-upgrades to C2_0002. All fixture transactions rolled back. Disposable and
  durable candidate each reported C2_0002, 24 tables, zero rows, 126 constraints, and 19 triggers.
- A pattern audit proved raw PostgreSQL 16 schema-dump SHA values were volatile because every dump
  changes random `\\restrict`/`\\unrestrict` lines. Only two sibling claims existed, both in Task
  3.2 evidence. `scripts/canonical_v2_schema_fingerprint.py` now removes only those control lines;
  two tests prove random-token stability and real schema-change sensitivity.
- Corrected C2_0001 fingerprint is
  `4c9df650d4f039ca9ba67ff6169ef44c839e0610528c2b27c4338eeeddf454c3` over 3,054 normalized bytes.
  C2_0002 candidate/disposable fingerprint matched at
  `ffeb1c92cb6dbc5ee9475b37142f632250b21dd97beb5da02a7f0642a64b6faf` over 50,032 bytes, with two
  random control lines removed from each.
- The sibling audit also found Task 3.2's baseline test was coupled to the durable candidate and
  dynamic head. After C2_0002, that could downgrade a future populated candidate and falsely require
  head to contain no tables. RED was reproduced on the disposable; the test now requires target kind
  `disposable`, verifies fixed revision C2_0001, and restores current head in `finally`.
- Real migration/integrity/fingerprint verification was `13 passed`; normal no-DB Canonical V2 was
  `23 passed, 10 skipped, 5 xfailed`; S1 was `9 passed`; S2/S2B was `32 passed`. Ruff, Pyright,
  strict OpenSpec, formal admission, and diff checks passed.
- After matched evidence capture, the disposable database was dropped. Durable
  `miroflow_canonical_v2_candidate_s3b` remains healthy, network-none/no-port, system identifier
  `7661313446684311592`, at C2_0002 with 24 tables and zero rows. Original `pgtest` stayed paused on
  its exact volume; recovery lab isolation and original Milvus/salvage hashes matched.
- Task 3.4 is Accepted under the user's self-approval authorization. This does not accept the whole
  S3 foundation; Task 3.5 owns that independent review.

## Task 3.4 pattern-fix report

- Reported cases fixed: nondeterministic schema-dump hashes and a baseline rollback test whose
  target/revision scope became unsafe after a second migration.
- Defect class: volatile command output treated as content identity; destructive tests bound to a
  durable target and dynamic head.
- Sibling search: all repository schema-dump/hash claims and Canonical V2 migration rollback tests.
- Sibling issues found/fixed: two raw Task 3.2 hash claims and one candidate-bound baseline test.
- Not fixed: no other matching schema-hash claim or Canonical V2 destructive test exists.
- New invariant/helper/test: normalized fingerprint CLI plus two tests; disposable-only fixed-
  revision baseline test with current-head restoration.
- Remaining risk: new dump evidence must use the helper; new destructive migration tests must use
  freshly marked disposable databases.

## S3E task 3.5 independent foundation review — 2026-07-11T18:22:18Z

- Independent review compared S3 commits `905ca35..e7fffe2` and the repair candidate against the
  OpenSpec design/specs, shared contracts, DDL, real tests, and predecessor gates. The full finding
  matrix and disposition are in `s3-foundation-review.md`; no Critical/Important finding remains.
- First review RED was eight serial database failures plus one contract failure: parent hashes were
  not bound to parent bytes, assertion endpoints were not bound to record/identity mappings,
  append-only history allowed bulk truncate, decision history could not cross releases, structured-
  LLM traces had no storage, and relationship assertions could use canonical endpoints.
- A default-xdist RED attempt produced one failure plus seven migration setup errors because workers
  raced the same disposable database. This was classified and fixed as a destructive-test harness
  defect; the Canonical V2 subtree now selects zero automatic xdist workers, and its default command
  ran serially.
- Second review RED added four database failures and two contract failures for mutable parser/source-
  identity provenance rewrite/delete and self-referential decision lineage. A final review pass added
  two wrong-subject supersession failures and one wrong-policy contract failure.
- C2_0003 repairs the complete defect class without rewriting C2_0001/C2_0002: composite artifact
  hash and record/identity provenance FKs; truncate guards; field-aware parser/source-identity
  mutation guards; globally unambiguous cross-release decision lineage bound to the same logical
  subject and never itself; and schema-validated JSONB LLM traces on identity, field, and
  relationship decisions.
- Shared contracts now require field-selection policy for canonical decisions, source identities for
  source-grounded relationship assertions, and non-self decision lineage. Future EvidenceLanding,
  KnowledgeBuild, and ReleasePublication modules must re-export the shared record/candidate/release
  types rather than create drift-prone duplicates.
- Full default Canonical V2 verification was `47 passed, 5 xfailed`; forced RED was exactly five
  `ModuleNotFoundError` failures for the future deep modules. The real disposable exercised base/
  C2_0001/C2_0002/C2_0003 downgrade/re-upgrade and all fixture rows rolled back.
- Two disposable dumps and the durable candidate dump normalized identically to
  `7d85702ecb0e84cbbbbbc175f88c4b735190e53f4a576c72e49088899dd94991` over 63,875 bytes, removing
  exactly two random PostgreSQL control lines. Both targets reported 24 shared tables, zero rows,
  141 constraints, 44 non-internal triggers, and three LLM-trace columns at C2_0003.
- Durable candidate `miroflow_canonical_v2_candidate_s3b` was forward-upgraded only after GREEN and
  exact gate/name/marker/system/network/volume proof. The test-only disposable was then dropped.
- S1 safety was `10 passed, 5 explicit skips`; S2/S2B was `32 passed`; Ruff passed; Pyright reported
  zero findings; strict OpenSpec and diff checks passed. Formal admission remained `accepted/50`.
  Original `pgtest` stayed paused on its exact volume, recovery lab stayed network-none/no-port, and
  original Milvus/salvage hashes matched.
- Task 3.5 and all S3 are Accepted under the user's objective-verification self-approval
  authorization. Task 4.1 remains unstarted until its own Ready slice.
- Final read-only invariant check at `2026-07-11T18:25:59Z` re-proved formal admission
  `accepted/50`, candidate C2_0003/24 tables/zero rows/141 constraints/44 triggers, disposable
  absence, original pause/volume, recovery isolation, and both source hashes.

## Task 3.5 pattern-fix report

- Reported cases fixed: audit-chain gaps across interface types, artifact/record identity,
  append-only/mutable history, reversible decisions, LLM trace storage, and test concurrency.
- Defect class: typed audit intent was present in names/models but not closed across interface,
  storage, cross-release lineage, bulk mutation, and test-execution boundaries.
- Sibling search: all three decision families, every append-only/mutable history table, all source-
  assertion endpoint paths, all Task 3.1 shared-type candidates, and all Canonical V2 destructive
  migration tests.
- Sibling issues found/fixed: three trace columns/checks, three decision lineage families, nineteen
  append-only truncate triggers, two mutable-history field/delete guards, artifact plus three
  assertion provenance FKs, three shared public type exports, and one subtree-wide xdist guard.
- Not fixed: later-slice repositories still own association cardinality and transactional build
  semantics; ReleasePublication owns verification/state authorization; domain/ops storage remains
  intentionally absent. None is exposed as accepted behavior in S3.
- New invariant/helper/contract/test: C2_0003 plus real RED/GREEN matrix; shared-contract validators;
  default-serial Canonical V2 DB tests; deterministic matched candidate/disposable fingerprint.
- Remaining systemic risk: later writers must enter through the shared typed/deep-module seams and
  add their own real transaction tests; direct caller SQL is not an accepted interface.

## Explicit non-claims

- S2B acceptance satisfies only the backup prerequisite; each later task still requires its own
  Ready slice, explicit isolated target, and verification loop.
- No populated Canonical V2 candidate, serving projection, or Milvus release is accepted.
- No original source write or production-like cutover is authorized.
