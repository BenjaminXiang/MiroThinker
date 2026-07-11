# Slice Contract: s2b-source-backup-restore

## Status

Specified. It may become Ready only after S2 tasks 2.4–2.5 are complete, backup and restore target
paths/capacity are recorded, and the source inventory checkpoint remains unchanged.

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
- Original source invariants still match, review evidence is complete, and the user accepts S2B.
- Only then may task 3.2 or any Canonical V2/landing write slice become Ready.
