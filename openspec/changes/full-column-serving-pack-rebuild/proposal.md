# Proposal: full-column-serving-pack-rebuild

> Phase 4 of Epic `fix-round-1-serving-pipeline` (data line, parallel to the
> code line; opened 2026-08-19 in a dedicated worktree).
> Human docs: round plan `docs/plans/2026-08-17-systematic-fix-round-1.md` ·
> this line's own log `docs/plans/2026-08-19-p4-data-rebuild-log.md`.
> Data-affecting: YES (new serving pack; no serving-code behavior change).

## Why

The 2026-08-17 coverage audit traced P5/P8's data roots to a thin serving
pack: ~5.7k objects served vs ~45k full-column source objects; patent
relations effectively empty (G4: relationship lane (0,0)); company coverage
27% with rich fields dropped. The code line is fixed and verified (R1); the
data ceiling must be raised or retrieval quality stays capped.

## What Changes

1. Rebuild the serving pack from the FULL-COLUMN legacy Postgres source
   (~45k content-bearing objects) through the existing s12 runner pipeline
   (same parser/policy/model versioning discipline; new run-id, NEW
   disposable database + NEW /var/tmp staging+index roots — never write the
   live s12f paths).
2. Relationship backfill: company↔patent links and professor↔paper links as
   additional source batches (existing batch discipline).
3. Embeddings: school API in batches (rate-limit fallback to hosted API per
   the recorded ruling).
4. Deliverable: serving-pack v2 + **reconciliation report** (per exit
   criterion ③: domain counts, field non-null rates, four-path reachability
   sampling vs the audit baseline).

Out of scope: serving-code changes, hot updates (data v2 ships via rsync
switch after acceptance, not via release/customer-test).

## Acceptance sketch

- Reconciliation report meets the exit-criterion bar (counts/non-null/
  reachability) and is archived under `.agents/runs/full-column-serving-
  pack-rebuild/`.
- The v2 pack serves smoke queries from a scratch port without touching the
  live 18188 instance.
