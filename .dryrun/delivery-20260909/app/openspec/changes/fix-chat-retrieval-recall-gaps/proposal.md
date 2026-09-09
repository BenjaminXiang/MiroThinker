# Proposal: fix-chat-retrieval-recall-gaps

## Why

Measured against `docs/测试集答案.xlsx` (41 rows; ~25 real cases), `/api/chat` end-to-end
**entity recall is 58% (11/19)** on single-domain gradable cases (synthesis off; harness
`apps/admin-console/scripts/eval_recall_chat.py`). The prior commit claim of 74% is **not
reproducible**: it depended on Serper web-search augmentation, which now fails with `403
Unauthorized` (dead credential) — see the `add-web-augment` change for that lever. With web
dead, real recall is 58% (pure DB + SQL routing + RRF + lookup paths).

First-principles DB+Milvus-grounded diagnosis
(`.agents/runs/retrieval-generation-alignment/diagnosis-baseline.md`) found three failure modes:

- **FM1a — data not ingested** (云迹/九号/擎朗/嘉立创 absent from `company`; 许晋诚/陈功 absent →
  block FM3): PRIMARY blocker, **not retrieval-fixable** (needs ingest — separate workstream,
  recorded as a decision gate).
- **FM1b — recall ranking for present+ready data**: broad-profile leaders (普渡 raw-ANN 32,
  深南电路 50) cut by the candidate window. The `candidate_limit` raise (30→64) was
  eval-NEUTRAL and **reverted**; the delivered lever is **hybrid RRF** (lexical-coverage fusion).
- **FM3 — routing**: cross-filter professor queries classify as `unknown` → no recall attempted
  (data-blocked for #19, but routing-reachable is the contract).

This change closes the **retrieval-logic** gap (FM1b RRF + FM3 routing) at the **58% baseline**,
eval-gated, with evidence persisted. FM1a (ingest) and web-augment (Serper) are split to their
own workstreams — NOT claimed solved here.

## What Changes

1. **FM1b — Hybrid RRF** (DELIVERED): vector-rerank + lexical-coverage + rerank three-way RRF
   fusion rescues broad-profile entities (普渡/深南电路) that the reverted `candidate_limit` raise
   could not. (Web-search augmentation is OUT of this change — split to `add-web-augment`.)
2. **FM3 — cross-filter professor routing** (DELIVERED, data-blocked): attribute-AND-attribute
   professor queries reach professor recall, not `unknown`. Acceptance is routing-reachable;
   recall ceiling for #19 is bound by ingest (许晋诚/陈功 absent).
3. **Eval harness** is the RED→GREEN oracle; baseline 58% persisted as per-case JSON.

Non-goals (deferred):
- FM1a ingest of missing companies (separate data-pipeline workstream — see
  `fm1a-ingest-decision.md`).
- The candidate_limit raise (FM1b original) was eval-NEUTRAL and reverted — NOT delivered.
- Web-search augmentation (Serper 403) — split to `add-web-augment`.
- Generation rewrite / streaming / AnswerGenerator (separate change).
- Embedding/profile-quality rework for broad summaries (mitigated via RRF, not redone).

## Capabilities
### New Capabilities
- `agentic-rag-retrieval` — chat retrieval recall behavior (baseline from
  `docs/Agentic-RAG-PRD.md` / `docs/Agentic-RAG-Operating-Guide.md`; this change deltas it).

## Impact
- `apps/admin-console/backend/api/chat.py` (routing/classifier for FM3) +
  `apps/miroflow-agent/src/data_agents/service/retrieval.py` (`_hybrid_rrf_select` for FM1b).
- No schema change; no A–G semantics change (only recall depth + a routing branch); evidence
  shape, `_VALID_DOMAINS`, `_is_indexable_paper` unchanged.
