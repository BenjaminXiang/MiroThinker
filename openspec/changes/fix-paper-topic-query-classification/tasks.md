# Tasks: fix-paper-topic-query-classification

## 1. Historical local slice

- [x] 1.1 Reproduce the topic-query misroute and identify precedence between the paper-topic and
  exact-English-title rules.
- [x] 1.2 Implement the guarded Type B/paper route while preserving bare-title and entity-anchored
  behavior.
- [x] 1.3 Add reported and sibling deterministic regression coverage and retain the local run notes
  under `.agents/runs/paper-retrievability-baseline/type4-classifier-fix.md`.
- [x] 1.4 Keep the implementation checkpoint in `c0f3db2` and the change strict-valid.

## 2. Candidate re-acceptance and disposition

- [x] 2.1 Correct lifecycle status to Candidate and link the umbrella counter-evidence.
- [ ] 2.2 Pass `close-retrieval-generation-contract` Slice A frozen route/domain/topic/endpoint and
  no-query-echo gates.
- [ ] 2.3 Pass Slice B canonical evidence/citation/semantic gates for the linked topic cases.
- [ ] 2.4 Pass Slice D frozen Type4 paper-level micro-P@5, citation, semantics, regression, and
  latency gates.
- [ ] 2.5 Record superseded-history acceptance, then archive with `--skip-specs` and
  `superseded_by=close-retrieval-generation-contract`.
