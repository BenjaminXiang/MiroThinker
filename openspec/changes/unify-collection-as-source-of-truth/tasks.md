# Tasks: unify-collection-as-source-of-truth

## P0 — mapping and design
- [x] 0.1 Field mapping table (professor/paper) and enum decisions.
- [x] 0.2 Id strategy (keep pack ids, record provenance via run_id).
- [x] 0.3 Dry-run: 3,736 professors / 24,003 papers to insert; 2 name collisions; 55 papers collection-only.

## P1 — professors
- [x] 1.1 Backfill script (bulk insert, single transaction, idempotent).
- [x] 1.2 Counts (3,956) and 3/3 sample parity; rerun inserts 0.
- [x] 1.3 Enrichment can select 2,024 padded professors via `--padded-only`.

## P2 — papers
- [ ] 2.1 Backfill with DOI/title dedupe.
- [ ] 2.2 Verify counts, duplicate rate and parity.

## P3 — guard
- [ ] 3.1 Daily pack-vs-database gap check + admin surfacing.
