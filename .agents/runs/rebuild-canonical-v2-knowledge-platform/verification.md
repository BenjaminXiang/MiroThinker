# Verification: rebuild-canonical-v2-knowledge-platform

## Current status

S1 database-target safety was accepted by the user at 2026-07-11T05:39:19Z. Tasks 1.1–1.5 have
RED/GREEN, real isolated Postgres, source-invariant, review, and acceptance evidence. No later slice
has started.

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

1. S2 baseline report and threshold freeze (tasks 2.4–2.5).
2. S2B complete source backup manifest and independent restore verification (task 2.6). Until this
   is reviewed and Accepted, task 3.2 and every Canonical V2/landing write remain blocked.

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
- Added task 2.6 and Specified slice `slices/s2b-source-backup-restore.md`. Task 3.2 and every
  Canonical V2 schema, landing, canonical, publication, or index write remain blocked until S2B is
  reviewed and Accepted. Read-only tasks 2.4–2.5 may continue.
- Canonical identity authority is now explicit: normalization, candidate recall, deterministic
  rules, structured LLM adjudication, human review, and merge/split publication belong to versioned
  offline builds. Query/answer paths may resolve user references against an accepted release but
  must emit an offline review gap instead of mutating identity/source mappings.
- This audit changed contracts only. It did not create a backup, run a restore, access a database,
  open Milvus, or authorize any rebuild write; task 2.6 remains incomplete.

## Explicit non-claims

- S1 acceptance does not authorize S2 writes, recovery replay, broad migration suites, or any
  production-like cutover without the next Ready slice contract.
- No Canonical V2 database or Milvus release is accepted.
- No original source write or production-like cutover is authorized.
