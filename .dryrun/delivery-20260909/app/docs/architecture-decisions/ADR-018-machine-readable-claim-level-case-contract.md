# ADR-018: Acceptance uses machine-readable claim-level case contracts

- **Date:** 2026-07-13
- **Status:** Accepted and carried by the active OpenSpec change
- **Related:** `CONTEXT.md` (Acceptance case contract, Stage oracle); ADR-013; OpenSpec
  `rebuild-canonical-v2-knowledge-platform`; Canonical V2 S2C, S8, S9, and S12
- **Contract:** carried by the active OpenSpec acceptance/corpus requirements before the frozen
  corpus is used to accept query or answer slices

## Context and decision

The workbook contains valuable user scenarios but also dynamic facts, internally inconsistent prose,
known-bad answers, and requirements that cannot be judged by keyword overlap or one aggregate LLM
score. A fluent response can mention a required name while assigning the wrong identity, role,
product capability, time, or evidence; conversely, a correct paraphrase should not fail because it
does not reproduce the reference wording.

Canonical V2 acceptance will use a versioned machine-readable claim-level case contract. Each
applicable turn records:

- `required_claims` and `forbidden_claims`, including subject, predicate, object/value constraints,
  materiality, and evidence obligation;
- `required_entities` and `forbidden_entities`, matched through reviewed identity/alias rules rather
  than raw substring presence;
- `allowed_variants` for semantically equivalent values, phrasings, units, or qualified outcomes;
- content-addressed `source_snapshots`, source nature, and the evidence scope available to the oracle;
- `as_of` and temporal tolerance/policy where current facts are evaluated;
- the ADR-013 enumeration policy, scope/universe, required members, and expected coverage accounting;
- stage oracles for query understanding/protected slots, candidate recall, fusion/sufficiency,
  claim-evidence mapping, rendered answer behavior, and session transition where applicable.

Reference-answer prose remains useful to reviewers and test authors but is explanatory and
non-normative. It is not a factual database, exact-text target, or substitute for the structured
contract. A known-bad response may be retained only as negative evidence or historical context; its
claims do not become accepted truth.

Hard per-case requirements and prohibitions cannot be averaged away by aggregate corpus scores. An
LLM judge may compare semantic variants or evidence entailment only against the structured contract
and supplied snapshots, and its agreement with human review must be calibrated. It cannot establish
external truth from model memory or from reference prose alone.

## Consequences

- The accepted historical S2 corpus/manifest and threshold artifacts need a reviewed S2C schema
  migration before
  serving as the S8/S9/S12 oracle; free-text `reference_key_points` may remain display metadata but
  cannot own pass/fail semantics.
- Case IDs, contract versions, source snapshot hashes, and review/approval state must be immutable and
  traceable in benchmark results.
- Required/forbidden identity, claim support, false exhaustiveness, protected-slot loss, and session
  transition failures are case-level failures even when aggregate quality remains above threshold.
- Stage results distinguish knowledge coverage, reach, ranking/fusion, sufficiency, generation, and
  context failures without asserting private implementation call order.
- This ADR records the oracle decision but does not itself modify OpenSpec, reclassify existing S2
  acceptance, or rewrite the corpus.

## Alternatives rejected

- **Reference prose/key points plus an improved LLM Judge:** still permits identity, evidence, time,
  and forbidden-claim errors to hide behind a fluent aggregate score.
- **Exact or approximate workbook-text gold:** overfits wording, imports known factual conflicts, and
  fails valid paraphrases or updated evidence.
