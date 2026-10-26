# Acceptance: hot-swap-professor-allowlist

| # | Criterion | Evidence |
|---|---|---|
| A1 | Reload on change | unit test; host check: rewritten file → new value visible (9876) without restart |
| A2 | Reuse while unchanged | unit test |
| A3 | Atomic publish | unit test (no `.tmp` remains); host swap left no staging file |
| A4 | Service stays healthy | `/api/health` 200 after the swap |
| A5 | Reversible | unset the variable or restore the previous file |

Status: **accepted** (2026-10-27 01:15 CST). Deployed; host-verified reload and
atomic swap.
