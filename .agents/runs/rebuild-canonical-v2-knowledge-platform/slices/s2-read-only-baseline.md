# Slice Contract: S2 Read-only Baseline and Threshold Freeze

## Status

Ready. S1 was accepted at commit `a58184c`; no later slice has started.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Tasks: 2.1–2.5 only
- Accepted predecessor: S1 database-target safety

## Goal

Freeze an auditable, read-only account of available recovery/historical evidence, PRD domain and
relationship coverage, regression/challenge scenarios, current measurable baseline, and acceptance
thresholds before any Canonical V2 schema, replay, recollection, or feature implementation starts.

## User / operator effect

Later reconstruction decisions are judged against stable PRD outcomes and known evidence limits,
not stale row counts, a single workbook, or metrics redefined after implementation.

## Non-goals

- No Canonical V2 schema, migration, source replay, parsing, identity resolution, enrichment,
  recollection, Web/LLM provider call, Milvus client open, or index build.
- No write to any Postgres database, original/recovery file, existing baseline, or source artifact.
- No claim that a legacy baseline is current when its database/index/provider substrate is gone.
- No fixed-answer expansion of the workbook into the product requirement.

## Allowed scope

- Read/hash repository PRDs, workbook, committed fixtures, historical baseline reports, forensic
  checkpoint documents, salvage dump, and recovery-copy metadata.
- Read recovery-lab database catalogs/counts only through a session forced to
  `default_transaction_read_only=on`; the two recovery checkpoint databases remain evidence, never
  migration/test targets.
- Hash the original Milvus file without opening a Milvus client; inspect a separately verified copy
  only if one already exists and its parent hash is proven.
- Create/update only S2 evidence under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2/`, this contract, OpenSpec tasks 2.1–2.5,
  acceptance thresholds/corpus status, change log, and verification evidence.

## Forbidden changes

- Original `pgtest`, port `15432`, source volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`.
- Original `apps/miroflow-agent/milvus.db` client access or mutation.
- Any SQL lacking a read-only session proof; any DDL, DML, Alembic, reset, seed, restore, or replay.
- Recovery checkpoint mutation, new database creation, live provider calls, secret reads, production
  code, domain behavior, test expectations, dependency changes, broad formatting, push, or cutover.

## Required outputs

- `s2/source-inventory.json` — source identity, path/DB, kind, size/count, hash, lineage, readability,
  authority, and limitation.
- `s2/build_source_inventory.py`, its test, and `recovery-db-readonly-snapshot.json` — deterministic
  read-only inventory generation and the separately captured database proof input.
- `s2/source-coverage-matrix.md` — Professor/Company/Paper/Patent objects, typed sub-objects,
  relation families, provenance, temporal/quality fields, retrieval paths, source coverage, and gaps.
- `s2/corpora/regression-v1.jsonl` and `challenge-v1.jsonl` — versioned scenario families with source,
  protected constraints, expected evidence/interaction behavior, and review status.
- `s2/corpus-manifest.json` — corpus hashes, counts by family/domain/query type, gold authority, and
  approval state.
- `s2/baseline-report.json` — measured/legacy/unavailable status for coverage/reach, Recall@K,
  Precision@K, rank, intent, support/citation, Universal Web, multi-turn, latency, and provider cost.
- `s2/acceptance-thresholds.json` — metric, population/corpus version, hard/soft gate, threshold,
  rationale, source, and approval state without lowering PRD minima.
- `s2/review.md` plus updated parent verification evidence.

## Required checks

- Every dynamic database command proves `transaction_read_only=on`, current database, and server
  identity in the same session before count queries.
- Source hashes/counts are recomputed where readable and stale/conflicting records remain explicit.
- Workbook cases are seed scenarios; PRD families and controlled variants supply broader coverage.
- Legacy metrics retain their original corpus/time/substrate labels and cannot silently become S2
  acceptance measurements.
- No same-model-generated expectation becomes human-reviewed gold without user review.
- JSON/JSONL parses, manifests match file hashes/counts, OpenSpec strict validation passes, and
  original source/Milvus hashes plus `pgtest paused=true` match after the run.

## Stop conditions

- Any command would connect to `pgtest`, port `15432`, open original Milvus, write a database/file,
  invoke a real provider, expose a secret, or require recovery replay.
- Recovery sources disagree with their frozen identity/hash without an explained new checkpoint.
- A proposed threshold lowers a PRD minimum, mixes incompatible populations, or has no rationale.
- A corpus case lacks source, observable expected behavior, or review status.
- Current behavior cannot be distinguished from historical/legacy evidence.

## Done means

- Tasks 2.1–2.5 have reproducible evidence and all required outputs parse/hash consistently.
- Thresholds retain all PRD lower bounds and explicitly gate missing dimensions.
- Regression/challenge corpora are versioned and user-reviewed/accepted.
- Source invariants remain unchanged, independent review accepts S2, and only then may S3 become
  Ready.
