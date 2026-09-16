# Verification evidence: local-citation-floor (Stage0-G1)

## ① New tests this slice (6, all GREEN)

Agent side — `apps/miroflow-agent/tests/canonical_v2/test_local_citation_floor.py`
(fixtures constructed, mirroring the 飞象 transcript scenario):
- `test_named_query_keeps_local_claim_without_binding` — RED before fix
  (reproduces 飞象: named query + binding-less local item → zero local
  claims), GREEN after. Locks the selector floor.
- `test_floor_does_not_duplicate_when_binding_exists` — control: no
  duplicate floor claim when the main loop already bound the object.
- `test_floor_silent_for_unnamed_topic_query` — control: topic queries get
  no synthesized claims.

Admin side — `apps/admin-console/tests/test_canonical_v2_local_citation_cards.py`
(constructed scenario):
- `test_local_citation_without_official_url_still_emits_card` — RED before
  fix, GREEN after. Locks the mapping floor (url=None card).
- `test_local_citation_card_is_deduped_per_handle` — one card per handle.
- `test_local_citation_with_official_url_keeps_url_card` — official-URL path
  unchanged.

## ② Pre-existing regression suites

- `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py` —
  **132/132 PASS**. One assertion updated (None-url tolerant /browse guard);
  one card-id convention aligned (archive card id = handle id).
- Agent serving suites (`test_ambiguity_gate_serving.py`,
  `test_ambiguity_switch_execution.py`, floor tests) — 15/15 PASS.
- `test_knowledge_answer_implementation_closure.py` — 45 passed, 3 failed;
  **all 3 pre-existing** (verified by stash-revert control run: same 3 fail
  without this change).

## ③ E2E replay evidence (RAG-level claim)

Serving 18188 restarted on fixed code (pack candidate-v2-20260819-r1);
first-query warmup 565s (lookup-document load, cold-instance cost — bisect
proved clean code hangs identically on first query, exonerating this change);
golden set rerun (same seed, same 34 queries):

| metric | before | after |
|---|---|---|
| 点名 in-pack（19 查询） | 12/19 (63%) | **16/19 (84%)** |
| — company | 2/7 | 4/7 |
| — paper | 2/4 | 4/4 |
| — professor / patent | 5/5, 3/3 | 5/5, 3/3 (held) |
| 语义（属性本地引用） | 2/4 | 3/4 |
| 关系 | 3/6 | 3/6 (G3 scope, unchanged) |
| 池外论文（诚实口径） | 0/5 | 0/5 (target not in pack — honest) |

Canonical case 飞象: answer now built from the local profile ("聚焦人工智能…
智能家电品制造商…暖风机、电风扇") with a local company citation card.

Residual 3 company LOCAL_DROPPED (ByteDance Ltd. / 字节跳动 / Future
Mobility): turn trace shows answer_subject = 深圳市安络科技有限公司 —
**subject resolution anchored the wrong entity** for English-named queries.
Owned by G2 (alias closure + exact-name entity resolution), not a G1
regression; recorded as G2 evidence.

## Runbook notes (ops)

- Cold-instance first chat turn ≈ 9-10 min (full lookup parse + integrity
  compare, then cached). Warm turns 4-60s.
- Restarting 18188 too quickly after SIGTERM can crash the new instance
  ("Open local milvus failed" — Milvus Lite file lock race with the old
  process's graceful shutdown). Wait for the port to be free.
- Launcher: `.agents/runs/full-column-serving-pack-rebuild/serve-v2-18200.sh
  18188` with `apps/miroflow-agent/.env` sourced (web-lane keys).
