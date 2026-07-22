# ADR-019: Answers use conditional structured continuation offers

- **Date:** 2026-07-13
- **Status:** Accepted and carried by the active OpenSpec change
- **Related:** `CONTEXT.md` (Continuation offer, Enumeration coverage report, Result set); ADR-013,
  ADR-017, ADR-018; OpenSpec `rebuild-canonical-v2-knowledge-platform`; Canonical V2 S8-S9
- **Contract:** carried by the active OpenSpec query/answer/session requirements before the
  affected slices are implemented

## Context and decision

Complex, broad, or ambiguous requests should not force one oversized answer or leave users to guess
how to continue. The current V2 design already supports progressive disclosure and eligible-relation
followups, but relation availability alone does not cover representative lists, ambiguity, partial
coverage, missing evidence, or budget-limited answers. An always-on “you can ask more” footer would
add noise without preserving an executable next-turn meaning.

Canonical V2 will emit an optional structured `ContinuationOffer` at the end of a response only when
one or more of these reasons applies:

- `broad_scope`;
- `ambiguity`;
- `partial_coverage`;
- `evidence_gap`;
- `budget_exhausted`;
- `eligible_next_hop`.

The offer contains at most three validated options. Each option identifies its user-facing label,
operation, target entity handle or displayed result set, relation/constraint/coverage continuation,
and availability/limitation metadata needed to construct the next typed turn. Options are ordered by
relevance to the user's current request and must not assert facts or relationship availability that
the route/result metadata cannot support.

For non-blocking ambiguity, the answer states the interpretation used and may offer another candidate
or scope. For blocking identity or intent ambiguity, the response is clarification-only: the
`ContinuationOffer` carries the candidate choices instead of appending them to an unsupported primary
answer. A simple complete answer with no valid trigger omits the offer.

## Consequences

- S8 plan/result metadata must expose trigger reasons and validated executable continuations without
  letting the prose model invent unsupported paths.
- S9 `TurnResult` and rendering need a typed optional continuation block; selecting or restating an
  option must resolve against its bound handle/result set/constraint under the normal session rules.
- Broad list offers align with ADR-013 coverage state; Web-only options use ADR-017 handles; evidence-
  gap options cannot imply the missing claim is true.
- ADR-018 case contracts need stage/answer/session expectations for trigger presence/absence, option
  count, binding correctness, unsupported option rate, and selected-option next-turn behavior.
- Acceptance requires zero unsupported factual claims in offers and no more than three rendered
  options; wording quality may vary without changing the structured operation.
- This ADR records the behavior decision but does not itself modify the active OpenSpec requirements.

## Alternatives rejected

- **Always append a generic invitation:** creates repetitive prose with no validated next-turn binding
  and makes presence meaningless as a product signal.
- **Only suggest typed relationship traversals:** safe but omits the most important continuations for
  ambiguity, coverage, evidence, and budget-limited answers.
