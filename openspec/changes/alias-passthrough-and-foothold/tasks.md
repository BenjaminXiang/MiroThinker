# Tasks: alias passthrough and local foothold

- [ ] T1 RED artifacts: round-47 failing asks reproduced (scratch or live read-only)
  + fixtures for the bracket-reorder name form
  → `.agents/runs/alias-passthrough-and-foothold/red-case.md`
- [ ] T2 verification contract written before production edits
  → `.agents/runs/alias-passthrough-and-foothold/verification-contract.md`
- [ ] T3 design readout — locate reuse points and write them down: entity
  name/alias index accessor in the serving layer, the web-only routing branch,
  the web-0 answer path, where the foothold result feeds lane selection
  → `openspec/changes/alias-passthrough-and-foothold/design.md`
- [ ] T4 implementation: foothold extension + alias→canonical resolution +
  local fallback + kill switch `CANONICAL_V2_ALIAS_FOOTHOLD`
- [ ] T5 unit tests: name-form matrix (bracket reorder / short / full), negative
  controls (concept questions keep web-only), kill switch, determinism
- [ ] T6 targeted regression: `tests/canonical_v2/test_knowledge_serving_isolated.py`,
  `test_followup_domain_carryover.py`
- [ ] T7 scratch E2E (port 1829x): 4-form matrix + web-0 fallback (AC1–AC5);
  `replay_fix_round1.py` 7/7; recall-gate `--diff`; route A/B on the round-41 set
- [ ] T8 reseal (s12g manifest-only path) + cutover dev line (18188) + field line
  (100.64.0.96) with rollback assets kept
- [ ] T9 docs: human log round + index line + `verification.md` (layered evidence)
