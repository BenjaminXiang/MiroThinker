# Tasks: wire-professor-paper-list-traversal

## 1. Historical local slice

- [x] 1.1 Reproduce professor paper-list queries returning a count-only profile.
- [x] 1.2 Implement the pure intent helper and reuse the existing verified-paper fetch/render path.
- [x] 1.3 Wire both A-professor entry sites and add positive/negative sibling regressions.
- [x] 1.4 Preserve the local implementation/run evidence in `c0f3db2` and
  `.agents/runs/paper-retrievability-baseline/type2-prof-papers-fix.md`.
- [x] 1.5 Correct historical paper-token arithmetic to 8/20 -> 15/20 and label it non-accepting.

## 2. Candidate re-acceptance and disposition

- [x] 2.1 Correct lifecycle status to Candidate and link the umbrella counter-evidence.
- [ ] 2.2 Pass umbrella Slice A exact ID/predicate/non-leaky evaluator gates.
- [ ] 2.3 Pass Slice B joined professor+paper evidence, citation, outcome, and semantic gates.
- [ ] 2.4 Pass Slice C1 full verified-set predicate, stable pagination, topic-port, paper-aware
  synthesis, regression, and latency gates.
- [ ] 2.5 Record superseded-history acceptance, then archive with `--skip-specs` and
  `superseded_by=close-retrieval-generation-contract`.
