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
business rows. Task 4.1's immutable-landing strict RED contract was Accepted at
`2026-07-11T18:33:37Z`. Task 4.2's storage-independent EvidenceLanding core and source adapters were
Accepted at `2026-07-11T19:06:55Z`. Task 4.3's C2_0004 and PostgreSQL repository were Accepted at
`2026-07-11T19:42:20Z`; Task 4.4 replayed the bounded real-source matrix at commit
`cef42a1e075d30c5a0e179f34ab543b4878edabd`. Task 4.5 independently reviewed and Accepted all S4 at
`2026-07-11T22:07:12Z` after a content-addressed dump restored with exact 26-table logical parity in
a distinct disposable PostgreSQL system. The durable candidate remains isolated at C2_0004 with
only immutable landing evidence and zero canonical/publication/index rows. Task 5.1's strict RED
assertion/decision contract was Accepted at `2026-07-11T22:58:11Z`; task 5.2 is next and has not
started.

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

## Next pending evidence

1. Task 5.2 decision-core implementation requires its own Ready slice. Task 5.1 RED acceptance does
   not authorize a production module, shared-contract/migration change, database write, or S5
   acceptance claim.

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

## S4A task 4.1 immutable landing RED — 2026-07-11T18:33:37Z

- The approved design keeps `EvidenceLanding.ingest/stream` deep and storage-independent. Task 4.1
  therefore targets a future concrete ephemeral composition through those public methods, rather
  than a local subclass that fabricates receipts or direct C2 table assertions that would leak Task
  4.3 storage.
- Four independent scenarios freeze observable effects: exact content hash and distinct source/copy
  artifacts with parent lineage plus mismatch rejection before streaming; same-artifact replay with
  distinct immutable parser v1/v2 record/run identities; partial and corrupt rows retaining readable
  payload plus typed field/record errors; and unreadable identity fields producing neither
  placeholders, parent IDs, canonical IDs, nor an active-release change.
- Synthetic historical-JSONL bytes include one explicit unreadable-external marker and one corrupt
  line solely to define the representative contract. No real recovery/historical/provider source was
  opened or replayed; Task 4.2 owns adapter implementation and Task 4.4 owns the bounded source
  matrix.
- Normal focused pytest was exactly `4 xfailed`. Forced `--runxfail` was exactly `4 failed`; every
  failure was `ModuleNotFoundError: src.data_agents.canonical_v2.evidence_landing`, with no syntax,
  fixture, collection, or assertion error.
- Normal Canonical V2 regression was `23 passed, 24 skipped, 9 xfailed`: real database cases skipped
  without explicit test target, the original five Task 3.1 seams remained strict RED, and the four
  new landing cases were the only additional xfails. S1 was `10 passed, 5 explicit skips`; S2/S2B
  was `32 passed`; Ruff and Pyright reported no findings.
- Strict OpenSpec and diff checks passed. Formal S2B admission, original pause/volume and source
  hashes, recovery isolation, and the zero-row C2_0003 candidate remained unchanged. No production
  module, migration, database, source, Milvus, provider, dependency, or runtime behavior changed.
- Task 4.1 is Accepted under the user's objective-verification self-approval authorization. This
  accepts only RED behavior; S4 remains unaccepted and task 4.2 has not started.
- Final read-only check at `2026-07-11T18:35:00Z` re-proved formal admission `accepted/50`, original
  pause/volume and hashes, recovery/candidate isolation, and candidate C2_0003/24 tables/zero landing
  or release rows.

## S4B task 4.2 EvidenceLanding and source adapters — 2026-07-11T19:06:55Z

- The implementation follows the approved deep-module boundary: `evidence_landing.py` owns strict
  request/receipt/parser/draft types, exact-byte and pre-parse parent-lineage checks, separate
  request/output fingerprints, deterministic identities, atomic visibility, replay retention, and
  the public `ingest/stream` seam. `evidence_adapters.py`
  owns format parsing only. Its composition uses an internal ephemeral repository; Task 4.3 still
  owns PostgreSQL persistence and Task 4.4 still owns actual-source matrix replay.
- Four pre-implementation adapter scenarios failed exactly with `ModuleNotFoundError` and covered
  verified WAL/FPI salvage envelopes, shared JSON/CSV/XLSX/SQLite record behavior, verified-copy-
  only Milvus exports, and already-collected response provenance. The Task 3.1 EvidenceLanding plus
  four Task 4.1 effects and those four adapter cases then produced an initial `9 passed` GREEN.
- Adapters consume only supplied immutable bytes. SQLite materializes those bytes to a temporary
  file opened with `mode=ro&immutable=1`; XLSX uses read-only mode; WAL/FPI and Milvus accept verified
  record envelopes rather than opening original stores; collected responses contain no acquisition
  or provider client. No original/recovery path or real source was opened by the implementation or
  behavior tests.
- Candidate self-review first found three escaped sibling defects. A repeated run ID did not fingerprint
  parent lineage, CSV/XLSX could silently overwrite duplicate columns, and collected-response
  provenance checked field presence without validating field shape. Three new regressions produced
  the expected `3 failed`; the shared fixes bind both parent identifiers, quarantine duplicate CSV
  and XLSX headers before row construction, and preserve invalid response envelopes as partial
  evidence with field-specific typed errors.
- A second immutable/silent-loss audit found six sibling failures: observation time was absent from
  run identity, returned payloads could mutate repository state, unheaded CSV cells were discarded,
  JSON duplicate keys used last-write-wins, boolean/empty Milvus identifiers passed, and a non-time
  retrieval string passed provenance validation. All six failed before their shared fixes and then
  passed. Final focused landing verification was `16 passed`.
- Default Canonical V2 verification was `39 passed, 24 skipped, 4 xfailed`; all skips require an
  explicit disposable database and all four xfails are the untouched future KnowledgeBuild,
  KnowledgeRead, KnowledgeAnswer, and ReleasePublication seams. Forced interface execution was
  exactly one EvidenceLanding pass plus those four `ModuleNotFoundError` failures. S1 was
  `10 passed, 5 explicit skips`; S2/S2B was `32 passed`.
- Focused Ruff passed and Pyright reported zero errors/warnings/information. Strict OpenSpec and
  `git diff --check` passed. No dependency, migration, database/schema row, actual source replay,
  Milvus client, provider call, canonical/publication/index state, or legacy runtime consumer
  changed.
- Final read-only evidence re-proved formal admission `accepted/50`; original `pgtest` is paused on
  volume `d81c6381…d241`; recovery and candidate containers remain network-none/no-port; original
  Milvus and salvage hashes remain `43ef203e…67cc` and `cef8eb6b…bb7`. The candidate marker and
  system ID match, revision is C2_0003, and it has 24 tables, 141 constraints, 44 non-internal
  triggers, and exactly zero rows across all Canonical V2 business tables.
