# source-links: fix-chat-retrieval-recall-gaps

Legacy behavior baseline consulted (not yet migrated to OpenSpec; per CLAUDE.md §14.3
touch-to-promote — this change touches chat retrieval but does NOT fully migrate the
capability; baseline authority remains the legacy docs until a later change):
- `docs/Agentic-RAG-PRD.md` — query classes A–G, recall/fusion/rerank intent.
- `docs/Agentic-RAG-Operating-Guide.md` — current online posture (M0.1–M6).

Code consulted (current behavior):
- `apps/admin-console/backend/api/chat.py` — classification + routing + answer assembly.
- `apps/admin-console/backend/deps.py` — RetrievalService/embedding/milvus/rerank wiring.
- `apps/miroflow-agent/src/data_agents/service/retrieval.py` — retrieve(), candidate_limit,
  rerank fallback, _search_collection (limit=candidate_limit).
- `apps/miroflow-agent/src/data_agents/providers/rerank.py` — RerankerClient (Qwen3-Reranker).

Measurement artifacts (this change):
- `apps/admin-console/scripts/eval_recall.py`, `eval_recall_chat.py`.
- `.agents/runs/retrieval-generation-alignment/diagnosis-baseline.md`.
