# Design: fix-chat-retrieval-recall-gaps

> Eval-first (CLAUDE.md §14.7). RED = baseline 53% (`eval_recall_chat.py`); GREEN = target
> recall per acceptance. Diagnosis: `.agents/runs/retrieval-generation-alignment/diagnosis-baseline.md`.

## FM1b — recall candidate window

**Root cause (verified):** `_search_collection` passes `limit=candidate_limit` (default 30) to
Milvus; relevant big-name companies rank beyond 30 in raw ANN (普渡=32, 深南电路=50). The
reranker (Qwen3-Reranker, verified HTTP 200, ranks 普渡 #2 on short docs) only gets the top-30,
so deep candidates are never rescued.

**Fix:** raise the default `candidate_limit` (e.g. 30 → 64) so the reranker window includes
rank-32..50 candidates. Risk: larger rerank batch (latency). Mitigation: reranker already
handles 200 in tests; cap at a sane bound; eval-gated (keep only if recall rises without
precision loss). The deeper profile-quality limit (broad summaries) is out of scope.

## FM3 — cross-filter professor routing

**Root cause:** `_classify_query_by_rules` returns `None` for attribute-AND-attribute queries
("毕业于X，且...专注Y的企业家"), and the LLM classifier either times out (2.5s) or returns None
→ endpoint falls to `unknown` refuse (chat.py ~4556). No recall attempted.

**Fix:** add a rule (or classifier target) recognizing the cross-filter professor pattern
(school/origin + field/topic → type B, domain professor) so it reaches professor Milvus recall.
Keep the existing rule-first / LLM-fallback structure.

## Verification surface (eval-first)
| Surface | What it proves | RED/oracle |
|---|---|---|
| `eval_recall_chat.py` (end-to-end /api/chat, synthesis off) | required-entity recall | baseline 53% |
| `eval_recall.py` (forced-domain) | isolates raw recall per domain | per-domain hit |
| `tests/scripts` + existing chat tests | no routing regression | green |

Deterministic-ish (retrieval + rules); the LLM-classifier branch is eval-first (§14.7).

## Risk
- Larger candidate_limit → rerank latency. Bounded + eval-gated.
- FM3 rule may over-trigger (route non-cross-filter to professor). Mitigation: tight pattern +
  eval (precision on other cases unchanged).
- FM1a (data) is NOT addressed — recall ceiling stays bounded for #4/#13 until ingest.

## Out of scope
FM1a ingest; generation/streaming/AnswerGenerator; embedding/profile rework; A–G enum;
`_VALID_DOMAINS`; `_is_indexable_paper`; evidence shape.
