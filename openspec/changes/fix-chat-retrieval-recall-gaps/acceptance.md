# Acceptance: fix-chat-retrieval-recall-gaps

A change is accepted only when ALL hold.

## Recall (eval-gated)
- [ ] End-to-end entity recall (`eval_recall_chat.py`) rises from baseline **53% (10/19)** to
      **≥ 63% (12/19)** on single-domain gradable cases, with **no passing case regressed**.
- [ ] FM1b: 普渡 (#4) and/or 深南电路 (#13) enter the candidate window after the
      candidate_limit raise (verified via `eval_recall.py` forced-domain).
- [ ] FM3: #19 (许晋诚/陈功) is routed to professor recall (no longer `unknown`).

## No regression
- [ ] Patent applicant (#40) / exact (#41) routing still correct.
- [ ] Single-entity profiles (#1/#10/#16/#21/#24/#26/#34) still recalled.
- [ ] Existing chat tests green; `openspec validate fix-chat-retrieval-recall-gaps --strict` 0.

## Honest scope (not blocked-on)
- [ ] FM1a (云迹/九号/擎朗/嘉立创 not ingested) recorded as the remaining recall ceiling —
      requires a separate ingest decision; NOT claimed solved by this change.

## Evidence to report
- Baseline 53% JSON → post-fix recall JSON; per-case hit/miss delta; FM1a blocker note.
