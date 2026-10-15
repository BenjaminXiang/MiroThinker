# Verification — alias passthrough and local foothold (in progress)

Layered evidence. T7 (scratch E2E) and T8 (reseal + cutover) are still open;
this file records what is proven so far.

## ① New tests written this slice (9, all green)

`apps/miroflow-agent/tests/canonical_v2/test_alias_foothold.py` — fixture
source: round-47 live turns (verbatim asks) + the read side's own
`_entity_name_forms` / `_entity_link_entry_indexes` (production language, no
hand-built vocabulary).

| cluster | locks |
|---|---|
| form coverage | both failing asks contain a generated form (国先中心 / 国际先进技术应用推进中心 via city-prefix strip) |
| negative controls ×4 | concept/general asks never link (世界上最美丽的女人是谁 / JEPA有哪些变体 / 介绍一下 / 深圳有哪些做机器人的公司) |
| foothold decision | without linker → False (pre-fix decision); with linker → True for both asks |
| kill switch | `CANONICAL_V2_ALIAS_FOOTHOLD=0` → False; lexical positives untouched |
| determinism | repeated calls stable |

## ② Pre-existing regression suites (green, one proven pre-existing red)

| suite | result |
|---|---|
| `test_llm_query_rewrite.py` (37) | 36 passed; `test_rewriter_timeout_falls_back_to_deterministic_view` tripped under full-suite load and **passes in isolation** (timing-sensitive, rerun) |
| `test_followup_domain_carryover.py` | passed |
| `test_serving_pack_loader.py` + `test_manual_recall_points.py` + `test_fast_boot.py` | 51 passed; `test_release_bound_vector_validator_exempts_manual_traces` fails on the baseline too（改动暂存后复跑同样失败 → 预存/环境性，Milvus mvccTs warning class，属既有红） |
| `s12a/test_complete_candidate_runner.py` | 7 passed |
| `test_alias_foothold.py` | 9 passed |

## ③ Replay / fault-injection (RAG/chat-level claim)

Not yet run for this slice — T7 pending: scratch boot + the 4-form
acceptance matrix + `replay_fix_round1.py` 7/7 + recall-gate `--diff`. The
in-suite baseline assertion (①) is the current RED-class evidence; live E2E
follows before any deploy.

## Changed files

- `knowledge_serving_isolated.py` — foothold way (d) + kill switch +
  `_proposal_provider` / `load_recorded_serving_inputs` threading
- `serving_pack_loader.py` — `create_local_name_linker` (lazy, memoized)
- `managed_config.py` — `serving.alias_foothold` row
- `s12a/complete_candidate_runner.py` — `_compose_local_name_linker` +
  `_serve` wiring + serving-input wrapper kwarg
- tests: new `test_alias_foothold.py`; fakes updated in three suites +
  `s12a/test_complete_candidate_runner.py`