- Task 4.2 is Accepted under the user's objective-verification self-approval authorization. This
  accepts only the ephemeral core and safe source adapters; S4 remains unaccepted, and task 4.3 has
  not started.

## Task 4.2 pattern-fix report

- Reported cases fixed: conflicting parent/time hidden behind one run ID; returned snapshots
  mutating retained evidence; duplicate or unheaded structured values being overwritten/discarded;
  ambiguous JSON, Milvus identifiers, and collected-response provenance treated as parsed.
- Defect class: evidence identity or shape checks were locally present but incomplete across
  idempotency, sibling structured adapters, and provenance fields.
- Sibling search: run/artifact/parent/time fingerprints and conflict paths; stream snapshot
  ownership; CSV/XLSX header and row-to-payload paths; every JSON-based adapter; Milvus record
  identity; every required collected-response provenance field.
- Sibling issues found/fixed: parent identity and normalized observation time enter the run
  request fingerprint before lineage/parse, while parser output remains separately fingerprinted;
  stream returns deep snapshots; CSV/XLSX enforce structural uniqueness and CSV keeps mapped fields
  with typed overflow errors; every JSON adapter rejects duplicate object keys; Milvus rejects
  empty/boolean identity; response URL/time/status/content type receive field-specific validation
  without discarding readable body bytes.
- Not fixed: durable cross-process idempotency and transactions belong to Task 4.3; real source-
  format/count compatibility belongs to Task 4.4. Neither is claimed by this ephemeral slice.
- New invariant/helper/contract/test: complete-run idempotency regressions, detached stream snapshot,
  cross-format duplicate-header and JSON matrices, CSV overflow preservation, invalid Milvus/
  provenance regressions, strict JSON loader, and non-shared parser defaults.
- Remaining systemic risk: adapters added later must apply the same pre-construction uniqueness and
  typed-degradation rules; Task 4.3 must re-prove atomicity/idempotency against real PostgreSQL.

## S4C task 4.3 durable EvidenceLanding — 2026-07-11T19:42:20Z

- The Task 4.2 core now depends on a small repository protocol for pre-parse admissibility, atomic
  prepared-run commit, and ordered stream. Hashing, adapter behavior, typed records, receipts, and
  the `EvidenceLanding.ingest/stream` seam remain shared by the ephemeral and PostgreSQL adapters;
  storage table/SQL details do not enter the caller interface.
- Initial RED was exactly `6 failed`: Alembic could not resolve C2_0004, four real behavior paths
  could not import `evidence_landing_postgres`, and the forced-rollback path lacked a persistence
  error type. The explicit Unix-socket DSN addressed only the newly marked
  `miroflow_canonical_v2_s4c_disposable`; generic `DATABASE_URL` was deliberately set to forbidden
  `localhost:15432/miroflow_real` and was not selected.
- C2_0004 adds immutable `landing.ingest_run`, `parser_run.parser_options`, and
  `source_record.record_ordinal` plus composite lineage/parser FKs, fingerprint/status/count checks,
  uniqueness, and append-only/immutable triggers. Its upgrade transaction refuses any nonempty
  C2_0003 landing because original run identities cannot be reconstructed without invention. A real
  RED proved the old migration silently accepted such a row; GREEN proved the failed upgrade leaves
  both C2_0003 revision and original artifact intact.
- The PostgreSQL factory first requires an absolute exact Accepted S2B gate root, then resolves only
  explicit target URL/name/kind, verifies connected database name/marker and C2_0004, and rechecks
  the gate before every write connection. A relative path to the real Accepted root failed RED only
  after attempting DNS; the reordered gate now rejects it before connect. A read-only probe of the
  durable candidate correctly rejected its intentional C2_0003 revision without writing it.
- Commit takes a transaction-scoped advisory lock per run ID, rechecks request/output fingerprints
  and artifact lineage, then atomically inserts artifact, parser configuration, ordered records,
  ordered errors, and the ingest-run receipt. Exact concurrent repeats commit once; conflicting
  repeats add nothing; distinct concurrent runs share one artifact without losing either replay;
  a forced record-insert trigger rolls back every preceding row.
- Restart/replay reconstructs parser/schema identity, record order, payloads, and ordered typed
  errors through shared contracts. `ingest_run` rejects update/delete/truncate and parser options
  reject rewrite. Python's non-standard `NaN/Infinity` JSON behavior was found at the PostgreSQL
  boundary: two REDs showed ephemeral false-parse and JSONB batch failure; the shared strict loader
  now quarantines those records as corrupt while the batch commits.
- Final real disposable verification was `34 passed`, including repeated C2_0001↔C2_0004
  downgrade/re-upgrade, all prior shared-integrity tests, nine Task 4.3 scenarios, concurrency, and
  transaction rollback. Focused ephemeral landing was `17 passed`. Default no-DB Canonical V2 was
  `41 passed, 32 explicit skips, 4 xfailed`; forced interfaces remained exactly one EvidenceLanding
  pass plus four missing future modules. S1 was `10 passed, 5 explicit skips`; S2/S2B was
  `32 passed`; Ruff check/format, Pyright, strict OpenSpec, and diff checks passed.
- Immediately before deletion, the disposable matched its marker/system ID at C2_0004 with 25
  tables, 153 constraints, 46 non-internal triggers, both required landing columns, and zero total
  business rows. It was then dropped and its database count became zero. The durable candidate
  remained C2_0003/24 tables/zero rows; no actual source was replayed and no Milvus/provider,
  canonical, publication, index, dependency, or legacy runtime state changed.
- Task 4.3 is Accepted under the user's objective-verification self-approval authorization. This
  accepts durable module behavior and disposable migration evidence only; S4 remains unaccepted,
  task 4.4 must separately upgrade/populate the isolated candidate from a bounded verified source
  matrix, and no production-like cutover is authorized.

## Task 4.3 pattern-fix report

- Reported cases fixed: in-memory-only idempotency/replay, cross-process run and artifact races,
  partial transaction visibility, mutable ingest/parser history, relative gate acceptance,
  unaccounted nonempty schema upgrade, and non-standard JSON crossing the Python/JSONB boundary.
- Defect class: correct local evidence semantics were not yet closed across process, transaction,
  migration, target-admission, serialization, and database-constraint boundaries.
- Sibling search: request/output/artifact identities; same/different-run concurrency; parser options,
  record/error order, every landing mutation trigger; gate-root and target/revision checks; C2_0003
  upgrade states; all JSON-based source adapters.
- Sibling issues found/fixed: one repository seam and advisory-locked transaction; persisted complete
  run identity/configuration/order; append-only ingest/parser guards; absolute gate-before-connect;
  candidate revision refusal; fail-closed nonempty upgrade; strict duplicate and non-finite JSON.
- Not fixed: actual verified-source format/count compatibility, source-matrix throughput/capacity,
  landing checkpoint hash/count summaries, and durable candidate C2_0004 upgrade belong to tasks 4.4
  and 4.5. None is claimed by Task 4.3.
