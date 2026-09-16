# Tasks: fix-web-lane-timeout-and-utf8-truncation

- [x] 1. Verification contract written (`.agents/runs/
       fix-web-lane-timeout-and-utf8-truncation/verification-contract.md`)
       BEFORE production edits.
- [x] 2. `_utf8_truncated()` helper + 4 snapshot call-site replacements;
       unit test: every boundary offset around multi-byte chars yields
       decodable bytes and survives `WebSnapshotPayload.model_dump(mode="json")`.
- [x] 3. Per-provider attempt timeouts in `_DualWebLaneAdapter` + per-provider
       outer wait; unit test: main lane (1500 ms) → bocha 2.0 s / serper 4.0 s,
       probe lane (3000 ms) → bocha 2.7 s / serper 4.0 s.
- [x] 4. Graded budget degradation in `_validated_evidence_set`; unit tests:
       time-only overrun retains web evidence, provider_calls overrun strips.
- [x] 5. Regression: existing canonical-v2 serving suites green. (No new
       failures; 3 agent-side + 37 admin-side failures proven pre-existing at
       HEAD via git-stash roundtrip.)
- [x] 6. Live replay on 18188: waseda query ×3 (0 internal_error, 0 crash,
       keypoints hit 2/3 — first-ever passes with the expected answer
       「帕西尼创始人许晋诚」; 1 cold-cache outage residual documented,
       trace f-xa59Ap, read-layer merge path, outside this slice's three
       chains) + 4 demo questions all pass.
- [x] 7. Human docs: plan doc + log entry + `docs/plans/index.md` update;
       acceptance evidence archived (`verification.md`).
