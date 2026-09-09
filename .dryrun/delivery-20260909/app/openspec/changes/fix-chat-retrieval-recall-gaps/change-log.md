# Change Log — fix-chat-retrieval-recall-gaps

## 2026-08-02 · Round 2: collection-reference + geography + intra-query antecedent

### Added

- **Enumeration vector-canonical survival** (`knowledge_serving_isolated.py::_serving_reranker`):
  list-style questions treat vector-lane canonical candidates as strong local so they stay
  balanced with Web gap candidates inside the window. Previously every vector candidate was
  filed under `other`, so when the Web lane filled the window (`candidate_limit`), no canonical
  handle survived and the next turn's collection reference ("上述企业…") had nothing to bind.
  Entity questions keep the conservative order (Web gap ahead of vector neighbor).

- **Geography slot predicate family** (`knowledge_read.py::_constraint_failures`): a geography
  slot is now satisfiable by `geography`, `headquarters_city`, `registered_address`,
  `office_city`, `branch_city` claims, and by the city inside a company's own registered name.
  Previously only a literal `geography` claim satisfied the slot, but the serving Web lane
  emits `headquarters_city` for 总部 questions and local candidates never carried a geography
  claim, so every city-filtered follow-up collapsed to the supplemental lane.

- **Intra-query set antecedent wins** (`canonical_v2_chat.py`): `has_internal_set_antecedent`
  now also gates `_planning_displayed_ids`, `_history_displayed_ids`, and the archived-history
  fallback in `_answer_locked`. A query that names its own set ("…厂商，他们…") is
  self-resolving and must not bind the previous topic's displayed set (Q14 vector lane was
  filtered to zero and answered "无法回答").

### Regression tests

- `test_serving_reranker_keeps_enumeration_vector_canonical_in_window`
- `test_geography_slot_accepts_relation_and_registered_name_evidence`
- `test_intra_query_set_antecedent_never_binds_archived_result_set`

### Verification

- serving isolated 116 passed; read atomic green contract 3 geography tests passed;
  referent history 19 passed; admin chat adapter 62/63 passed (1 pre-existing S11A seam fail).
- End-to-end on 18199: hotel T1→T2 (深圳 subset, 11 companies, 博歌 correctly excluded) →T3
  (普渡 FlashBot Arm); Q14 answered 13+ 深圳具身智能/灵巧手厂商 with data routes.
- Full workbook replay (single session, all 25 turns): every turn has a substantive answer;
  no transport/contract failures. Q7 now answers 许晋诚 (matches reference answer).