- New invariant/helper/contract/test: C2_0004 empty-landing admission; PostgreSQL repository protocol;
  restart/concurrency/rollback matrices; cross-layer strict JSON tests; per-test migration reset;
  explicit read-only candidate-behind-head rejection.
- Remaining systemic risk: Task 4.4 must use this public factory with the exact gate/target inputs,
  verify real source bytes before parsing, and prove bounded replay counts/errors without bypassing
  the repository or directly inserting landing rows.

## S4D task 4.4 bounded real-source landing matrix — 2026-07-11T20:33:12Z

- A Ready S4D contract froze six concrete members of the exact Accepted S2B checkpoint: the verified
  FPI salvage dump; `released_objects.db`; the eight-row Company knowledge JSONL; the one-row Patent
  identifier workbook; the 1.3 GB Milvus restore copy; and one verified Professor fetch-cache
  response. The matrix records complete source IDs, member/restore paths, sizes, source SHA-256,
  parser/schema/options, fixed selectors, and expected output summaries. Its SHA-256 is
  `eaba2ecb93f1418b90ece45e91d7071d638095897bdd6a2c012efe6a9db9a923`.
- Initial artifact/adapter RED was exactly seven failures: streaming artifact registration was
  absent, recorded-response provenance was rejected as the wrong source kind, and SQLite ignored or
  accepted invalid/non-deterministic bounds. Matrix/materializer RED was exactly five failures,
  followed by individual REDs for destination-before-preflight, selected COPY filtering, strict
  six-family loading, and two ambiguous-JSON cases. GREEN adds no fixture-only bypass: the same
  public ephemeral/PostgreSQL landing seams execute tests and the real replay.
- `RegisterArtifactRequest` hashes local files in 1 MiB chunks, validates stable file identity,
  expected size/hash and parent pair, and persists an artifact manifest without parser bytes. Both
  repositories retain it idempotently. This permits the accepted backup and restore Milvus/database
  artifacts to form real parent chains without loading 1.3 GB into memory. Direct restored files
  parent to their backup artifacts; WAL, Milvus, and recorded-response exports parent to restore
  artifacts, which parent to their backup artifacts.
- SQLite bounds accept only integer limits 1-1000 and require deterministic primary-key order. The
  historical recorded response keeps the known URL/body/cache hash/path while deliberately omitting
  unknown retrieval time, status, and content type; the shared response adapter preserves it as one
  partial record with three typed `schema_mismatch` errors rather than invent provenance. A complete
  newly collected HTTP envelope remains a later recollection input and is not claimed here.
- The task tool first executes the hard-coded Accepted/50 gate, verifies each selected member in its
  accepted member manifest, constrains all paths below distinct backup/restore roots, streams both
  file hashes/sizes, and rejects shared inodes. WAL extraction scans the verified custom dump in a
  read-only/network-none/tmpfs Docker invocation and retains only three fixed Paper keys/errors;
  every invocation proves the Docker volume set unchanged. Milvus opens only an inode-independent
  working copy of the verified restore, exports three fixed Company IDs/non-vector fields, and proves
  both working and restore hashes unchanged. Matrix/member/cache JSON rejects duplicate keys and
  non-standard numbers before paths or values are used.
- Two read-only real-source observe executions produced byte-identical summary files with SHA-256
  `f529a013e6ee3ea8f2a0b720ec67ea3ca4d4fc556f25ad5ce695e4e158e9277e`.
  Both reported six entries, 21 records, six typed errors, and entry-summary SHA-256
  `5b77b4a4f3ea9f0a0fd4667dfccff6afefa968b5fb43124de816e652d1c58293`.
  The frozen per-entry result is: WAL 3 partial/3 missing-external errors; SQLite 5 parsed; JSONL 8
  parsed; XLSX 1 parsed; Milvus 3 parsed; recorded response 1 partial/3 schema errors.
- Immediately before the first candidate schema write, the gate returned `accepted/50`; container
  isolation was network-none/no-port/restart-no; database name, isolated-candidate marker, and system
  ID `7661313446684311592` matched; revision was C2_0003; and all landing/business rows were zero.
  The candidate was upgraded forward only to C2_0004. No durable candidate downgrade was run.
- Durable replay uses only `create_postgres_evidence_landing`; there are no direct landing inserts.
  Resulting counts are 15 artifacts, six ingest runs, six parser runs, 21 source records, and six
  errors. Artifact kinds are six backup copies, three restore copies, three direct structured
  artifacts, and one each WAL/Milvus/recorded-response derived artifact. There are six roots and nine
  valid parent edges with zero orphan/hash-mismatched edges. Run states are four accepted/two partial;
  records are 17 parsed/four partial; errors are three missing-external/three schema-mismatch.
- Three durable script executions retained exactly those counts. The latter two checkpoint outputs
  compared byte-for-byte with the committed summary; all have SHA-256
  `a88b44fab38d4e56a7894fabb93e56b46c043278082c200773c038a7dc6e80b5`.
  The committed entry hash remains `5b77b4…c58293`. Every knowledge and publish table remains zero;
  no active release, canonical assertion/identity/decision, provider call, live recollection, or
  active/new Milvus index was created.
- Real disposable baseline/integrity/landing validation reported `35 passed`, including migration
  round trips, append-only/FK/reversal/release invariants, streaming parent registration,
  concurrency, rollback, and a candidate-behind-head regression that no longer depends on durable
  candidate state. The disposable was verified by exact marker and deleted; database count returned
  to zero. Default Canonical V2 reported `57 passed, 33 explicit skips, 4 expected xfails`; S1 was
  `10 passed, 5 explicit skips`; S2/S2B was `32 passed`.
- Final static verification passed Ruff check/format, Pyright with zero findings, strict OpenSpec,
  both JSON documents, and `git diff --check`. The final read-only audit at
  `2026-07-11T20:38:12Z` re-proved Accepted/50; original `pgtest` paused on exact volume
  `d81c6381…d241`; original/restore Milvus hash `43ef203e…67cc`; original/restore salvage hash
  `cef8eb6b…bb7`; recovery/candidate network-none/no-port isolation; candidate C2_0004 with 25
  tables and 46 non-internal triggers; 15/6/6/21/6 landing counts; six roots/nine matching parent
  edges/no orphans; zero non-landing rows; no disposable database; and exact matrix/summary hashes
  `eaba2ecb…a923` / `a88b44fa…e80b5`.
- At the Task 4.4 checkpoint it was complete only as a reviewable Candidate; Task 4.5 still had to
  independently review the whole landing slice and restore-verify its database dump before S4 could
  be accepted. No S4 acceptance or production-like promotion was claimed at that earlier point.

## S4E task 4.5 landing review and checkpoint — 2026-07-11T22:07:12Z

