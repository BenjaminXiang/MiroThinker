# Verification Contract — fix-chat-retrieval-recall-gaps

> CLAUDE.md §14.7. Eval-first.

## Change
- **change-id:** `fix-chat-retrieval-recall-gaps` (OpenSpec Standard; behavior-affecting chat
  retrieval). Capability `agentic-rag-retrieval` (new; legacy baseline = docs/Agentic-RAG-PRD.md).

## Classification
- **FM1b (candidate_limit):** deterministic (retrieval depth default). Unit-testable.
- **FM3 (cross-filter routing):** has an LLM-classifier branch → **eval-first** (§14.7); a unit
  test alone is not enough — the eval harness is the oracle.

## RED
- Baseline end-to-end entity recall = **53% (10/19)** via `eval_recall_chat.py`
  (POST /api/chat, synthesis off, required-entity substring over full JSON).
- Diagnosis: `.agents/runs/retrieval-generation-alignment/diagnosis-baseline.md`.

## GREEN
- Recall ≥ **63% (12/19)** with **no passing case regressed**.
- FM1b: 普渡 (#4) and/or 深南电路 (#13) enter the candidate window (forced-domain eval).
- FM3: #19 routed to professor recall (not `unknown`).
- Existing chat tests green; `openspec validate --strict` 0.

## Allowed Superpowers mode
- FM1b: TDD ok (deterministic default) but the REAL gate is the eval (recall delta).
- FM3: eval-first; rules may be unit-tested but acceptance = eval.
- Both: implement → re-run `eval_recall_chat.py` → adversarial check (no regression) → iterate.

## Honest scope (not claimed)
- FM1a (云迹/九号/擎朗/嘉立创 not ingested) blocks #4/#13 ceiling → separate ingest decision.
