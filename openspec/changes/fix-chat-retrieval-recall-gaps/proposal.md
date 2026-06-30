# Proposal: fix-chat-retrieval-recall-gaps

## Why

Measured against `docs/测试集答案.xlsx` (41 rows; ~25 real cases), `/api/chat` end-to-end
**entity recall is 53% (10/19)** on single-domain gradable cases (harness:
`apps/admin-console/scripts/eval_recall_chat.py`). First-principles DB+Milvus-grounded
diagnosis (`.agents/runs/retrieval-generation-alignment/diagnosis-baseline.md`) found three
failure modes:

- **FM1a — data not ingested** (云迹/九号/擎朗/嘉立创 absent from `company`): PRIMARY blocker,
  **not retrieval-fixable** (needs ingest — flagged as a separate data workstream).
- **FM1b — recall candidate window too small**: `candidate_limit=30` cuts ready+embedded
  companies (普渡 raw-ANN 32, 深南电路 50) before the reranker sees them. The reranker works
  (HTTP 200) but only just rescues them because their `profile_summary` is broad.
- **FM3 — routing**: cross-filter professor queries (e.g. "毕业于早稻田，且在深圳专注在机器人
  行业的企业家") classify as `unknown` → no recall attempted.

This change closes the **retrieval-logic** gaps (FM1b + FM3), eval-gated. FM1a (data ingest)
is recorded as the remaining blocker requiring a separate ingest decision.

## What Changes

1. **FM1b — widen the recall candidate window**: raise the default `candidate_limit` (30 →
   larger) so the cross-encoder reranker sees deep-but-relevant candidates (普渡/深南电路) before
   truncation. Eval-gated: keep only if it raises recall without hurting precision.
2. **FM3 — route cross-filter professor queries to recall** instead of `unknown`: extend the
   rule/classifier so attribute-AND-attribute professor queries (school + field) reach the
   professor Milvus recall path.
3. **Eval harness** (`eval_recall.py` + `eval_recall_chat.py`) becomes the RED→GREEN oracle;
   baseline 53% recorded; target per acceptance.

Non-goals (deferred):
- FM1a ingest of missing companies (separate data-pipeline workstream — recorded, not done here).
- Generation rewrite / streaming / AnswerGenerator wiring (separate change).
- Embedding/profile-quality rework for broad summaries (FM1b deeper layer).

## Capabilities
### New Capabilities
- `agentic-rag-retrieval` — chat retrieval recall behavior (baseline from
  `docs/Agentic-RAG-PRD.md` / `docs/Agentic-RAG-Operating-Guide.md`; this change deltas it).

## Impact
- `apps/admin-console/backend/api/chat.py` (routing/classifier for FM3) +
  `apps/miroflow-agent/src/data_agents/service/retrieval.py` (`candidate_limit` default for FM1b).
- No schema change; no A–G semantics change (only recall depth + a routing branch); evidence
  shape, `_VALID_DOMAINS`, `_is_indexable_paper` unchanged.
