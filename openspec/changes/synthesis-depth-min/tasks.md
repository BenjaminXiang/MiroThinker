# Tasks: synthesis-depth-min (slice ①min)

- [x] T1 diagnosis + RED on the live line: verbatim transcript (719 chars, 0
  citations, 8/8 「EJA」 pages), merge-order read, provider probe table
  (0/8 → 3/16 relevant), the `local_scope_foothold` gate; English full-name query
  11/11 relevant
  → `.agents/runs/synthesis-depth-min/red-case.md`
- [x] T2 OpenSpec change + verification contract before production edits
  → this directory + `.agents/runs/synthesis-depth-min/verification-contract.md`
- [x] T3 design readout (drop points DP1/DP2 with line refs; DP3 recorded as the
  contingency and, after T7's first run, implemented in the same slice;
  marker-set decision recorded) → `design.md`
- [x] T4 implementation: Web-only branch for `max_web_results` +
  `CANONICAL_V2_WEB_WIDE_WINDOW` kill switch + `managed_config` row + the
  rewrite-prompt clause + DP3's per-view head cap (`_merge_web_results_across_views`
  / `_discovery_front_merge` / lane call site) with the shared `_web_list_shaped`
  predicate
- [x] T5 unit tests: window-gate matrix (6), kill switch, prompt clause, merge-cap
  lock (7 passed total); the pre-fix assertion in
  `test_knowledge_serving_isolated.py` flipped to the list-shaped rule
- [x] T6 targeted regression: `test_knowledge_serving_isolated.py` (-k window/
  foothold: 31 passed; -k rewrite/merge/window/web after DP3: 99 passed),
  pack/recall/fast_boot/alias_foothold 60 passed (1 known pre-existing red),
  `test_llm_query_rewrite.py` 33 passed (1 pre-existing race-flake documented:
  the 榜单/名单 concurrent arrival order)
- [ ] T7 scratch E2E: before/after on the reported question, the 片② matrix 6/6,
  replay 7/7, recall gate 0 fail-level, TTFT envelope
- [ ] T8 reseal + dual-line cutover (dev 18188, site 100.64.0.96) with rollback
  assets kept
- [ ] T9 docs: human log round + index line + `verification.md`; push main
