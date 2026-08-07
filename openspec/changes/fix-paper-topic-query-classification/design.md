# Design: fix-paper-topic-query-classification

## Context

This narrow change repaired deterministic routing for paper-topic queries that contain English
terms and do not end at the paper noun. The broader topic-retrieval, grounding, and answer-quality
contract was not part of the local implementation and is now owned by
`close-retrieval-generation-contract`.

## Local design

- Recognize paper noun plus topic/search intent before the exact-English-title rule.
- Preserve bare English exact titles and professor/company-anchored routes through explicit guards.
- Reuse the existing `B_paper_topic_search` endpoint; add no query type, provider, schema, or data
  mutation.
- Cover the reported mixed-language examples and sibling false-positive routes in deterministic
  regression tests.

## Acceptance boundary

The local route/type/domain result is necessary but not sufficient. Candidate-to-Accepted promotion
requires umbrella Slice A's non-leaky oracle, Slice B's canonical grounding/citation contract, and
Slice D's paper-level Type4 precision, semantic, regression, and latency gates. Historical response-
wide tokens or unblinded “looks relevant” observations cannot replace those gates.

## Rollback and archive

The local guard is reverted independently if its sibling routing matrix regresses. Once linked
umbrella gates pass, this change is accepted only as superseded historical evidence and archived
with `openspec archive fix-paper-topic-query-classification --skip-specs`, recording
`superseded_by=close-retrieval-generation-contract`. Its broad in-flight capability delta must not
be migrated over the umbrella's narrower canonical specs.
