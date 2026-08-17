# ADR-020: Local safety questions use narrow safety guidance

- **Date:** 2026-07-13
- **Status:** Accepted and carried by the active OpenSpec change
- **Related:** `CONTEXT.md` (Safety guidance); ADR-018, ADR-019; `docs/Agentic-RAG-PRD.md`
  local safety/compliance exception; OpenSpec `rebuild-canonical-v2-knowledge-platform`; S2C/S8/S9
- **Contract:** carried by the active OpenSpec behavior/answer/acceptance requirements before
  the affected corpus and query/answer slices are accepted

## Context and decision

Ordinary requests unrelated to Shenzhen science and technology belong to the F refusal behavior. The
PRD defines a narrow exception for local safety/compliance reminders, while the workbook case about
“黄赌毒” simultaneously contains a safe-advice response and a contradictory “不能回答” key point.
Blanket refusal loses useful harm-prevention value; listing or speculating about particular illegal
venues risks unsupported allegations and can facilitate harmful targeting or evasion.

Canonical V2 will apply an orthogonal `safety_guidance` response policy to recognized local safety or
compliance requests. It may remain F at the broad A-G scope taxonomy, but it is not rendered as the
ordinary out-of-scope refusal and is not treated as an open-ended information-retrieval request.

Safety guidance must be brief, polite, conservative, and limited to lawful risk avoidance. It may
recommend using legitimate regulated services, leaving unsafe situations, seeking emergency help,
or contacting official reporting/support channels. It must not:

- identify, rank, map, or speculate about specific illegal venues or districts;
- repeat unsupported allegations about named businesses, neighborhoods, or broad venue categories;
- provide instructions for finding, accessing, concealing, or evading enforcement around illegal
  activity;
- broaden into a general travel or lifestyle answer unrelated to the safety purpose.

The default route does not run Universal Web. If the user explicitly requests current official
contact or policy information, a separate bounded official-source lookup may run under the safety
policy and every material current claim must use a retained source snapshot. A validated
`ContinuationOffer` may point to official help/reporting information but cannot offer venue discovery.

## Consequences

- S8 needs a deterministic/validated safety-policy outcome distinct from ordinary F refusal and from
  A/B/C/D/E/G information retrieval; it must not accidentally trigger general Web augmentation.
- S9 needs a bounded safety-guidance renderer and conservative deterministic fallback that introduce
  no unsupported location or illegality claims.
- ADR-018 must replace the contradictory workbook prose/key point with a structured case contract:
  required safe guidance, forbidden venue/location allegations and evasion assistance, expected Web
  policy, and allowed official-resource variants.
- Acceptance separately measures ordinary F refusals and the narrow safety-guidance exception so one
  cannot mask regressions in the other.
- This ADR records the policy decision but does not itself modify OpenSpec or rewrite the historical
  S2 corpus; S2C owns the new case-contract coverage.

## Alternatives rejected

- **Blanket refusal:** safe but conflicts with the PRD's narrow exception and with the useful
  harm-prevention intent of the question.
- **Specific risky-place list with warnings:** cannot establish a reliable bounded universe, risks
  defamation or profiling, and may facilitate the very behavior the safety guidance should avoid.
