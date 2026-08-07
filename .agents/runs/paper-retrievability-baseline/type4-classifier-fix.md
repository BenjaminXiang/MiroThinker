# Verification + Review — fix-paper-topic-query-classification (2026-07-10)

> **Status correction (2026-07-10): Candidate.** The historical review below accepted only the
> local classification slice. The later audit found that response-wide query echo and a changed
> Type4 token oracle prevent it from proving retrieval → citation → semantic correctness. The
> controlling re-acceptance contract is
> `openspec/changes/close-retrieval-generation-contract/` Slices A and D.
>
> Claude-owned. Behavior-affecting (A-G classification routing). The historical local slice targeted
> the Type4 routing gap from the paper-retrievability baseline. Its local GREEN evidence remains
> below, but no longer constitutes end-to-end acceptance. Companion to
> `openspec/changes/fix-paper-topic-query-classification/`.

## Change
- **change-id:** `fix-paper-topic-query-classification` (OpenSpec Standard; behavior-affecting).
- **Capability delta:** `agentic-rag-retrieval` (ADDED: paper-topic-search routing requirement).
- **Code:** `apps/admin-console/backend/api/chat.py:637` — broadened the B paper-topic rule with
  a topic-search-intent clause + two guards (not bare-EN-title, not entity-anchored). One rule;
  no other rule, schema, migration, or persisted column changed.

## RED (baseline, before fix — true)
- Type4 (topic→paper) e2e recall = **0/4**. qid109/110 classified `unknown` → zero retrieval
  (284 perovskite + 145 FL ready papers exist but were unreachable via topic query).
- Root cause: exact-paper rule (`chat.py:658`) over-fired on `论文 + ASCII run`; B paper-topic
  rule (`chat.py:637`) required ending in 论文. Direct `_classify_query_by_rules` diagnosis
  confirmed qid109/110 → type A, name=whole-query, reason "exact paper deterministic rule".

## Historical local GREEN (verified in the original session)

1. **Classification routing fixed (deterministic).** `_classify_query_by_rules`:
   - qid109 "关于perovskite…论文有哪些" → **B/paper**, topic="perovskite钙钛矿材料" (was A).
   - qid110 "关于联邦学习federated learning的最新论文" → **B/paper** (was A).
   - clean/找 variants → B/paper.
2. **Zero regression (deterministic).** qid100/16 (bare EN titles) → A/paper; qid106/107
   (professor) → A/professor; qid1/4/10/50/40/41 → identical types/domains as before.
3. **E2e routing + real retrieval (`eval_recall_chat.py`, synth off, backend cycled).**
   - qid109/110 → `query_type=B_paper_topic_search` (was `unknown`).
   - All 21 other cases identical; overall 21/43 unchanged (Type4 went 0/4 → 0/4 by the
     existing required tokens — see measurement caveat below; the ROUTING is what changed).
4. **Historical live behavior observed (`/api/chat`, synth on, backend :18188):**
   - qid109 returns **8 perovskite papers** (Hybrid Perovskite LEDs, Dion–Jacobson Phase
     Perovskite, perovskite single-crystal, …) with a synthesized answer. Was: nothing.
   - qid110 returns **8 federated-learning papers** (FedTC, FedPN, FedLF, FedREM, …). Was: nothing.

## Honest caveat — measurement, not defect

Type4 recall NUMBER stayed 0/4 because the oracle's `required` tokens for qid109/110 are
specific notable top-cited paper titles ("Hybrid Halide Perovskites", "Federated Learning Over
Wireless"), while `B_paper_topic_search` returns the **top-vector-similar** papers (different,
     different candidate set). Substring topic scoring is a weak instrument (Q3 blind spot). The
classification routing changed and the system returned topic-shaped local candidates, but the
manual “relevant” impression was not retained as blind labels and is not precision evidence.
Refining the Type4 oracle is now owned by the umbrella contract.

## Verification commands (run this session; backend cycled per [[milvus-single-writer-real-index]])

```bash
# deterministic classifier check (no Milvus; backend up or down)
cd apps/admin-console && unset <proxy vars>
set -a; source ../miroflow-agent/.env; set +a
export DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real UV_OFFLINE=1
uv run python -c "from backend.api.chat import _classify_query_by_rules as R; \
  print(R('关于perovskite钙钛矿材料的论文有哪些'))"   # -> type B, target_domain paper

# e2e (backend DOWN — in-process Milvus; codex-companion auto-restarts after)
MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 uv run python scripts/eval_recall_chat.py

# live value (backend UP)
curl -s -X POST http://localhost:18188/api/chat -H 'Content-Type: application/json' \
  -d '{"query":"关于perovskite钙钛矿材料的论文有哪些"}' | python3 -m json.tool | head
```

## Decision

**Candidate (supersedes the historical local Accept decision).** The classifier implementation and
live retrieval observations remain useful evidence, but the measurement caveat is now inside the
umbrella acceptance boundary. Re-accept only after a same-snapshot, frozen-topic paper-level
Precision@5 run plus canonical citation and semantic gates pass. This change remains unarchived.
