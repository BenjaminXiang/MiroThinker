# Verification Contract: fix-web-lane-read-outer-wait

Written BEFORE production edits. Slice: `fix-web-lane-read-outer-wait`.

## RED condition (current code)

The read orchestrator computes the web lane's outer wait as
`web_policy.timeout_ms / 1000` with NO floor: a policy with timeout_ms=1500
kills a web lane that legitimately needs >1.5 s (verified live: G7 turns
show evidence trace `web status="unavailable", candidates=0` while the
serving-layer trace records `in=72 retained=72`, zero provider errors).

## GREEN conditions

1. Unit: `_web_lane_outer_wait_seconds(WebSearchPolicy(timeout_ms=1500))`
   == 20.0 (floor applies); `timeout_ms=30000` → 30.0 (policy wins above
   floor); disabled mode → None.
2. Integration: a fake web adapter that sleeps 2 s under a 1 500 ms policy
   still lands its items in the evidence set with trace status "succeeded"
   (no "unavailable").
3. Live replay on 18188: G7 ×3 (优必选 present in ≥2/3), waseda ×3
   (keypoints ≥2/3, no internal_error), full replay gate G-green or the
   only remaining failure documented as a separate family (G3).
4. Existing suites: no new failures.
