# Tasks: unify-collection-as-source-of-truth

## P0 — mapping and design
- [ ] 0.1 Field mapping table (professor/paper) and enum decisions.
- [ ] 0.2 Id strategy (keep pack ids, record provenance via run_id).
- [ ] 0.3 Dry-run: count conflicts against the existing 220/555 rows.

## P1 — professors
- [ ] 1.1 Backfill script (bulk insert, single transaction, idempotent).
- [ ] 1.2 Verify counts and 50-record parity.
- [ ] 1.3 Enrichment pipeline can select the full roster.

## P2 — papers
- [ ] 2.1 Backfill with DOI/title dedupe.
- [ ] 2.2 Verify counts, duplicate rate and parity.

## P3 — guard
- [ ] 3.1 Daily pack-vs-database gap check + admin surfacing.
