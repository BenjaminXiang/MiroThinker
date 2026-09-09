# Slice Contract: s2b-source-backup-restore

## Status

Accepted at `2026-07-11T16:11:23Z` under the user's explicit authorization to self-approve when
objective verification can decide. S2 tasks 2.4–2.5 were already Accepted; target identity/capacity,
complete backup, independent restore, format-specific probes, source invariants, and fail-closed
admission all passed. This acceptance satisfies the task 2.6 prerequisite but does not itself start
or authorize a production-like cutover.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `2.6`
- Depends on: Accepted S1 database-target safety and completed S2 source inventory

## Goal

Create content-addressed backups for every required original, forensic, recovery, and historical
source family; independently restore or materialize those backups into isolated targets; and obtain
reviewed evidence that the complete source set is recoverable before any Canonical V2 or landing
write begins.

## Non-goals

- Create or migrate the Canonical V2 database.
- Replay sources into landing or construct canonical identities.
- Repair, mutate, compact, recollect, or delete any original source.
- Open the original Milvus file with a client or start the original Postgres container.
- Treat hash-only inventory or the existing salvage-only restore as complete backup acceptance.

## Allowed scope

- Read-only/hash access to inventoried originals and forensic/recovery artifacts.
- A dedicated read-only mount of the quiesced original Postgres volume solely for backup copying.
- Writes only to named backup targets, independent restore/materialization targets, and this slice's
  evidence artifacts.
- Opening Postgres/Milvus clients only against verified restored copies in network-none/no-port
  isolation.
- Deterministic scripts/tests for manifest completeness, copy independence, hashes, recovery probes,
  and fail-closed write admission.

Required source families:

- original PostgreSQL volume or equivalent restorable backup;
- original Milvus database file;
- WAL/FPI, ext4, salvage dump/IDs, and recovery metadata/checkpoints;
- every inventoried historical SQLite, JSONL, XLSX, PDF, cache, release, and raw-source family.

## Ready preflight

- Run ID: `canonical-v2-s2b-20260711T152222Z`.
- Frozen inventory: 48 records, 16,447,082,378 recorded bytes, SHA-256
  `83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09`.
  Re-running the accepted builder over all current members produced the same bytes and hash.
