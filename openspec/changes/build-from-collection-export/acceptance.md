# Acceptance: build-from-collection-export

| # | Criterion | Target | Evidence |
|---|---|---|---|
| A1 | Export determinism | identical sha256 on rerun | two export runs |
| A2 | Mapper acceptance | 100% of sampled rows per domain | validator report |
| A3 | Ingest rehearsal | counts match, hashes self-check | rehearsal log |
| A4 | Full rebuild | four domains match the database within baseline | pack counts vs DB counts |
| A5 | No regression | eval gate >= 80/120, replay 7/7 | gate output |
| A6 | Rollback | old pack/index/manifest retained | runbook |

Status: **proposed** — design and slicing only; S0 not started.
