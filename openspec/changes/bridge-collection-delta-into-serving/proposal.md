# Proposal: bridge-collection-delta-into-serving

Human doc: `docs/plans/2026-10-27-uploaded-data-searchability.md`.

## Why

Two upload paths exist and only one is searchable:

- company documents (PDF/Word) go to the manual-recall store and participate in
  retrieval;
- XLSX bulk imports write canonical rows into the collection database, while the
  serving line reads a frozen pack — so imported companies/papers were silently
  unreachable. Evidence: a company that exists only in the collection database
  produced eight citations, all web pages, and no local source.

## What Changes

1. New operator script `publish_collection_delta.py`: reads the collection
   database, diffs against the pack by display name/title, and publishes the
   missing rows into the manual-recall store using the service's own store class.
2. Deterministic record ids (`delta-<domain>-<pk>`) keep re-runs idempotent.
3. Runbook: back up the store, run the script, restart the service (the store is
   loaded at boot).

## Impact

- Imported records become answerable with a `local-source` citation without a
  pack rebuild.
- Transitional by design: the store is a linear scan and publishing requires a
  restart; large volumes belong in the next pack rebuild.

## Out of scope

- Patents (the collection database has no patent rows today).
- Exact-identifier matching (name collisions are accepted for now).
