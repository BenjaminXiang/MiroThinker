# Acceptance: unify-collection-as-source-of-truth

| # | Criterion | Target | Evidence |
|---|---|---|---|
| A1 | Professor rows in collection DB | 3,956 (3,958 pack = 220 existing + 3,736 inserted, 2 merged) | count query |
| A2 | Paper rows in collection DB | 24,558 (24,003 inserted + 555 existing) | count query |
| A3 | Sampled field parity | ≥ 98% | 50-record comparison |
| A4 | Backfill idempotency | 0 new rows on rerun | rerun: `to_insert: 0` |
| A5 | Gap visible | per-domain gap in admin status | status payload |

Status: **P0–P2 accepted** — pack ⊆ collection for professors and papers; P3 (guard) and P4 (build from DB) remain.
