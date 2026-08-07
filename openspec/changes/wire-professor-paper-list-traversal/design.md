# Design: wire-professor-paper-list-traversal

## Context

This narrow change reused an existing verified professor-paper fetch/render path when a single-turn
professor query expressed paper-list intent. It repaired local candidate delivery but did not define
complete predicates, stable pagination, canonical evidence composition, or generated-answer
grounding; those are owned by `close-retrieval-generation-contract`.

## Local design

- Detect professor-anchored paper-list intent with a pure helper.
- Reuse existing verified-link fetch/render helpers rather than create another traversal.
- Wire both A-professor entry sites and retain profile behavior when list intent is absent or no
  verified paper is available.
- Add reported and sibling intent/route regressions without schema, data, or index changes.

## Acceptance boundary

Local `A_prof_papers` payload delivery is necessary but not sufficient. Promotion requires umbrella
Slice A's fixed ID oracle, Slice B's cross-domain evidence/citation contract, and Slice C1's full
verified-set predicates, materialized pagination, topic port, paper-aware synthesis, semantics,
regression, and latency gates. Historical response-wide token arithmetic is not acceptance.

## Rollback and archive

The two call-site rewires/helper can be reverted without changing data. Once linked umbrella gates
pass, accept only as superseded historical evidence and archive with
`openspec archive wire-professor-paper-list-traversal --skip-specs`, recording
`superseded_by=close-retrieval-generation-contract`; do not migrate its overlapping delta.