- Two independent read-only final reviews returned `Ready` with zero open Critical/Important
  findings. The review first blocked operation and drove systemic repair of exact target admission,
  source/inode revalidation, immutable evidence outputs, separate execution receipts, complete
  table/integrity hashing, final Postgres readiness, restore image/socket/storage policy, and
  owned-ID graceful cleanup. The accepted disposition is in `s4-landing-review.md`.
- Focused S4D/S4E RED began with 13 replay-guard failures and 10 missing-checkpoint failures. Final
  focused verification is `48 passed`; Ruff and Pyright report no findings. In addition to pure
  guards, a real read-only C2_0004 candidate snapshot executed all table and landing-integrity SQL.
- Fresh guarded replay ID `canonical-v2-s4-landing-20260711T215953Z-cef42a1` used the exact Task 4.4
  commit, current S4D tool hash, OpenSpec/worktree identity, Accepted/50 gate, and explicit candidate
  DSN. It returned six entries, 21 records, six expected typed errors, entry hash
  `5b77b4a4...c58293`, and the exact frozen summary SHA-256 `a88b44fa...e80b5`. Candidate target and
  bounded landing state matched before and after; provider calls were zero.
- The checkpoint tool revalidated all six prepared source members before/after dump and after the
  restore drill. It captured an atomic PostgreSQL custom archive only after the exact C2_0004
  candidate and Accepted S2B gate passed. Pre/post snapshots contain the exact 26 user/revision
  tables, normalized schema SHA-256 `7237483f...f4aef`, logical SHA-256 `6328e811...054e8`, the
  15/6/6/21/6 landing counts, all required status/lineage/error aggregates, eleven zero integrity
  violations, and zero non-landing business rows.
- Checkpoint manifest SHA-256 is `ab091aac1cfbf2ba1699f521b9a5629d4d9b02dfb236e0600a4f711219c966b1`.
  It binds full commit `cef42a1e075d30c5a0e179f34ab543b4878edabd`, current Git status/diff,
  S4D/S4E tool/test hashes, OpenSpec tree, accepted threshold/corpus hashes, S2B gate, matrix/fresh
  execution, candidate identity, tool versions, sanitized commands, dump hash/list, and complete
  snapshot. No DSN/credential appears in committed evidence.
- Independent restore used candidate image
  `sha256:8ed3192326bb9d114cd5ef9acace453d5dae17425bd089d089330584c84c5a34`,
  a new name/database, network-none, no ports, restart-no, read-only rootfs, tmpfs PGDATA, no Docker
  volume, and a host-bounded Unix socket. PID 1 had exec'd `postgres` and three readiness probes were
  stable before the marker or restore write. Source/restore system IDs are
  `7661313446684311592`/`7661394091808735279`; revision/schema/all table hashes/logical hash match
  exactly. Restore verification SHA-256 is
  `caf789ae87dc4c0429e068dcc3421c8d1346bec02296f6d056d816a3416f0acc`.
- Cleanup first re-proved the returned 64-character owned container ID, stopped PostgreSQL
  gracefully, removed only that ID without force, and proved container/socket absence. Docker
  volume-set hashes before/after match. The external root
  `/md1/mirothinker-backups/canonical-v2-s4-landing-20260711T215953Z-cef42a1` is frozen with 0550
  directories/0440 files and tree SHA-256 `4ae5f2ce...b05012`; repository copies are byte-identical.
- Expanded verification passed: default Canonical V2 `73 passed, 33 explicit skips, 4 expected
  xfails`; a second fresh isolated disposable PostgreSQL target passed `35` migration/integrity/
  landing tests and was removed with unchanged Docker volumes; S1 was `10 passed, 5 explicit skips`;
  S2/S2B was `32 passed`. The four expected xfails remain the approved future KnowledgeBuild,
  KnowledgeRead, KnowledgeAnswer, and ReleasePublication RED interfaces.
- The response-family acceptance uses complementary evidence: Task 4.2's complete
  `newly_collected_response` adapter contract and Task 4.4's real degraded
  `recorded_collected_response` bytes. Known URL/body survive, unknown HTTP metadata remains typed
  missing provenance, and no live call or invented value is needed to accept the family.
- Acceptance record SHA-256 is `20e11fbe2506a44913e58351ef27121065c0b63bfa12a85cdf9425db6578f58c`.
  Tasks 4.1–4.5 and all five Evidence Landing acceptance checks are Accepted. Task 5.1 has not
  started; no canonical/domain/release/index/provider or production-like state was created.
- Final read-only invariants at `2026-07-11T22:14:20Z` re-proved Accepted/50; original `pgtest`
  `paused=true` on exact volume `d81c6381...d241`; original/restore Milvus hashes both
  `43ef203e...67cc`; original/restore FPI salvage hashes both `cef8eb6b...bb7`; recovery and candidate
  network-none/no-port isolation; exact candidate marker/system/C2_0004/bounded counts; and zero
  non-landing rows. No original Postgres command or Milvus client was used.

## S5A task 5.1 assertion/decision RED — 2026-07-11T22:58:11Z

- Three independent read-only design reviews converged on a package-internal deep module,
  `CanonicalDecisionEngine.decide(batch) -> result`, rather than extending `CandidateRelease`,
  adding decision CRUD to `KnowledgeBuild`, or testing direct C2 tables. The future Task 7.2
  `KnowledgeBuild` hides this module; Task 5.1 neither creates nor awakens that public seam.
- Five independent scenarios freeze observable outcomes: all competing field assertions remain
  distinct while a decision-backed current value retains supporting/conflicting evidence; identity,
  source-state, field/entity, and build-as-of constraints filter LLM candidates without deleting
  assertions; recorded structured output is schema/version/evidence/content-hash bound and order-
  independent; material field ambiguity remains unresolved with no current fact; and accepted plus
  unresolved relationship decisions retain all evidence while only accepted relations become
  current.
- The first formal review found three Important contract defects: any nested `ModuleNotFoundError`
  could be masked as expected RED, the four Task 5.2 shared-contract/storage reconciliations were not
  explicit, and unresolved relationship no-projection behavior lacked execution coverage. Exact
  exception-name guarding, an explicit GREEN handoff, and an accepted/unresolved relation pair
  closed them.
- The second review found that an unbound `preferred_source_systems` input could change a winner
  without changing the policy digest, and that arbitrary output hashes were not content-bound. The
  source-preference shortcut was removed; conflicting winner selection now uses recorded structured
  adjudication. Recorded responses now retain canonical raw bytes plus their computed expected
  SHA-256, the trace exposes the validated output and computed digest, and a mismatched digest must
  raise `AdjudicationIntegrityError`. Final independent review reported zero Critical/Important
  findings and Ready.
- Focused normal pytest exited `0` with exactly `5 xfailed`. Final forced
  `--no-cov --runxfail` exited `1` with exactly `5 failed`, every failure the exact absent
  `src.data_agents.canonical_v2.canonical_decision_engine`; there was no syntax, collection,
  fixture, assertion, or nested-import failure.
