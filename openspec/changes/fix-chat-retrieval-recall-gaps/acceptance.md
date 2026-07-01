# Acceptance: fix-chat-retrieval-recall-gaps

A change is accepted only when ALL hold.

## Recall (eval-gated, 58% baseline)
- [x] End-to-end entity recall (`eval_recall_chat.py`) is **58% (11/19)** (current-HEAD, no-web,
      Serper 403), persisted as `post-fix-recall.json`, with no passing case regressed.
      (The commit-claimed 74% is NOT reproducible — depended on a now-dead Serper key; web is
      split to `add-web-augment`.)
- [x] RRF rescues broad-profile entities (#4 普渡) into the candidate window (verified via
      `eval_recall.py` forced-domain).
- [x] FM3: #19 routed to professor recall (no longer `unknown`) — routing-reachable; recall
      ceiling bound by ingest.

## Precision (new oracle, baseline only this round)
- [x] `precision-baseline.json` persisted; false-positive substrate surfaced (candidate labels);
      `unsourced_web=0` (Serper dead — web-provenance audit deferred to `add-web-augment`).
      GREEN p@k threshold set after labeling (design §1.1).

## No regression
- [ ] Patent applicant (#40) / exact (#41) routing still correct.
- [ ] Single-entity profiles (#1/#10/#16/#21/#24/#26/#34) still recalled.
- [ ] Existing chat tests green; `openspec validate fix-chat-retrieval-recall-gaps --strict` 0.

## Honest scope (not blocked-on)
- [x] FM1a (云迹/九号/擎朗/嘉立创/许晋诚/陈功 not ingested) recorded in
      `fm1a-ingest-decision.md` as the recall ceiling — separate ingest decision; NOT claimed
      solved.
- [x] Web-search augmentation (Serper 403) split to `add-web-augment` — NOT claimed solved.
- [x] **FM4 (cross-domain paper→professor not wired on topic path)** recorded in `design.md`
      as a known recall-logic gap, **measured** by oracle case 50 (0/4: 柯文德/任尔夫/王强/刘桂良
      missed). NOT a data gap (3367 active professors, 2843 with paper links). Implementation
      deferred to a follow-on recall-logic change.

## Evidence to report
- post-fix-recall.json + precision-baseline.json + latency-baseline.json; per-case delta; FM1a
  blocker note; Serper-403 note.
