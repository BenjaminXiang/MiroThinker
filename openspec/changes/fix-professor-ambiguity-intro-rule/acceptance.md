# Acceptance: fix-professor-ambiguity-intro-rule

## Historical local candidate evidence

- [x] The academic-title guard is present at `c0f3db2`.
- [x] Q004/Q017 type routing and title-less ambiguity sibling regression evidence are retained.
- [x] The 100-row type result is labeled local classifier evidence, not entity/answer acceptance.
- [x] Lifecycle is Candidate and controlled by `close-retrieval-generation-contract`.

## Re-acceptance and archive

- [ ] Umbrella Slice A passes type/domain/normalized-name/endpoint non-leaky gates.
- [ ] Slice B passes canonical evidence/citation/outcome/semantic gates.
- [ ] Slice C0 passes exact resolved professor ID, endpoint, citation, semantics, regression, and
  latency for Q004/Q017.
- [ ] Independent review accepts only superseded history; archive uses `--skip-specs` and records
  `superseded_by=close-retrieval-generation-contract`.
