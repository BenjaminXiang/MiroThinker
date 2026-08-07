# Acceptance: fix-paper-topic-query-classification

## Historical local candidate evidence

- [x] The guarded classifier change is present at `c0f3db2`.
- [x] Reported mixed-language topic queries and bare-title/entity-anchor sibling routes have local
  deterministic regression evidence.
- [x] Historical live candidates are labeled anecdotal/non-blind rather than precision evidence.
- [x] Lifecycle is Candidate and controlled by `close-retrieval-generation-contract`.

## Re-acceptance and archive

- [ ] Umbrella Slice A passes frozen type/domain/topic/endpoint and no-query-echo gates.
- [ ] Slice B passes canonical evidence/citation/semantic gates for the linked cases.
- [ ] Slice D passes sealed paper-level Type4 precision, citation, semantic, regression, and latency.
- [ ] Independent review accepts only superseded history; archive uses `--skip-specs` and records
  `superseded_by=close-retrieval-generation-contract`.
