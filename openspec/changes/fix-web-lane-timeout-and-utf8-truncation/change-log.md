# Change Log: fix-web-lane-timeout-and-utf8-truncation

## 2026-08-28 — R1: three-chain repair, verified live

- `knowledge_serving_isolated.py`:
  - NEW `_utf8_truncated()` (encode + byte cap + back-off to a complete
    character boundary); replaced all 4 `.encode("utf-8")[:cap]` snapshot
    sites (web lane + person/theme/relation probe evidence builders).
  - `_DualWebLaneAdapter`: per-provider attempt timeouts
    (`bocha-v1` ≥ 2.0 s, `serper-v1` ≥ 4.0 s, scaling `timeout_ms * 0.0009`)
    replacing the shared `timeout_ms * 0.00045` formula; NEW
    `_outer_wait_seconds()` per-provider future wait (attempt + 0.5 s);
    page-fetch timeout keyed off the bocha budget.
- `canonical_v2_admin.py`: NEW `_budget_receipt_overrun_kind()`
  (None / "wall_time" / "resource"); `_validated_evidence_set` keeps web
  evidence on wall-time-only overruns (logged), strips on resource overruns
  (previous behavior for that case).
- Tests: +14 new (agent 9, admin 5); 1 legacy timeout assertion updated
  (0.675 → 4.0).
- Live evidence: waseda query first-ever passes (2/3), 0 internal_error,
  demo 4/4; residual cold-cache outage documented (trace f-xa59Ap).
