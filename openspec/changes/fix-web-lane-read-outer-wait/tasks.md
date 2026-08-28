# Tasks: fix-web-lane-read-outer-wait

- [x] 1. Verification contract written before edits
       (`.agents/runs/fix-web-lane-read-outer-wait/verification-contract.md`).
- [x] 2. `_web_lane_outer_wait_seconds()` + `_WEB_LANE_OUTER_WAIT_FLOOR_SECONDS`
       (20 s) in `knowledge_read.py`; execute() uses it for the web future
       (was: raw `policy.timeout_ms/1000`).
- [x] 3. Unit tests: floor math (1 500 ms → 20.0; 30 000 ms → 30.0;
       disabled → None) + integration: a 2 s web lane under a 1 500 ms
       policy lands its items with a succeeded trace.
- [x] 4. Regression: knowledge_read/serving/supplemental suites green
       (258 pass, 1 pre-existing prose-renderer fail).
- [x] 5. Live replay on 18188: G7 ×3 PASS (web lane succeeded/48, 优必选
       present, 37–40 s) + waseda ×3 PASS (12.5–13.1 s, keypoints hit, zero
       outage) — `/tmp/live-replay-outerwait.json`.
- [x] 6. Full replay gate: 18/19 — G7 GREEN; only G3 person-pronoun fails
       (separate pre-existing family: personal pronoun bound to an
       organization anchor without a type check; clarification rule at
       canonical_v2_chat.py:778 exists but does not fire; needs its own
       planner-side slice).
