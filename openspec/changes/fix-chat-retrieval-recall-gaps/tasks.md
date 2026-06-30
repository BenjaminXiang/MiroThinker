# Tasks: fix-chat-retrieval-recall-gaps

> Eval-first. Codex may implement; Claude runs the eval oracle (localhost).

## 0. Verification contract
- [ ] 0.1 `.agents/runs/retrieval-generation-alignment/verification-contract.md` — RED =
      baseline 53% (`eval_recall_chat.py`); GREEN = recall ≥ target (acceptance). FM3 routing =
      eval-first (LLM-classifier branch).

## 1. Eval harness (the oracle) — mostly done
- [x] 1.1 `eval_recall.py` (forced-domain) + `eval_recall_chat.py` (end-to-end) — baseline 53%.
- [ ] 1.2 Pin the eval as a runnable script + record baseline JSON to the run dir.

## 2. FM1b — candidate window
- [ ] 2.1 Raise default `candidate_limit` in `retrieval.py` (30 → 64); eval-gated.
- [ ] 2.2 Re-run eval; confirm recall rises on #4/#13 (普渡/深南电路 enter candidates) without
      precision loss on passing cases; revert/adjust if it hurts.

## 3. FM3 — cross-filter professor routing
- [ ] 3.1 Add a rule/classifier-target for school+field professor cross-filter → professor
      recall (not `unknown`); locate the `unknown` fallthrough in chat.py.
- [ ] 3.2 Re-run eval; confirm #19 (许晋诚/陈功) improves; no regression on other cases.

## 4. Acceptance, ledger, validate
- [ ] 4.1 Evidence: baseline 53% → post-fix recall; per-case deltas; FM1a blocker note.
- [ ] 4.2 `openspec/change-ledger.md` status → in-verification.
- [ ] 4.3 `openspec validate fix-chat-retrieval-recall-gaps --strict` exits 0.
- [ ] 4.4 Claude review against acceptance; accept / revise / reject.
