# Acceptance: guard-allowlist-auto-publish

| # | Criterion | Evidence |
|---|---|---|
| A1 | Guard refuses a gutted list | unit tests (too small / shrink) |
| A2 | Guard allows normal weeks | unit test (growth, ±10%) |
| A3 | Previous generation kept | unit test; live run left `.prev` next to the allowlist |
| A4 | Runs unattended | `env -i` run on the host: full refresh, metrics + allowlist published (536) |
| A5 | Rollback is one file | restore `.prev`, overlay hot-reloads |

Status: **accepted** (2026-10-27 01:23 CST).
