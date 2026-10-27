# Proposal: unify-collection-as-source-of-truth (Epic)

Human doc: `docs/plans/2026-10-28-unify-collection-source-of-truth.md`.

## Why

The serving pack holds 3,958 professors and 24,520 papers; the collection
database holds 220 and 555. The pack is built from external source bundles, not
from the collection database, so:

- most pack records cannot be browsed, edited or enriched through the collection
  database;
- anything written to the collection database survives only until the next
  rebuild (the rebuild reads the source bundles and would drop it).

## What Changes (phased)

1. **P1 professors**: backfill all pack professors into the collection database
   (professor + affiliation + source page), idempotent by pack id.
2. **P2 papers**: backfill all pack papers, deduped by DOI then normalized title.
3. **P3 consistency guard**: a daily check that pack records exist in the
   collection database, surfaced in the admin status.
4. **P4 (separate change)**: make the build read a collection-database export
   instead of external source bundles.

## Impact

- After P1/P2 the collection database is a superset of the pack and becomes the
  operational surface (enrichment, corrections, browsing).
- P1–P3 do not change serving behaviour; P4 changes the build's source contract.

## Out of scope

- Changing the serving pack contents (that stays a rebuild concern).
- Migrating historical identifiers.
