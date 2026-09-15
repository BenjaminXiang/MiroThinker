# Tasks: web-lane topical floor

- [x] T1 RED reproduction + attribution (channel, tier, verbatim output)
  → `.agents/runs/web-lane-topical-floor/red-case.md`
- [x] T2 verification contract written before production edits
  → `.agents/runs/web-lane-topical-floor/verification-contract.md`
- [x] T3 implementation: `_apply_web_topical_floor` + two call sites (main pass,
  refinement pass), kill switch, gate-drop reporting
- [x] T4 unit tests (15) — reported case, location-only overlap, refinement pass,
  identity exemption (name form, soft subject, pinyin brand domain),
  enumeration sample, fail-open ×2, kill switch, determinism, trace, 5 ms budget
- [x] T5 targeted regression: `tests/canonical_v2/test_knowledge_serving_isolated.py`,
  `test_turn_trace_reporting.py`, `test_enumeration_deep_fetch.py`
- [x] T6 scratch E2E on port 18295 (pack run15, index copy):
  - [x] revision 1 (d0ef568e/b6105337) ran the reported query: the camp page
    survived, which produced the real-snippet diagnosis behind 99e7f479
  - [ ] revision 2 (99e7f479) reported query returns no weight-loss-camp page
  - [ ] probes verbatim: `字节跳动`, `优必选有哪些专利`
  - [ ] enumeration: `深圳有哪些做机器人的公司` (key entities 3/3),
    `深圳有哪些做具身智能的公司`
  - [ ] `replay_fix_round1.py --base-url http://127.0.0.1:18295` 7/7 PASS
  - [ ] web-lane wall time (`lane_timings.web`) not worse than the 4.159 s baseline
- [ ] T7 docs: OpenSpec change, ledger row, human log + index line,
  verification.md (layered evidence)
- [ ] T8 scratch process stopped, scratch dirs left in place for the record
