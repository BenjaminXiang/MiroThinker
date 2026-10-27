# Acceptance: unify-collection-as-source-of-truth

| # | Criterion | Target | Evidence |
|---|---|---|---|
| A1 | Professor rows in collection DB | 3,956 (3,958 pack = 220 existing + 3,736 inserted, 2 merged) | count query |
| A2 | Paper rows in collection DB | ≥ 24,520 | count query |
| A3 | Sampled field parity | ≥ 98% | 50-record comparison |
| A4 | Backfill idempotency | 0 new rows on rerun | rerun: `to_insert: 0` |
| A5 | Gap visible | per-domain gap in admin status | status payload |

Status: **in progress** — P0 and P1 accepted; P2 (papers) pending the `canonical_source` migration.
