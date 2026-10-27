# Proposal: publish-enriched-professors-pilot

Human doc: `docs/plans/2026-10-26-systematic-completion-gates.md` §3.13.

## Why

The enrichment pilot filled 18 thin professor biographies in the collection
database, but nothing reached the serving line: it reads the manual-recall store,
which is loaded into memory at boot and had no professor records.

## What Changes

1. New operator script `publish_professor_pilot.py`: reads enriched professors
   from the collection DB, builds the professor payload, and adds them to the
   manual-recall store **through the same store class the service uses**.
2. Deterministic record ids (`pilot-<professor_id>`) make re-runs idempotent.
3. Operational guard: back up `var/manual-recall-v1` first (the runbook records
   it), run with `--dry-run`, then write and restart.

## Impact

- 18 professor records (store 17 → 35 points) now serve enriched biographies with
  citations.
- Reversible: the store's tombstone API, or restore the backup directory.

## Out of scope

- The remaining 2,134 thin professors (batch decision).
- Rebuilding the pack so the summaries also enter the vectors.
