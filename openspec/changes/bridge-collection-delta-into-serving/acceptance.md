# Acceptance: bridge-collection-delta-into-serving

| # | Criterion | Evidence |
|---|---|---|
| A1 | Delta detected | dry-run: 3 companies, 47 papers missing from the pack |
| A2 | Published | `written: 3` + `written: 47`; store points 52 → 102 |
| A3 | Answers cite local data | `{"type":"company","id":"local-source-…","url":null}` |
| A4 | No regression | eval gate 78/120, product 26/27, verdict pass |
| A5 | Reversible | store backup `manual-recall-v1.backup-20261027-2`; deterministic ids |

Status: **accepted** (2026-10-27 11:00 CST).