- One intermediate attempt ran normal and forced pytest concurrently in one worktree. Both
  `pytest-cov` processes targeted shared coverage state; the forced process ended with a coverage
  SQLite `no such table: file` internal error after its five intended failures. The exact empty
  generated shard was removed, serial `--no-cov` replay produced the required five failures, and no
  source/test behavior was changed. Same-worktree pytest verification is serial from this point.
- Default Canonical V2 regression, with all four explicit integration settings removed, was
  `73 passed, 33 explicit skips, 9 expected xfails`: the existing four future deep-module xfails plus
  these five Task 5.1 cases. S1 target/seed-loader safety was `10 passed, 5 explicit skips`; S2/S2B
  was `32 passed`. Ruff check/format, Pyright, strict OpenSpec, and `git diff --check` passed.
- Formal S2B gate returned `state=accepted`, `source_count=50`, manifest
  `a14c1eab...e59c8`, and restore verification `98826e8d...d231`. `pgtest` remained
  `paused=true` on exact volume `d81c6381...d241`; it was not entered or connected. Recovery and
  candidate containers remained running with network none and no ports; candidate restart policy
  remained `no`.
- Hash-only checks matched original/backup Milvus at `43ef203e...67cc` and original/backup FPI
  salvage at `cef8eb6b...bb7`; no Milvus client opened the original. The S4 external checkpoint
  remained directory mode 0550 and file mode 0440.
- Corrected read-only candidate probes returned C2_0004, landing counts `15/6/6/21/6`, canonical
  counts `0/0/0/0/0`, and release/build/active counts `0/0/0`. Two preceding read-only probes used
  incorrect unqualified/schema relation names and failed without mutation before this exact query.
- Task 5.1 is Accepted under the user's objective-verification self-approval authorization. This
  accepts only the RED contract. No production/shared-contract/migration/database/source/index/
  provider/runtime change or write occurred; Canonical knowledge acceptance and S5 overall remain
  open.

## S5B task 5.2 canonical decision GREEN — 2026-07-12T04:32:46Z

- The Accepted Task 5.1 scenarios were implemented behind one package-internal
  `CanonicalDecisionEngine.decide` seam. Every supplied field/relationship assertion is retained;
  deterministic source state, canonical ownership, entity/type/version/path, source-record, and
  build-as-of constraints run before any recorded structured adjudication. Zero survivors and
  material ambiguity remain explicit unresolved decisions with no current projection.
- Recorded LLM output is strict UTF-8/finite JSON with exact base64/raw-byte SHA-256 binding,
  validated-output equality, ordered input evidence, provider/model/prompt/schema versions, and
  disjoint selected/conflicting roles. Selected fields must strictly equal their retained assertion
  values; accepted relationships retain exact typed endpoints and role bindings.
- Decision-group manifests partition every retained assertion and bind complete assertion models.
  Field and relationship IDs now recompute a canonical seed over every serialized decision field,
  policy/method/run/time/trace content, exact deterministic outcomes, the manifest, and identity
  constraint input. Rehashed trace metadata, falsified rejection reasons, wrong canonical owners,
  and reversed relationship endpoints all fail typed result validation.
- C2_0005 hardens all three structured-decision trace families, adds partial unique terminal-role
  indexes, and adds two exact five-column append-only constraint-outcome ledgers. It also adds
  FK-linked append-only field/relationship decision-time identity-context snapshot ledgers. Upgrade
  refuses a populated C2_0004 field or relationship decision table with SQLSTATE `55000` because no
  safe historical context backfill exists; failed upgrades preserve C2_0004 and the original rows.
  Downgrade takes `ACCESS EXCLUSIVE` locks across outcome/context ledgers and refuses any nonempty
  append-only history before dropping C2_0005 objects.
- The explicit-target PostgreSQL store revalidates the Accepted S2B gate, connected database marker,
  disposable kind, and minimum known revision before use. Under one transaction/advisory lock it
  validates current authoritative `identity_decision_output` and source-membership/record context,
  persists assertions, decisions, immutable context snapshots, roles, and outcomes, reconstructs the
  uncommitted typed result, and commits only on exact equality. Exact replay is idempotent; changed
  run content conflicts; missing parents/membership create nothing; no current projection table is
  materialized.
- One merged Task 5.2 review initially found incomplete seed reconstruction and absent
  source-to-canonical ownership checks. Vertical RED/GREEN repairs added complete seed recomputation,
  deterministic outcome replay, field/relationship ownership matrices, and durable mapping
  preflight. Closure then found that loading from mutable current identity state would break old
  decisions after incremental collection. Immutable decision-time snapshots plus
  `persist -> append source record/update allowed source state -> exact historical load` closed that
  defect. The final migration closure added populated-C2_0004 refusal for both decision families.
  Final reviewer disposition: `APPROVED`, zero open Critical/Important findings.
- Commit-checkpoint verification passed:
  - default Canonical V2: `93 passed, 48 explicit integration skips, 4 approved xfails`;
  - real disposable baseline/integrity/decision: `41 passed`;
  - separate S4C landing compatibility: `10 passed`;
  - decision-engine contract: `11 passed`;
  - S1 target plus backup-gate safety and S2/S2B: `49 passed` (`17 + 32`);
  - S4 checkpoint harness: `23 passed`;
  - Ruff check/format, Pyright (`0 errors, 0 warnings, 0 informations`), strict OpenSpec, wheel
    contents, secret scan, and `git diff --check` all passed.
- The real test system was container
  `b748e6b66ac9b3ae2c39d2c25747b7b03072d13d5673784e5ca81ad9e67a7ac3`, network `none`, no
  ports, restart `no`, read-only rootfs, tmpfs PGDATA, system ID `7661462653419962415`, with exact
  disposable database markers. Fresh C2_0005 snapshot and S4C databases ended at zero business rows;
  no sibling database remained. The container was gracefully stopped/removed, its host socket and
  wheel-check roots were deleted, and the Docker volume-set hash remained
  `8314a2b0200baffdf78d25ebfe0a9f11c5b22f129f8f33c05f1aa4f859ec896c`.
- Final source/candidate audit re-proved Accepted S2B `accepted/50`, original `pgtest`
  `paused=true` on volume `d81c6381…d241`, original Milvus hash-only
  `43ef203e…67cc`, S4 manifest/restore/acceptance hashes, and the exact C2_0004 candidate marker,
  system ID `7661313446684311592`, landing counts, and zero knowledge/publish rows. No original
  Postgres exec/connection or Milvus client was used.
- The audit corrected an earlier shorthand: the durable candidate has no persistent database/role
  `default_transaction_read_only` setting and its unforced value is `off`. All Task 5.2 candidate
  probes explicitly forced read-only sessions/transactions, the decision store rejects non-
  `disposable` targets, and candidate revision/counts remained unchanged. Task 5.2 therefore claims
  zero candidate writes, not database-level immutable enforcement; persistent candidate hardening is
  a pre-existing operational risk for a future authorized infrastructure slice.
