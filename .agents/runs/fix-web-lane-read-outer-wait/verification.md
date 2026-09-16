# Verification Evidence: fix-web-lane-read-outer-wait

Contract: `verification-contract.md` (written before edits).

## Unit (GREEN)

- `tests/canonical_v2/test_web_lane_read_outer_wait.py` — 2/2:
  floor math (1 500 ms → 20.0 s, 30 000 ms → 30.0 s, disabled → None);
  integration: web adapter sleeping 2 s under a 1 500 ms policy lands its
  item, trace `succeeded` (RED before the fix: lane killed, trace
  `unavailable`).

## Regression

- knowledge_read universal web contract + serving isolated + supplemental
  person criteria: 258 pass, 1 pre-existing prose-renderer fail (fails at
  HEAD, documented in the previous slice).

## Live replay (18188 restarted with the fix; raw:
`/tmp/live-replay-outerwait.json`)

| Query | x3 result |
|---|---|
| 深圳有哪些做具身智能的公司 (G7) | PASS/PASS/PASS — web lane `succeeded/48` (was `unavailable/0`), 优必选 present, 37–40 s |
| 毕业于早稻田…企业家 (waseda) | PASS/PASS/PASS — 12.5–13.1 s, keypoints hit, zero outage wording |

## Full replay gate: 18/19

G1/G2/G4/G5/G6/G7 all PASS (G7 was 4/6 flaky-to-red before). Remaining:
G3 person-pronoun T2「他有哪些论文」after an organization anchor — answered
with junk papers instead of clarifying. Pre-existing, separate family:
session snapshot is correct (org anchor + referent hint), planner bound the
personal pronoun to the org anchor without a type check; the clarification
rule (canonical_v2_chat.py:778) never fired. Needs a planner-side slice
(pronoun × anchor-type guard), filed as the next gap.

## Final testset E2E (post-fix)

See `docs/plans/2026-08-28-web-lane-timeout-utf8-fix-log.md` R2 entry.
