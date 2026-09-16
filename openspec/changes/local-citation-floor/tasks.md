# Tasks

- [x] 1. Verification contract written before production edits
      (`.agents/runs/local-citation-floor/verification-contract.md`)
- [x] 2. RED: selector unit test — named-entity query, local item without
      claim_binding ⇒ `select()` returns ≥1 claim bound to that local item
      (`apps/miroflow-agent/tests/canonical_v2/test_local_citation_floor.py`)
- [x] 3. RED: mapping unit test — handle-bound local citation without an
      official URL ⇒ public card emitted with `url=None`
      (`apps/admin-console/tests/test_canonical_v2_local_citation_cards.py`)
- [x] 4. Implement selector floor (one floor claim per exact-named object,
      inside `local_claim_limit`)
- [x] 5. Implement mapping floor (url-less local card, handle-deduped,
      before web cards; card id = handle id)
- [x] 6. GREEN: both unit tests pass; focused neighbors pass
      (adapter 132/132; serving suites 15/15; closure-suite 3 failures
      pre-existing, verified by stash control)
- [x] 7. E2E: restart 18188 serving on the fixed code; rerun the golden-set
      attribution script; record hit-rate deltas in the log
      (点名 in-pack 12/19→16/19; evidence in verification.md §③)
- [x] 8. Docs: log entry + index status update; acceptance evidence linked
