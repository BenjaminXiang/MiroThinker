# ADR-022: Assessments use per-turn LLM-selected dimensions

- **Date:** 2026-07-13
- **Status:** Accepted and carried by the active OpenSpec change
- **Related:** `CONTEXT.md` (Assessment frame, Evidence-based assessment, Claim-evidence map);
  ADR-018, ADR-019; OpenSpec `rebuild-canonical-v2-knowledge-platform`; S2C/S8/S9
- **Contract:** carried by the active OpenSpec planning/answer/acceptance requirements before
  assessment scenarios are accepted

## Context and decision

Questions such as “是否成熟”, “市场竞争力怎么样”, and “是不是大牛” need explicit evidence-based
dimensions, but those dimensions legitimately vary with the question and available evidence. Building
a global versioned registry of assessment types, mandatory dimensions, weights, and thresholds before
the product has enough usage evidence would over-design this slice. Storing one canonical score or
label would still present contextual judgment as false objectivity.

For each assessment turn, the LLM may select a small, relevant set of dimensions from the user's
question and retrieved evidence. Explicit user criteria take precedence. The selected dimensions form
one structured `AssessmentFrame`; each dimension records its name, brief rationale, supporting
evidence IDs, conclusion or `insufficient_evidence`, and uncertainty. The answer states the dimensions
when they materially affect the judgment and produces a conditional overall synthesis.

There is no required global Assessment Policy registry, fixed dimension catalog, universal weighting,
or numeric score in this change. The existing plan/schema/model/prompt trace is sufficient to explain
which dimensions were chosen. The LLM cannot treat model memory as evidence, convert missing evidence
into poor performance, or store the resulting judgment as canonical fact.

## Consequences

- S8/S9 need only a compact structured assessment frame and per-dimension evidence mapping, not a new
  policy service or registry.
- Missing or conflicting evidence is disclosed and may produce an ADR-019 continuation option for
  targeted follow-up rather than a fabricated categorical verdict.
- ADR-018 cases normally validate user-criterion preservation, evidence support, missing/conflict
  handling, disclosure, and forbidden unsupported labels; they do not require one universal dimension
  list unless the scenario itself names required dimensions.
- Prompt/model changes may change reasonable dimensions. Acceptance focuses on grounded usefulness
  rather than exact dimension identity when the user did not prescribe a rubric.
- Repeated stable dimensions may be promoted into a lightweight shared template later if real usage
  demonstrates the need; this is not required for V2.
- This ADR records the simplified decision but does not itself modify OpenSpec.

## Alternatives rejected

- **Versioned Assessment Policy registry now:** reproducible but premature; it adds catalog, policy,
  calibration, and version-management work before stable assessment types are known.
- **Canonical maturity/competitiveness/expert score:** filterable but falsely objectifies contextual,
  time-bound judgment and obscures missing evidence.
