# Acceptance: add-professor-projection-metrics-api

| # | Criterion | Evidence |
|---|---|---|
| A1 | Endpoint serves metrics | unit test `test_returns_metrics_when_configured`; live check after deploy |
| A2 | Bounded errors | 3 unit tests (503/404/500) |
| A3 | Unattended run resolves paths and publishes | 6 unit tests; one real run on the host |
| A4 | Failure leaves state intact | wrapper exits before the refresh when the pack is missing (unit test) |
| A5 | Reversible | endpoint has no side effects; remove the cron line and the env var to disable |

Status: **accepted** (2026-10-27 01:05 CST). Live: endpoint answers 401 without a
session (route present, gate active) and the metrics file on the host carries the
refreshed numbers; the wrapper ran once for real on the host — projection rebuilt
from the 1 MB edge cache, coherence scored through the managed key, metrics
published (allowlist 536 / 6,132 papers). Weekly cron installed (Sunday 03:00).
