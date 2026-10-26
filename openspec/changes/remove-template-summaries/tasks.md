# Tasks: remove-template-summaries

- [x] 1.1 Remove the padding loop from `pipeline_v2._build_fallback_summary`.
- [x] 1.2 Drop known padding sentences in professor claim rendering
      (`_drop_filler_sentences` before `_collapse_repetition`).
- [x] 1.3 Tests: fallback without padding, facts preserved, filler dropped,
      unrelated text untouched, claim rendering end to end.
- [ ] 1.4 Deploy to the customer site and verify a padded professor's claim.
- [ ] 1.5 Eval gate on the live site.
