# Tasks: alias passthrough and local foothold

- [x] T1 RED artifacts: round-47 failing asks (verbatim) + in-suite baseline
  assertion (pre-fix decision captured in the green suite)
  → `.agents/runs/alias-passthrough-and-foothold/red-case.md`
- [x] T2 verification contract written before production edits
  → `.agents/runs/alias-passthrough-and-foothold/verification-contract.md`
- [x] T3 design readout — reuse points are the read side's audited lookup view
  (`_create_audited_lookup_view` + `_entity_link_indexes_for_view`); web-only
  branch at `_proposal_provider` lanes; runner seam in `s12a`
  → `openspec/changes/alias-passthrough-and-foothold/design.md`
- [x] T4 implementation: foothold extension (linker way, runs last) + lazy
  pack-name linker (`serving_pack_loader.create_local_name_linker`) + runner
  threading + kill switch `CANONICAL_V2_ALIAS_FOOTHOLD` (+ managed_config row).
  Layers ②/③ subsumed per design.md (decide from T7 evidence).
- [x] T5 unit tests (9, all green): name-form matrix (bracket reorder / short /
  full), negative controls ×4, pre-fix baseline, kill switch, determinism
- [x] T6 targeted regression: `test_llm_query_rewrite.py`,
  `test_followup_domain_carryover.py`, `test_serving_pack_loader.py`,
  `test_manual_recall_points.py`, `test_fast_boot.py`,
  `s12a/test_complete_candidate_runner.py` — all green except
  `test_release_bound_vector_validator_exempts_manual_traces`（还原复跑证明预存：
  暂存本片改动后同样失败，Milvus mvccTs 类环境失败）
- [ ] T7 scratch E2E (port 1829x): 4-form matrix + web-0 fallback (AC1–AC5);
  `replay_fix_round1.py` 7/7; recall-gate `--diff`; route A/B on the round-41 set
- [ ] T8 reseal (s12g manifest-only path) + cutover dev line (18188) + field line
  (100.64.0.96) with rollback assets kept
- [ ] T9 docs: human log round + index line + `verification.md` (layered evidence)
