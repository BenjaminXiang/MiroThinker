# S2B Review: Complete Source Backup and Independent Restore

## Status

Accepted at `2026-07-11T16:11:23Z` under the user's instruction to self-approve tasks when objective
verification or deep technical review can decide. Task 2.6 is complete. No Canonical V2 schema,
landing, canonical, publication, index, or production-like write occurred in this slice.

## Bound acceptance evidence

- Backup manifest SHA-256:
  `a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8`.
- Restore verification SHA-256:
  `98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231`.
- Acceptance record SHA-256:
  `3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b`.
- Run ID: `canonical-v2-s2b-20260711T152222Z`.
- Backup root: `/md1/mirothinker-backups/canonical-v2-s2b-20260711T152222Z`, device `2305`.
- Restore root: `/var/tmp/mirothinker-restores/canonical-v2-s2b-20260711T152222Z`, device `66306`.
- Primary evidence device: `2049`. All three devices are distinct and both targets remained above
  the 50,000,000,000-byte capacity floor.

The immutable manifests retain Candidate-state metadata; `acceptance-record.json` is the explicit
acceptance overlay bound to their exact hashes. Any manifest edit invalidates admission.

## Backup result

- All 48 frozen inventory records were expanded to 42,556 logical members and 16,447,082,378 bytes.
  Content-addressed storage contains 40,075 deduplicated SHA-256 objects totaling 14,290,920,139
  bytes; every source/copy hash matched and every copy was inode-independent.
- Original PostgreSQL volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`
  was mounted `rw=false` while `pgtest` remained paused. Its 3,762-entry archive is 418,849,280 bytes
  with SHA-256 `509cf117eae7ae3069e8d41d247044cd43168086b33b231590d9605546288da9`.
- The complete forensic/recovery tree, excluding only the active derived recovery-lab PGDATA,
  contains 24,230 entries. WAL/FPI, ext4, salvage, checkpoint dumps, recovery metadata/tools, and
  forensic PostgreSQL bytes are archived in 2,212,828,160 bytes with SHA-256
  `59f5901ecae7f612848ce7142031ad1efa1c366ce00a50b99019732b2d4d1055`.
- The excluded active lab PGDATA is not original evidence: its immutable source dump/checkpoint
  inputs are in the forensic archive, while the original PostgreSQL volume is backed separately.

## Independent restore result

- All 48 inventory records rematerialized to the restore device with 42,556 member hashes and 86
  deterministic JSON/JSONL/XLSX/PDF/SQLite/archive/bounded-read probes; all passed.
- The forensic tree's 24,230-entry manifest matched byte-for-byte. `pg_restore --list` read the
  salvage and checkpoint dumps (29 and 350 TOC lines), PG16 `pg_waldump` decoded a retained WAL
  record, and all 20,427 sampled FPI page files were exactly 8,192 bytes.
- PostgreSQL first restored to a labeled exact-materialization volume whose 3,762-entry tree matched
  the source. A separate labeled probe volume removed only its copied `postmaster.pid`, started with
  `network=none`, no host ports, and a read-only root filesystem, then proved database
  `miroflow_real`, revision `V042`, 42 public tables, and zero Company/Professor/Paper/Patent rows.
- Original Milvus SHA-256 remained
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
  A third verified probe copy—not the original or first restored copy—opened six collections with
  70,780 rows. Its hash was unchanged by the client probe.

## Admission behavior

`backup_restore.py verify-gate` requires exactly all frozen source-record fingerprints plus
`original_postgresql_volume` and `forensic_recovery_tree`; complete independent restore status;
passed PostgreSQL, Milvus, and forensic probes; and an Accepted record bound to the exact two
manifest hashes. Missing source, hash failure, hardlink dependence, failed restore/probe, or changed
acceptance hash fails before a future rebuild write.

## Pattern-fix report

- Reported case fixed: yes; forensic extraction no longer inherits an undeclared writable volume.
- Defect class: L3 shared boundary guard + C1 test-matrix gap.
- Invariant enforced: every S2B tool container has an exact persistent-mount allowlist; a Postgres
  image's implicit PGDATA volume is replaced by bounded tmpfs unless the named probe volume is the
  explicit target; temporary containers are removed with volumes.
- Sibling patterns searched: PostgreSQL manifest/archive, forensic manifest/archive/extract/verify,
  PostgreSQL materialize/probe, and repository S2B Docker references.
- Sibling issues found/fixed: all affected S2B tool-container commands use the shared invariant;
  seven attributable anonymous dangling volumes were empty, unreferenced, and removed by exact ID.
- Not fixed and why: older unrelated anonymous/Compose volumes predate this run and were not touched.
- New invariant/helper/test: `validate_container_mount_policy` and its implicit-volume/tmpfs matrix.
- Remaining systemic risk: future ad-hoc Docker commands must use the helper/allowlist pattern; the
  retained materialized and probe volumes are intentionally labeled acceptance evidence.

## Verification and non-claims

- Pre-acceptance suite: 32 tests passed; Ruff clean; Pyright reported zero errors/warnings;
  full source-inventory regeneration remained byte-identical; strict OpenSpec validation passed.
- Original `pgtest` remained `paused=true`; original Milvus and salvage hashes matched; recovery lab
  remained network-none/no-port. No provider call or recollection occurred.
- S2B acceptance removes the backup prerequisite for task 3.2. The next OpenSpec task remains 3.1,
  and no production-like cutover or original-source cleanup is authorized.
