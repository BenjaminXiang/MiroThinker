# Proposal: fix-outage-rewrite-surgical

> P0-B of the P0–P2 campaign. Human docs:
> `docs/plans/2026-08-28-testset-first-principles-review.md`.

## Why

Test-set 问题14/G12 (「…具身智能、灵巧手厂商…数据路线」) answered with a
79-char outage message instead of its substantive local enumeration. Live
trace: all 4 web-view searches timed out in-service (providers measure
204–486 ms standalone — a transient stall), the LLM's grounded answer (48
local + 3 supplemental candidates) contained a negative fragment, and
`_rewrite_lane_outage_answer_text` REPLACED the whole answer with the
outage wording. Same misfire as the waseda residual: the rewrite's purpose
is to prevent short world-negative claims over an outage, but it swallows
substantive enumerations whole.

## What Changes

- `canonical_v2_chat.py`: `_rewrite_lane_outage_answer_text` gains the
  same length philosophy as `_rewrite_refusal_answer_text`
  (`_REFUSAL_ANSWER_MAX_CHARS`): only a SHORT answer (≤ 200 chars) that is
  essentially the negative claim is rewritten; longer answers keep their
  grounded content even if they contain a negative fragment.

## Impact

- One guard + tests. Web-outage honesty is preserved for short refusals;
  substantive local answers survive transient web stalls.
- Non-goal: the in-service search-timeout forensics (why all 4 views timed
  out while providers are fast) — that rides the P2-A caching slice.
