# Design: fix-professor-ambiguity-intro-rule

## Context

This narrow change prevented the generic ambiguous-introduction rule from consuming professor
queries that already contain an academic title. It repaired the local type/domain branch but did not
prove normalized entity extraction, endpoint choice, resolved ID, citation, or answer semantics;
those are owned by `close-retrieval-generation-contract`.

## Local design

- Add an academic-title guard to the ambiguous-intro rule.
- Let title-bearing queries fall through to the existing professor-name extraction path.
- Preserve title-less ambiguous queries as Type G.
- Cover Q004/Q017 plus the title-less sibling negative without adding a new query class or schema.

## Acceptance boundary

Type A alone is insufficient. Promotion requires umbrella Slice A's full classifier row fields,
Slice B's grounded response contract, and Slice C0's exact normalized name, professor domain/
endpoint, resolved professor ID, citation, semantics, regression, and latency gates.

## Rollback and archive

The guard is independently reversible. Once the linked umbrella gates pass, accept only as
superseded historical evidence and archive with
`openspec archive fix-professor-ambiguity-intro-rule --skip-specs`, recording
`superseded_by=close-retrieval-generation-contract`; do not migrate its overlapping delta.
