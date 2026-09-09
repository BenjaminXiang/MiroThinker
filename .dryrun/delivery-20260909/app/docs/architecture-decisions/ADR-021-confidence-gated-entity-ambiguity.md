# ADR-021: Entity ambiguity uses confidence-gated answer or clarification

- **Date:** 2026-07-13
- **Status:** Accepted and carried by the active OpenSpec change
- **Related:** `CONTEXT.md` (Confidence-gated ambiguity, Continuation offer, Result set); ADR-017,
  ADR-018, ADR-019; `docs/Agentic-RAG-PRD.md` type G; OpenSpec
  `rebuild-canonical-v2-knowledge-platform`; Canonical V2 S2C/S8/S9
- **Contract:** carried by the active OpenSpec query/answer/session/acceptance requirements
  before the affected slices are implemented

## Context and decision

The PRD expects a highly relevant unambiguous interpretation to be useful immediately while still
letting the user switch entities. Always selecting rank one can silently answer for the wrong
Company or Professor; always requiring clarification adds a turn even when exact identifiers,
institution, geography, aliases, and evidence make one candidate clearly dominant. An LLM's own
confidence is not identity evidence and cannot safely decide this boundary by itself.

Canonical V2 will use a versioned domain-aware ambiguity policy with an evidence floor, selection
confidence threshold, and minimum lead margin. Candidate evidence may include accepted identity/
alias resolution, protected query constraints, strong identifiers, typed affiliation/geography, and
traceable relevance decisions. A candidate cannot clear the gate when a protected constraint
conflicts, and LLM self-confidence alone is insufficient.

The interaction has two modes:

- **Non-blocking ambiguity:** exactly one candidate clears the evidence/threshold/margin policy. The
  system answers that candidate, begins with a short interpretation notice, and, when another viable
  candidate remains, ends with an ADR-019 `ContinuationOffer` for switching to it.
- **Blocking ambiguity:** no candidate or more than one candidate remains within the accepted margin.
  The response is clarification-only and renders up to three evidence-backed candidate choices with
  useful discriminators. It does not generate a primary entity answer before the user selects.

Selecting an alternate candidate binds the next turn to its accepted Canonical ID or ADR-017 Web
entity handle and records the selection in session state. The system retains the original candidate
decision trace and never uses ambiguity resolution to mutate canonical identity.

Numeric thresholds and domain calibration are versioned acceptance policy, not prompt constants or
hardcoded name lists. “No matching candidate” remains distinguishable from “several plausible
candidates.”

## Consequences

- S8 plans/results need structured ambiguity state, candidate evidence, policy version, confidence,
  margin, protected-constraint checks, and selected/blocked outcome.
- S9 needs deterministic interpretation notices, clarification rendering, candidate-bound
  `ContinuationOffer` options, and correct next-turn anchor binding.
- ADR-018 case contracts need exact, near-name, same-name, alias, institution/geography constraint,
  threshold-boundary, no-candidate, alternative-selection, and Web-handle ambiguity scenarios.
- Acceptance separately verifies false auto-selection and unnecessary clarification; one aggregate G
  score cannot hide either failure direction.
- This ADR records the policy decision but does not itself set numeric thresholds or modify OpenSpec.

## Alternatives rejected

- **Always answer rank one:** minimizes interaction cost but silently converts ranking uncertainty into
  an identity claim.
- **Always clarify on multiple candidates:** identity-safe but adds unnecessary turns when one
  candidate is strongly and evidentially dominant.
