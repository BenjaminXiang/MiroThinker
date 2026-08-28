# Verification Contract: fix-web-lane-timeout-and-utf8-truncation

Written BEFORE production edits (TDD boundary). Slice ID:
`fix-web-lane-timeout-and-utf8-truncation`.

## RED conditions (must fail on current code)

1. **UTF-8 truncation**: for a CJK-rich snapshot JSON, byte-slicing at an
   offset that splits a multi-byte character makes
   `WebSnapshotPayload(...).model_dump(mode="json")` raise
   `UnicodeDecodeError`. (Reproduced standalone 2026-08-28; the unit test
   locks the OLD behavior as a documented regression and the NEW helper as
   the fix.)
2. **Timeout starvation**: `_DualWebLaneAdapter(timeout_ms=1500)` assigns
   every provider a 0.675 s HTTP timeout — below Serper's measured
   1.7–2.8 s latency (live measurement `/tmp/bocha-latency-log.json`,
   Serper 1732/2017/2780 ms ×3).
3. **Degradation granularity**: a supplemental budget receipt with
   elapsed_ms > wall cap but provider_calls/retries/cost/attempt_count all
   within caps still strips ALL web evidence today.

## GREEN conditions (unit level, this slice)

1. `_utf8_truncated(text, cap)` output for EVERY cap in a boundary-dense
   range: decodes as UTF-8 without error, length ≤ cap, equals full encoding
   when cap ≥ encoded length; wrapped in `WebSnapshotPayload` it survives
   `model_dump(mode="json")` at every tested cap.
2. Adapter (main, timeout_ms=1500): bocha attempt timeout 2.0 s, serper 4.0 s.
   Adapter (probe, timeout_ms=3000): bocha 2.7 s, serper 4.0 s. Outer wait per
   provider = attempt + 0.5 s.
3. Time-only receipt overrun → evidence returned unchanged (warning logged).
   provider_calls overrun → web evidence stripped (existing behavior).

## GREEN conditions (live replay, gates acceptance)

1. Waseda query ×3 on 18188 after restart: 0 × internal_error, 0 × outage
   wording, keypoint (早稻田|许晋诚|帕西尼) hit in ≥2/3 runs.
2. The 4 live demo questions (CN117873146A / 优必选专利 / 华力创 / PCB打板)
   still answer with keypoints hit.
3. Pre-existing canonical-v2 serving test suites all green (agent app) +
   admin-console degradation-related tests green.

## Evidence archive

- `/tmp/bocha-latency-log.json` — vendor-blame ruling experiment (16/16).
- `/tmp/demo6-rerun.json`, `/tmp/testset-results.json` — failing baseline.
- `.agents/runs/fix-web-lane-timeout-and-utf8-truncation/verification.md` —
  final replay results (to be written in step 7).
