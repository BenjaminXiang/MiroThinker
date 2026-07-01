# Design: fix-chat-retrieval-recall-gaps

> Eval-first (CLAUDE.md §14.7). RED = baseline 58% (`eval_recall_chat.py`, measured this round,
> synthesis off, Serper 403 → web dead); GREEN = recall ≥ 58% (current-HEAD) with no passing
> case regressed. Diagnosis: `.agents/runs/retrieval-generation-alignment/diagnosis-baseline.md`.

## FM1b — recall candidate window (DELIVERED as hybrid RRF; candidate_limit reverted)

**Root cause (verified):** `candidate_limit=30` cuts deep candidates, but raising it (30→64) was
eval-NEUTRAL and reverted — the reranker still does not reliably promote broad-profile entities
(普渡 rerank-rank-10 over the full pool). The delivered lever is **hybrid RRF**
(`_hybrid_rrf_select`, `retrieval.py:242`): lexical coverage fuses vector-rerank + keyword ranks
so deep-but-lexically-relevant entities enter the window via a second signal.

**Web-search augmentation** was a second recall lever (commit `1fb6449`), but it is OUT of this
change: Serper now returns `403 Unauthorized`, so web contributes 0 to the measured 58%. Web is
split to `add-web-augment` (its own contract + the Serper fix). The deeper profile-quality
layer (broad summaries) is also out of scope (mitigated via RRF, not redone).

## FM3 — cross-filter professor routing

**Root cause:** `_classify_query_by_rules` returns `None` for attribute-AND-attribute queries
("毕业于X，且...专注Y的企业家"), and the LLM classifier either times out or returns None
→ endpoint falls to `unknown` refuse. No recall attempted.

**Fix (DELIVERED, data-blocked):** a rule/classifier target recognizing the cross-filter
professor pattern (school/origin + field/topic → type B, domain professor) reaches professor
Milvus recall. Acceptance = routing-reachable; #19 recall is bound by ingest (许晋诚/陈功 absent).

## Verification surface (eval-first)
| Surface | What it proves | RED/oracle |
|---|---|---|
| `eval_recall_chat.py` (end-to-end /api/chat, synthesis off) | required-entity recall | baseline 58% (measured) |
| `eval_recall.py` (forced-domain) | isolates raw recall per domain | per-domain hit |
| `tests/scripts` + existing chat tests | no routing regression | green |

Deterministic-ish (retrieval + rules); the LLM-classifier branch is eval-first (§14.7).

## Risk
- FM3 rule may over-trigger (route non-cross-filter to professor). Mitigation: tight pattern +
  eval (precision on other cases unchanged).
- FM1a (data) is NOT addressed — recall ceiling stays bounded for #4/#13 until ingest.
- Web-augment (Serper 403) is NOT addressed here — split to `add-web-augment`.

## Out of scope
FM1a ingest; web-search augmentation (Serper); generation/streaming/AnswerGenerator;
embedding/profile rework; A–G enum; `_VALID_DOMAINS`; `_is_indexable_paper`; evidence shape.