- Original PostgreSQL volume:
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`;
  a Docker-inspected `rw=false` mount read as UID 999 reported 407,844 KiB and 3,762 files. The
  original `pgtest` remained paused before and after the probe.
- Backup root: `/md1/mirothinker-backups/canonical-v2-s2b-20260711T152222Z`, device `2305`,
  3,109,684,568,064 bytes available at preflight. The path did not exist.
- Independent materialization root:
  `/var/tmp/mirothinker-restores/canonical-v2-s2b-20260711T152222Z`, device `66306`,
  1,276,234,944,512 bytes available at preflight. The path did not exist.
- Primary workspace/recovery evidence is on device `2049`. Backup, restore, and primary evidence
  devices are pairwise distinct. PostgreSQL restore volumes must also have new Docker volume IDs.
- The conservative capacity floor is 50,000,000,000 bytes on each target, covering the inventory,
  raw PostgreSQL backup/restore, the required WAL/FPI/recovery tree, manifests, and probe copies.
- Original Milvus and salvage hashes still matched at `2026-07-11T15:25:02Z`; the recovery lab
  remained network-none/no-port. No database or Milvus client was opened during preflight.

## Execution plan

1. Add RED contract tests for target separation, complete inventory/family coverage, copy
   independence, hash equality, restore evidence, and fail-closed rebuild admission.
2. Implement deterministic content-addressed copy/manifests and run them only against the named
   backup root, with the original PostgreSQL volume mounted `rw=false` and original Milvus treated
   as bytes only.
3. Materialize every backup into the named independent root, compare hashes/member manifests, and
   run bounded JSON/JSONL/XLSX/PDF/SQLite/archive/recovery probes.
4. Restore PostgreSQL into new no-network/no-port volumes and inspect Milvus only through the
   verified restored copy; record identities, schemas/collections, counts, and failures.
5. Run admission, source-invariant, strict OpenSpec, static, and test checks; update review and mark
   task 2.6 Accepted only if every hard gate passes.

## Acceptance checkpoint

- Backup manifest: 50/50 required source records, SHA-256
  `a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8`.
- Restore verification: 50/50 passed, SHA-256
  `98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231`.
- Acceptance record: SHA-256
  `3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b`.
- Frozen inventory backup covered 42,556 logical members and 16,447,082,378 bytes. The original
  PostgreSQL volume and the forensic recovery/WAL/FPI tree are additional independently archived
  sources.
- PostgreSQL exact materialization matched 3,762 tree entries; a second network-none/no-port probe
  started `miroflow_real` at `V042`, found 42 public tables, and confirmed zero rows in the four core
  domain tables.
- The verified Milvus probe copy opened six collections with 70,780 rows; neither original nor first
  restored copy changed. The forensic tree matched all 24,230 entries and passed dump, WAL, FPI, and
  ext4 bounded probes.
- A systemic Docker-image implicit-volume defect was repaired with a persistent-mount allowlist,
  explicit PGDATA tmpfs override, and `docker rm -v`. Seven attributable anonymous volumes were
  proved empty/unreferenced and removed; no recent anonymous dangling volume remained.
- Full Candidate verification passed 32 tests, Ruff, Pyright, inventory regeneration, artifact/hash,
  capacity/target, source-invariant, admission, and strict OpenSpec checks before acceptance.

## Forbidden changes

- Any write, migration, parser output, or repair against an original source path/volume.
- Any Canonical V2 schema, landing, canonical, publication, or index write.
- Any hard-link backup or manifest entry whose backup resolves to original bytes/path identity.
- Any restore target shared with an original or backup location.
- Any unpause/start/exec of the original `pgtest` container.
- Any Milvus client open on `apps/miroflow-agent/milvus.db`.
- Any production-like cutover, active pointer/alias mutation, provider recollection, or cleanup.

## Expected unchanged behavior

- Original `pgtest` remains paused and its volume identity remains unchanged.
- Original Milvus, forensic checkpoint, salvage, and historical source hashes remain unchanged.
- Recovery checkpoint databases remain read-only evidence and are not promoted.
- S2 corpus/threshold versions and current application behavior remain unchanged.

## Required checks

- Preflight target identity, free-space/capacity, no-hard-link/canonical-path, and source hash checks.
- Manifest completeness against the frozen `source-inventory.json`, with explicit family coverage.
- Source-to-backup byte size and SHA-256 equality for every file/artifact or deterministic family
  manifest equality for large families.
- PostgreSQL restore in a network-none/no-port isolated target with current database, revision,
  schema/table, and agreed count/hash probes.
- Milvus inspection only on a verified copy, recording collection/schema/count or equivalent probes.
- Backup-to-second-target materialization plus SHA-256 and bounded readability/replay probes for
  WAL/FPI, salvage, SQLite, JSONL, XLSX, PDF, cache, release, and raw-source families.
- RED/GREEN admission tests proving incomplete/mismatched/unrestored manifests reject task 3.2 and
  all rebuild writes before their first write.
- Post-run source pause/identity/hash invariants and strict OpenSpec validation.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2b/backup-manifest.json`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2b/restore-verification.json`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2b/review.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- OpenSpec `tasks.md`, `acceptance.md`, and `change-log.md`

## Stop conditions

- Original pause/identity/hash changes or any source is not provably read-only.
- Backup/restore target resolves to an original, existing evidence checkpoint, or production-like
  location.
- Required family is missing, copy/restore hash mismatches, capacity is insufficient, or a recovery
  probe fails.
- PostgreSQL or Milvus recovery requires opening the original instead of a verified copy.
- The proposed implementation would begin Canonical V2/landing writes before this slice is Accepted.
- Rollback or cleanup would delete the only verified backup or recovery evidence.

## Done means

- Every required family is present in an immutable reviewed backup manifest with matching hashes.
- Every backup has passed an independent format-appropriate restore/materialization verification in
  a distinct isolated target.
- Fail-closed admission tests prove task 3.2 and all rebuild writes require the accepted manifest.
- Original source invariants still match, review evidence is complete, and S2B has reviewed
  acceptance under the user's explicit self-approval authorization.
- Only then may task 3.2 or any Canonical V2/landing write slice become Ready.
