# Acceptance: unify-collection-as-source-of-truth

| # | Criterion | Target | Evidence |
|---|---|---|---|
| A1 | Professor rows in collection DB | 3,956 (3,958 pack = 220 existing + 3,736 inserted, 2 merged) | count query |
| A2 | Paper rows in collection DB | 24,558 (24,003 inserted + 555 existing) | count query |
| A3 | Sampled field parity | ≥ 98% | 50-record comparison |
| A4 | Backfill idempotency | 0 new rows on rerun | rerun: `to_insert: 0` |
| A5 | Gap visible | per-domain gap JSON daily, baseline-aware | `var/pack-collection-gap.json` (`ok=true`) |

Status: **P0–P3 accepted** — pack ⊆ collection for all four domains (gaps within baseline), daily guard running; P4 (build from DB) remains.
