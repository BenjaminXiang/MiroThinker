# Change Log: professor-fact-cross-format-dedup

## 2026-06-23 — Created (Phase: proposed)

- Authored OpenSpec change: proposal, specs delta (MODIFY idempotency +
  ADD universal-writer + ADD semantic-key-correctness), design, tasks,
  acceptance, source-links, agent-links.
- Baselined against the live `professor-fact-extraction` spec, which already
  mandates `normalized_fact_key` dedup — this change strengthens the key to
  semantic and closes the four raw-INSERT bypass paths.
- Key algorithm + false-positive guards validated empirically this session
  (`.agents/runs/professor-fact-within-format-dedup/`, ~23,000 rows superseded,
  zero confirmed false positives after the years-from-whole fix).
- Verification contract drafted (deterministic → unit/contract RED, full TDD
  allowed per CLAUDE.md §14.7).
- Next: hand to Codex via `.agents/handoffs/2026-06-23-professor-fact-cross-format-dedup.md`.

## 2026-06-23 — Implemented + self-reviewed (Phase: in-verification)

- Codex dispatch did not execute (companion background-status quirk); implemented
  directly with full TDD per the verification contract.
- NEW `fact_dedup_key.py`; upgraded `_upsert_fact` (semantic + keep-richest);
  removed `fact_backfill` retire helpers; routed paths B/C/D/G through the writer.
- Tests: `test_fact_dedup_key.py` (25), `test_upsert_fact_dedup.py` (5),
  `test_fact_extraction.py` + `test_run_topic_split_backfill.py` updated →
  42 touched-area tests GREEN; ruff clean; `grep "ON CONFLICT"` on
  `INSERT INTO professor_fact` → NONE.
- Full suite: 25 pre-existing failures + 63 errors remain, all unrelated
  (0 references to changed symbols; spot-checked). See
  `.agents/reviews/2026-06-23-professor-fact-cross-format-dedup.md` (accept).
- Residual (prose↔structured cross-format) documented as out of scope.
- Changes unstaged; no commit (commit-on-request).

