# Tasks: fix-professor-ambiguity-intro-rule

## 1. Historical local slice

- [x] 1.1 Reproduce Q004/Q017 falling into Type G and identify the academic-title guard.
- [x] 1.2 Implement the guard while retaining title-less ambiguous Type G behavior.
- [x] 1.3 Add reported and sibling deterministic regressions and retain implementation evidence in
  `c0f3db2` and `tests/test_paper_retrievability.py`.
- [x] 1.4 Preserve the historical 100-row type result only as local classifier evidence.

## 2. Candidate re-acceptance and disposition

- [x] 2.1 Correct lifecycle status to Candidate and link the umbrella counter-evidence.
- [ ] 2.2 Pass umbrella Slice A type/domain/normalized-name/endpoint non-leaky gates for Q004/Q017.
- [ ] 2.3 Pass Slice B canonical evidence/citation/outcome/semantic gates.
- [ ] 2.4 Pass Slice C0 exact normalized professor ID, endpoint, citation, semantics, regression, and
  latency gates.
- [ ] 2.5 Record superseded-history acceptance, then archive with `--skip-specs` and
  `superseded_by=close-retrieval-generation-contract`.