- Task 5.2 is Accepted. Task 5.3 identity RED has not started; no canonical candidate release,
  domain projection, index, provider call, legacy `chat.py`, or production-like cutover is claimed.

## Task 5.2 pattern-fix report

- Reported cases fixed: trace/role content gaps, outcome/group relinking, incomplete decision seed
  validation, field/relationship ownership rebinding, historical context drift, unsafe populated
  migration, and ConfigParser percent interpolation across Alembic test targets.
- Defect class: evidence identities were locally typed but not completely content-bound across
  result reconstruction, mutable identity context, persistence, and migration/replay boundaries.
- Sibling search: all three decision trace families, both assertion/decision families, every
  terminal role/outcome ledger, identity source/output mappings, source-record evolution, all
  Alembic URL setters, migration upgrade/downgrade/race paths, and restart/replay behavior.
- Sibling issues found/fixed: one canonical decision seed helper; deterministic constraint replay;
  batch identity contexts; authoritative pre-write mapping checks; immutable per-family context
  snapshots; two-family populated-upgrade refusal; one percent-escaping configuration boundary.
- Not fixed: offline merge/split identity decisions, temporal intervals, typed domain projections,
  publication, and query institution slots belong to Tasks 5.3–S8. Persistent read-only enforcement
  for the already accepted candidate is recorded but was not mutated in this forbidden-write slice.
- New invariant/helper/contract/test: manifest-bound full seeds, exact deterministic outcomes,
  context-snapshot ledgers, historical-load-after-identity-evolution, membership omission matrices,
  SQLSTATE `55000` two-family preflight, minimum-revision lineage, and rendered-socket URL matrices.
- Remaining systemic risk: Task 5.3 must define reversible identity action context for general
  merge/split outputs; future candidate-writing slices must explicitly decide and verify persistent
  candidate access control before broadening authorized writers.

## Task 5.3 canonical identity-resolution RED acceptance — 2026-07-12

- Slice `s5c-canonical-identity-red` used only the approved OpenSpec and slice contract as plan
  sources. No production/shared-contract/migration/database/provider/index/runtime file or state was
  changed.
- Five scenarios cross one future package-internal
  `canonical_identity_resolution` request/result seam:
  - matching normalized DOI evidence merges two prior Paper identities deterministically and
    order-independently;
  - bilingual/cross-format Professor evidence uses an exact-input, raw-byte-bound recorded
    structured-LLM verdict and rejects changed evidence;
  - same-name Professors with conflicting ORCID/institution evidence remain two active objects under
    `different_entities`, with no terminal reject or LLM override;
  - a named mistaken Company merge is reversed once into an exact disjoint/exhaustive 1-to-N source
    allocation while prior identities/decisions remain history;
  - recovered WAL/FPI Patent evidence links to an existing official canonical identity while the
    V042 ID, source system/key, records, assertions, and mapping lineage remain retained.
- One shared invariant proves unique active source ownership, no missing/duplicate/cross-wired
  assignments, source-to-decision-to-output consistency, active/history separation, exact
  source/record/assertion retention, request policy/run/method binding, output decision linkage, one
  release-scoped manifest per decision, and mutation-sensitive decision/result hashes. Candidate
  verdicts stay independent from applied actions; only direct `same_entity` actions inherit the
  verdict confidence/rationale/trace.
- The intentional RED marker catches only a private sentinel emitted for the exact absent target
  module. A nested or lazy `ModuleNotFoundError` after import is not an accepted xfail.
- Focused verification:
  - `uv run pytest -n0 tests/canonical_v2/test_canonical_identity_resolution_contract.py -q
    --tb=short` -> exactly `5 xfailed`;
  - the same command with `--no-cov --runxfail` -> exactly five failures, each
    `_MissingTargetModule` directly caused by the exact target `ModuleNotFoundError`;
  - focused Ruff check/format and Pyright -> clean, `0 errors, 0 warnings, 0 informations`.
- Commit-checkpoint verification:
  - explicit no-database `uv run pytest -n0 tests/canonical_v2 -q --tb=short` -> `93 passed, 48
    skipped, 9 expected xfails`;
  - `test_database_target_safety.py` plus `test_rebuild_write_gate.py` -> `17 passed`;
  - the four S2 harnesses plus S2B backup/restore -> `32 passed`;
  - S4E checkpoint harness -> `23 passed`;
  - formal `backup_restore.py verify-gate` -> `state=accepted`, `source_count=50`, backup manifest
    `a14c1eab…e59c8`, restore verification `98826e8d…7d231`;
  - strict OpenSpec, `git diff --check`, high-confidence secret scan, Ruff check/format, and Pyright
    all passed.
- The single merged specification/code-quality review found and closed assignment completeness and
  cross-wiring, overly broad xfail masking, recovery create-vs-link, decision/result evidence
  binding, and candidate-verdict/action coupling defects. Final disposition: `APPROVED`, zero open
  Critical/Important findings.
- Read-only source/candidate audit:
  - original `pgtest` remains `paused=true` on exact volume `d81c6381…d241`; no exec or connection
    was made against it;
  - original Milvus was hash-only and remains `43ef203e…67cc`; S4 checkpoint/restore/acceptance hashes
    remain `ab091aac…966b1`, `caf789ae…f0acc`, and `20e11fbe…f58c`;
  - durable candidate container remains network-none/no-port/restart-no at exact ID
    `c0bf2374…b21849`. A forced read-only transaction proved the exact isolated-candidate marker,
    revision C2_0004, landing counts `15/6/21/6/6`, and zero rows in all 20 knowledge/publish tables;
  - the candidate's unforced persistent default remains `default_transaction_read_only=off`. Task
    5.3 made no connection without the explicit read-only setting except the read-only `SHOW` probe
    and claims no database-level immutable enforcement.
- Task 5.4 handoff is explicit: current identity tables cannot express output-specific split
  allocation, immutable decision-time identity context, or complete release/assertion-bound
  decision replay. GREEN must add these effects without inferred backfill, preserve unique current
  ownership separately from terminal history, and keep all identity mutation inside the offline
  build. Migration and downgrade safety receive the extra review/testing permitted by lean
  execution.

## S5D task 5.4 canonical identity GREEN — 2026-07-12T08:40:35Z

- The Accepted Task 5.3 pair scenarios now run through one complete-release
  `CanonicalIdentityResolver.resolve(request) -> result` seam. The engine normalizes DOI, ORCID,
  patent, company, and textual keys; recalls deterministic multi-domain components; applies strong-
  identifier, Professor composite, and recorded structured-LLM rules; and materializes stable no-op,
  create, link, merge, split, reverse, reject, or unresolved effects with generation-safe successor
  IDs.
