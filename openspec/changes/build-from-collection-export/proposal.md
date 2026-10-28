# Proposal: build-from-collection-export (P4)

Human doc: `docs/plans/2026-10-28-p4-build-from-collection-export.md`.

## Why

The build reads external source bundles, so everything backfilled into the
collection database (P1: 3,956 professors, P2: 24,558 papers) is invisible to a
rebuild — and would be dropped by it. The collection database is now a superset
of the pack, which makes it the right source.

## What Changes

1. `export_collection_sources.py`: per domain, export collection rows as
   released-object JSONL, deterministic, content-addressed (`<sha256>.source`),
   with a manifest fragment.
2. `validate_export_sources.py`: run the build's real released-objects mapper over
   a sample, so schema problems surface in seconds instead of after a 20-hour
   build.
3. Manifest assembly: DB-export members plus the source bundles that remain
   authoritative (mixed manifest).
4. Build consumes the new manifest **unchanged** — the contract (manifest + hashed
   members) is preserved.

## Impact

- Rebuilds no longer drop database writes; imported/enriched data survives.
- Reproducibility kept: same snapshot → same bytes → same hashes.
- Rollback: old pack, index and manifest stay in place.

## Out of scope

- Changing the builder's internals.
- Removing the external source bundles (they stay for domains not yet migrated).
