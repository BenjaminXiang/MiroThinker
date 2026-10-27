# Acceptance: allow-real-upload-after-dry-run

| # | Criterion | Evidence |
|---|---|---|
| A1 | Dry run does not block | unit test `test_a_dry_run_does_not_block_a_real_upload` |
| A2 | Real dedupe unchanged | existing store tests still pass |
| A3 | Customer unblocked | real upload 202 after removing the dry-run record |
| A4 | Deployed | pending next restart window |

Status: **candidate** — code + tests landed; deploy pending.
