# Tasks: fix-chat-retrieval-recall-gaps

> Eval-first. Delivered in commits 1fb6449/0c85b04/06ae50b. This change re-truths the contract
> to the measured 58% baseline (web-augment split to add-web-augment).

## 0. Verification contract
- [x] 0.1 verification-contract.md exists (RED=baseline; GREEN=recall target). Baseline
      re-measured this round = 58% (Serper 403 → web dead).

## 1. Eval harness (the oracle)
- [x] 1.1 eval_recall.py + eval_recall_chat.py — baseline.
- [x] 1.2 Post-fix recall JSON persisted (`.agents/runs/.../post-fix-recall.json`, 58% 11/19).

## 2. FM1b — candidate window (DELIVERED as hybrid RRF, not candidate_limit)
- [x] 2.1 `_hybrid_rrf_select` delivered (retrieval.py:242); candidate_limit raise reverted.
- [x] 2.2 RRF rescues broad-profile entities (#4 普渡) into the candidate window.

## 3. FM3 — cross-filter professor routing (DELIVERED, data-blocked)
- [x] 3.1 Cross-filter professor pattern routes to recall (not `unknown`).
- [x] 3.2 #19 routed to professor recall; recall ceiling bound by ingest (许晋诚/陈功 absent).

## 4. Acceptance, ledger, validate
- [x] 4.1 Evidence persisted (recall + precision + latency baseline JSON).
- [ ] 4.2 change-ledger status → in-verification.
- [ ] 4.3 openspec validate fix-chat-retrieval-recall-gaps --strict exits 0.
- [ ] 4.4 Claude review against acceptance; accept / revise / reject.

## Out of scope (split to other workstreams)
- FM1a ingest → `fm1a-ingest-decision.md` (decision gate).
- Web-search augmentation (Serper 403) → `add-web-augment` change.
