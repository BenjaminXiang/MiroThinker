# ADR-015: Canonical V2 uses an internal versioned Technology model

- **Date:** 2026-07-13
- **Status:** Accepted and carried by the active OpenSpec change
- **Related:** `CONTEXT.md` (Technology concept, Technology route, Industry brief); OpenSpec
  `rebuild-canonical-v2-knowledge-platform`; Canonical V2 S6R/S7/S8/S9
- **Contract:** carried by the active OpenSpec change before the affected catalog/index/query/
  answer slices are implemented or accepted as dependencies

## Context and decision

The product must compare technical routes, explain their methods and applicability, and map each
route to representative Companies, products, Papers, and Patents. Free-form tags and Company route
summaries are useful retrieval text but cannot provide stable hierarchy, alias resolution, temporal
meaning, or evidence-backed per-entity route attribution. Making Technology a fifth public domain
would broaden the confirmed four-domain product and confuse reusable reference knowledge with a
business-domain inclusion policy.

Canonical V2 will retain Professor, Company, Paper, and Patent as the four public PRD domains and add
an internal versioned Technology model:

- `TechnologyConcept` provides stable internal taxonomy identities, aliases, definitions, hierarchy,
  source assertions, and temporal/version context;
- `TechnologyRoute` represents an evidence-backed method category and its relationship to relevant
  concepts, conditions, and typed adoption/discussion evidence;
- typed relationships may connect Companies, products, Papers, and Patents to concepts/routes, but
  each relationship must preserve its exact semantics, evidence, state, and time rather than treating
  a topic mention as proven adoption or capability;
- `IndustryBrief` is a release-scoped derived synthesis over accepted local knowledge plus cited
  current-Web evidence, with explicit scope and as-of. It is never written as canonical fact.

Unresolved or newly observed technical language remains an evidence-bearing term/alias candidate
until an offline build accepts its identity or relationship. Online Web/LLM output may support the
current brief or create a gap, but cannot mutate the accepted Technology model directly.

## Consequences

- S6R must extend the historical S6 taxonomy/topic/geography catalog boundary with internal
  Technology identities,
  route semantics, and precise relationship types such as discussion, claimed adoption, and
  demonstrated use; these states must not collapse into one generic tag edge. Product capability
  remains answer-scoped under ADR-016 rather than becoming a canonical relationship in this change.
- S7 may publish internal Technology lookup/semantic projections bound to one accepted release without
  creating a fifth independently included public-domain index.
- S8 retrieval plans can resolve route aliases, preserve scope/as-of, retrieve typed cross-domain
  evidence, and apply the hybrid enumeration policy to representative-vendor questions.
- S9 Industry Brief answers require claim-evidence mapping, source conflict disclosure, coverage
  reporting, and conditional conclusions. Brief text is reproducible derived output, not canonical
  storage input.
- This ADR records the boundary decision but does not itself modify OpenSpec behavior or reopen an
  Accepted slice; the V2 design owner must reconcile the affected S6R/S7/S8/S9 contracts first.

## Alternatives rejected

- **Only tags, summaries, and live-Web synthesis:** fast to implement but cannot provide stable route
  identity, typed per-entity attribution, reproducibility, or systematic coverage evaluation.
- **Fifth public Technology domain:** makes reusable reference knowledge look like another business
  entity population and expands inclusion, publication, API, and acceptance scope unnecessarily.
