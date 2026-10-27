# Acceptance: unify-collection-as-source-of-truth

| # | Criterion | Target | Evidence |
|---|---|---|---|
| A1 | Professor rows in collection DB | ≥ 3,958 | count query |
| A2 | Paper rows in collection DB | ≥ 24,520 | count query |
| A3 | Sampled field parity | ≥ 98% | 50-record comparison |
| A4 | Backfill idempotency | 0 new rows on rerun | second run count |
| A5 | Gap visible | per-domain gap in admin status | status payload |

Status: **proposed** — plan only; P0 not started.
