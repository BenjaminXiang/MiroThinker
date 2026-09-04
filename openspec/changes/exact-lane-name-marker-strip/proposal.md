# Proposal: exact-lane-name-marker-strip (Stage0-G2a)

> Grounded in `docs/plans/2026-09-03-stage0-hit-rate-baseline.md` G2 and the
> G1 residual evidence (ByteDance Ltd. exact-name query anchored the wrong
> subject). Amends the exact-lane matching behavior.

## Why

The planner stamps every lane query as `f"{pure_topic} [lane={lane}]"`
(`knowledge_read.py` `_lane_queries`). The lexical, vector, and web lanes
strip their own marker before matching (`_lexical_query_phrase`,
`[lane=vector]` at 7252, `[lane=web]` at knowledge_serving_isolated:1522) —
**the exact lane never strips `[lane=exact]`**. Consequently the equality
path in `_matches_exact_request` (`_normalize(request.query_text) in
searchable_terms`) can NEVER match a display name: every query text ends
with " [lane=exact]".

Empirical fallout (golden set, live serving):
- exact lane = 0 for ALL name queries (31/34), including queries that EQUAL
  the pack's canonical name byte-for-byte (深圳市飞象工业科技有限公司);
- only patent numbers hit exact, via the `exact_identifier` protected slot
  (clean slot value, unaffected by the marker);
- G6 long-title containment still worked because substring containment is
  insensitive to a trailing marker — which is why the bug hid behind G6;
- without an exact hit, subject anchoring falls to vector/lexical fusion,
  which misanchors English-named entities (answer_subject = 安络科技 for
  "ByteDance Ltd.").

## What Changes

1. `_matches_exact_request` compares against an `_exact_query_phrase` that
   strips the trailing `[lane=exact]` marker (and surrounding quotes),
   mirroring `_lexical_query_phrase`; used in BOTH the equality check and
   the paper/patent containment check.

## Impact

- Exact-name queries (Chinese or Latin, equal to pack name/alias/title) hit
  the exact lane again; deterministic anchoring returns for named entities;
  the G1 selector floor's `exact_named_objects` set also grows (exact-lane
  hits feed `preferred_objects`).
- Alias queries (字节跳动 → ByteDance Ltd.) remain unmatched until alias
  closure lands as a data work item (G2b, unchanged scope).
- Non-goal: alias data, subject-resolution changes beyond the exact hit,
  G3/G4 data batches.
