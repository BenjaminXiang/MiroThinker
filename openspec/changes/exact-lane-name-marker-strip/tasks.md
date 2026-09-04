# Tasks

- [x] 1. Verification contract before production edits
- [x] 2. RED: exact matcher returns False for a query_text carrying the
      planner's `[lane=exact]` marker even when it equals the display name
- [x] 3. Implement `_exact_query_phrase` marker strip; use in equality and
      containment checks
- [x] 4. GREEN + neighbors (`test_exact_title_containment.py` all pass;
      exact/lexical sweep 84 pass, 1 pre-existing failure verified by
      stash control)
- [x] 5. E2E: restart 18188; golden set rerun — exact-lane hits 3/24→16/24;
      named-entity in-pack 16/19→18/19; ByteDance/Future Mobility flip to
      correctly-anchored PASS; 字节跳动 residual owned by G2b (alias data)
- [x] 6. Docs: log entry + index; acceptance evidence
      (`.agents/runs/exact-lane-name-marker-strip/verification.md`)