- Candidate verdicts, applied decisions, manifests, exact decision-time contexts, output-specific
  source allocations, active current owners, terminal history, and lineage remain independently
  content-bound. Pair/component LLM evidence is never copied onto unrelated local decisions;
  contradictory groups, confidence below the versioned threshold, tampered raw bytes, changed
  assignments, unknown lineage, entity conflicts, and rehashed action/output substitutions fail
  validation or degrade without terminally rejecting valid objects.
- C2_0006 adds immutable identity-resolution runs, candidate verdicts, complete context snapshots,
  assertion/source/record edges, output membership, current assignments, and lifecycle lineage.
  Deferred PostgreSQL validators enforce action cardinality, exact non-reject source partitions,
  context/evidence/LLM-edge equality, active-membership/current-assignment equality, canonical state,
  and lineage topology. All identity tables are locked in one parent-to-child order by the store,
  upgrade, and downgrade; downgrade refuses nonempty append-only history with SQLSTATE `55000`.
- The explicit PostgreSQL adapter rechecks the Accepted backup gate and connected disposable marker
  before its first write, locks the full projection, compares existing source rows, complete record
  sets, and assertion fingerprints before inserting a run, persists atomically, forces deferred
  constraints before commit, and reloads the exact typed snapshot. Same-ID/different-content,
  missing parents, row-key substitution, late rollback, and concurrent replay leave no partial
  identity rows. The C2_0005 decision store retains its legacy path but rejects multi-output
  decision-wide ownership rather than inferring an unsafe source mapping.
- One merged specification/code-quality review reported one Critical and five Important findings;
  the vertical repair loop closed complete-batch resolution, prior-context binding, action/output
  hashes, decision-local evidence, exact base-row conflict checks, and deep-module exports. The one
  focused migration/database-safety review reported five Important and one Minor finding; closure
  added deferred release/action validators, exact relational release checks, full parent-first
  writer/downgrade locks, store-vs-downgrade race coverage, tolerant in-development downgrade, and
  lock/trigger inventory assertions. Closure audit found zero open Critical/Important findings; no
  second merged review was performed under lean execution.
- Commit-checkpoint verification passed:
  - focused identity/decision/head matrix: `75 passed` (`29` pure identity, `32` identity Postgres,
    `13` C2_0005 decision compatibility, `1` head inventory);
  - explicit no-database Canonical V2: `124 passed, 79 explicit integration skips, 4 approved
    future-interface xfails`;
  - real S5D disposable Canonical V2 excluding the separately named S4C module: `193 passed, 4
    approved xfails`; independent S4C landing compatibility: `10 passed`;
  - S1 target plus gate safety: `17 passed`; four S2 harnesses plus S2B: `32 passed`; S4E checkpoint:
    `23 passed`;
  - Ruff check/format, targeted Pyright (`0 errors, 0 warnings, 0 informations`), strict OpenSpec,
    formal verification-contract gate, wheel contents, cached diff, high-confidence secret scan,
    and writer-import isolation all passed. The wheel contains C2_0001–C2_0006 and both canonical
    identity modules.
- One initial all-in-one integration invocation produced nine setup errors because the frozen S4C
  test correctly rejected the S5D expected database name. No behavior assertion failed. Running the
  suite on its two explicitly named, independently marked disposable bases produced the passing
  `193 + 10` results above; the safety rejection was not weakened.
- Formal S2B admission remains `state=accepted`, `source_count=50`, backup manifest
  `a14c1eab…e59c8`, and independent restore verification `98826e8d…7d231`. Docker metadata shows
  original `pgtest` still `paused=true` on exact volume `d81c6381…d241`; it was neither entered nor
  connected. Recovery and durable-candidate containers remain network-none/no-port/restart-no.
  SHA-256 hash-only checks matched original/restored Milvus at `43ef203e…67cc` and original/restored
  FPI salvage at `cef8eb6b…bb7`; no Milvus client opened the original.
- A forced read-only candidate transaction re-proved exact isolated-candidate marker, PostgreSQL
  system ID `7661313446684311592`, revision C2_0004, landing counts `15/6/6/21/6`, and zero rows
  across all 20 knowledge/publish tables. S4 manifest, restore, and acceptance hashes remain
  `ab091aac…966b1`, `caf789ae…f0acc`, and `20e11fbe…f58c`.
- The real disposable was container `ef1768e1df66b3a119ba93f975171f045ef2fb99bbee27ddd11f09c4f2c6b501`,
  network `none`, no ports, restart `no`, read-only rootfs, tmpfs PGDATA, PostgreSQL system ID
  `7661462653419962415`, with exact disposable markers. Its S5D and S4C bases ended at C2_0006 with
  zero business rows and no test sibling database. The container, host socket, and wheel artifacts
  were removed; Docker volume-set SHA-256 remained
  `8314a2b0200baffdf78d25ebfe0a9f11c5b22f129f8f33c05f1aa4f859ec896c`.
- Task 5.4 is Accepted under the existing objective-verification authorization. Task 5.5 has not
  started; no durable-candidate migration, original/recovery write, domain projection, release,
  publication, Milvus rebuild, provider call, query/chat behavior, or cutover is claimed.

## Task 5.4 pattern-fix report

- Reported cases fixed: pair-only identity resolution, content-rehash bypasses, decision-wide split
  ownership, missing decision-time context, unsafe same-ID replay, incomplete cross-row constraints,
  and migration/store lock races.
- Defect class: identity effects were locally typed but not completely bound across release-batch
  planning, immutable evidence context, relational projection, current ownership, lifecycle history,
  and concurrent migration boundaries.
- Sibling patterns searched: every action and entity domain; candidate verdict and structured-LLM
  trace paths; source/assertion/record identity; current and terminal mappings; store/load/replay;
  upgrade/downgrade/preflight; C2_0005 ownership compatibility; and query/admin/runtime writer use.
- Sibling issues found/fixed: one release-batch engine and rule-set hash; explicit prior decision
  contexts; per-output allocation; complete base-row comparison; deferred action/release validators;
  one shared parent-first lock order; and fail-closed legacy multi-output ownership.
- Not fixed: temporal intervals, review queues, typed domain projections, eligibility, publication,
  query institution slots, Web augmentation, answer generation, and index work belong to Tasks 5.5+
  and S6–S10.
- New invariant/helper/contract/test: complete context hashes, generation-safe identity IDs, exact
  decision/output binding, multi-component four-domain matrix, create→merge→reverse round-trip,
  low-confidence degradation, relational topology validators, conflict-before-run tests, and real
  store/downgrade serialization.
- Remaining systemic risk: future temporal and aggregate S5 work must preserve these immutable
  decision-time contexts while adding validity/current-history projections; the durable candidate
  remains deliberately behind at C2_0004 until a later explicitly authorized candidate write.

## Explicit non-claims

- S2B acceptance satisfies only the backup prerequisite; each later task still requires its own
  Ready slice, explicit isolated target, and verification loop.
- No populated Canonical V2 candidate, serving projection, or Milvus release is accepted.
- Task 5.3 does not claim Task 5.4 implementation, durable identity storage, or S5 acceptance.
- No original source write or production-like cutover is authorized.

## S5E task 5.5 proportional temporal semantics — 2026-07-12T09:58:35Z

- `CanonicalDecisionEngine.decide` remains the one deep decision seam. Assertions retain
  `observed_at`, optional source publication/event time, and optional natural validity. Selected
  evidence must share one exact interval; equal values/attributes with different intervals remain
  unresolved unless a structured adjudicator selects one exact interval-bound subset.
- Validity membership is half-open `[valid_from, valid_to)`. Field and relationship decisions
  outside their interval remain immutable history while only the as-of-valid subset appears in
  generic current selections. Null endpoints remain open/unknown and are never synthesized;
  `source_event_time` neither replaces `observed_at <= as_of` nor creates validity.
- A Professor A→B affiliation-like scenario retains both generic relationship episodes and their
  evidence, copies exact selected validity into relationship decisions/current selections, treats
  the shared boundary correctly, and returns only B as current. Active, ended-at-boundary, future,
  unknown-validity, static-field, overlapping-conflict, reordered replay, and rehashed tamper cases
  are covered for both field and relationship families.
- All Canonical V2 aware timestamps now use one `CanonicalDatetime` contract that normalizes the
  instant to UTC before JSON, IDs, hashes, fingerprints, or persistence. UTC and `+08:00` inputs
  produce byte-identical results; a real PostgreSQL restart under an `Asia/Shanghai` session proves
  session timezone cannot change durable hashes.
- Validation-time selected-interval disagreement now raises `ValueError`, which Pydantic and the
  PostgreSQL adapter can translate. Generation maps an invalid structured selection to
  `AdjudicationOutputError`; corrupt durable restart remains wrapped as
  `CanonicalDecisionPersistenceError` rather than leaking an engine-private exception.
- No C2_0007 migration was added. C2_0002 and C2_0005 already retain assertion observation/event/
  validity and relationship-decision validity; field current validity is derived from immutable
  selected assertions, avoiding a duplicate temporal store.
- Focused evidence:
  - `test_shared_contracts.py` plus `test_canonical_decision_engine_contract.py` -> `39 passed`;
  - complete `test_canonical_decision_postgres.py` on the named disposable -> `16 passed`;
  - targeted Ruff format/check -> clean; targeted Pyright -> `0 errors, 0 warnings, 0
    informations`.
- Commit-checkpoint regression:
  - explicit no-database Canonical V2 -> `136 passed, 82 skipped, 4 approved xfails`;
  - real S5E disposable Canonical V2 excluding the fixed-name S4C module -> `208 passed, 4 approved
    xfails`;
  - independent fixed-name S4C PostgreSQL compatibility -> `10 passed`;
  - S1 target plus write-gate safety -> `17 passed`; four S2 harnesses plus S2B -> `32 passed`; S4E
    checkpoint harness -> `23 passed`;
  - formal S2B gate -> `state=accepted`, `source_count=50`, backup manifest
    `a14c1eab…e59c8`, restore verification `98826e8d…7d231`;
  - wheel contents include C2_0001–C2_0006, shared contracts, decision engine/store, and identity
    engine/store; strict OpenSpec, diff/whitespace, high-confidence secret scan, and offline-writer
    import isolation passed.
- The one merged specification/code-quality review found two Important defects: offset-dependent
  time hashes/restart and an engine-private validation exception. The repair loop closed both plus
  two Minor audit-wording/fixture-semantics findings. Final disposition is `APPROVED`, with zero open
  Critical/Important findings. Relationship `superseded` interval semantics and projector
  deduplication remain non-blocking Task 5.6/deepening follow-ups.
- Frozen-source/candidate audit:
  - original `pgtest` remains `paused=true` on exact volume
    `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`;
  - original Milvus hash-only check remains `43ef203e…67cc`; verified FPI salvage remains
    `cef8eb6b…bb7`; the initial worktree-relative Milvus path was absent, then the exact frozen
    source path `/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db` matched;
  - recovery lab and durable candidate remain network-none/no-port/restart-no. A forced read-only
    candidate transaction re-proved exact marker, system ID `7661313446684311592`, C2_0004, landing
    `15/6/6/21/6`, and zero rows in all 20 knowledge/publish tables;
  - S4 manifest/restore/acceptance hashes remain `ab091aac…966b1`, `caf789ae…f0acc`, and
    `20e11fbe…f58c`.
- Owned disposable container
  `75195921959bd8f4252cc363fdc447bfdc24c2134eb438b39167934e25c94ce9` used system ID
  `7661567410199961641`, network `none`, no ports, restart `no`, read-only rootfs, tmpfs PGDATA, and
  exact disposable markers. Its S5E/S4C bases ended at C2_0006 with zero business rows and no test
  sibling database. Container, socket root, databases, and wheel-check artifacts were removed;
  Docker volume-set SHA-256 remained
  `8314a2b0200baffdf78d25ebfe0a9f11c5b22f129f8f33c05f1aa4f859ec896c`.
- Task 5.5 is Accepted. Task 5.6 production work did not start in this commit; no durable-candidate
  migration, original/recovery write, Milvus open/rebuild, live provider call, domain projection,
  publication, query/chat change, push, PR, or cutover is claimed.

## Task 5.5 pattern-fix report

- Reported cases fixed: historical/future decisions incorrectly projected as current, exact
  intervals dropped on restart, equal interval-conflicting evidence auto-merged, non-UTC instants
  changed hashes, and validation corruption leaked a private exception.
- Defect class: temporal meaning was retained in row fields but not treated as one canonical,
  hash-stable invariant across decision generation, current projection, model validation, and
  restart reconstruction.
- Sibling patterns searched: every `AwareDatetime` in the shared Canonical V2 contract and engine;
  field and relationship deterministic/LLM paths; selected/current validation; assertion
  fingerprints; PostgreSQL write/load/replay; timezone session behavior; and query/runtime writer
  imports.
- Sibling issues found/fixed: one UTC-normalized timestamp type across all shared contract fields;
  UTC-normalized batch/current fields; one exact-validity primitive; typed generation translation;
  both field/relationship current subsets; faithful validity-interval fixture metadata; and corrupt
  restart wrapping.
- Not fixed and why: `superseded` relationship interval shape is not emitted or specified by Task
  5.5 and belongs to Task 5.6; consolidating the adapter projector is a non-blocking future deepening
  because shared primitives plus result validation already fail closed.
- New invariant/helper/contract/test: `CanonicalDatetime`, `_selected_validity`,
  `_generated_selected_validity`, `_interval_contains`, affiliation transition/membership matrices,
  offset-equivalence hashing, Asia/Shanghai restart, tamper cases, and corruption abstraction.
- Remaining systemic risk: Task 5.6 must freeze review/supersession history before S6 assigns typed
  relationship time semantics; the durable candidate deliberately remains C2_0004 until a later
  explicitly authorized candidate write.
