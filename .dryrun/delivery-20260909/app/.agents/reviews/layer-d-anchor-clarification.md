# Review — layer-d-multi-turn-context, task group 6: anchor discipline (lock) + member-listing clarification

- **Date:** 2026-07-09  **Builder:** Codex  **Reviewer:** Claude  **Decision: Accept**

## Scope check

| Deliverable | Verdict |
|---|---|
| Member-listing clarification (singular pronoun + no anchor + live same-domain set → list members) | ✓ `_singular_pronoun_domain` + clarification; labels via retrieval-service `get_object` → by-id helpers → ID fallback; `query_type=C_cross_domain_clarification` |
| Profile-then-他 unchanged (anchor exists → resolves normally) | ✓ guarded to no-anchor+live-set only |
| Anchor-discipline regression lock (list answers push no anchor; profile does) | ✓ |
| tests/test_chat_anchor_clarification.py | ✓ |

Hard boundaries respected: NO change to `push_entity`/`_record_and_return` (6.1 already correct), no classifier/traversal/narrowing changes, no fixture/eval edits.

## Reviewer fix applied (Claude, inline)

S3-F fixture `answer` was a placeholder ("澄清 哪位 教授 论文") that failed the coarse coverage
check. Blank it (consistent with routing-only cases) — S3-F scores on its query_type assertion
(must clarify); member-listing QUALITY is covered by the unit test + smoke. Correct oracle for a
behavior case.

## Evidence

- Unit: **150 passed** (affected suite), ruff clean.
- Smoke: list → "他的论文是哪些" → "您指的是上轮列表中的哪一位？1.高庆 2.马鑫 … 9.邵奕天" (all members listed).
- Multi-turn (`post-group6-final-2026-07-09.json`): **9/18 pass** (S3-F flipped). No D-mechanism
  defects remain — the 9 red are all out-of-D-scope / oracle-artifact / upstream-retrieval (see
  group-7 acceptance).
- **Single-turn: no PASSING case regressed** (qid16/19/20 hit-count wobble is synthesis variance
  on already-failing knowledge/judgment queries; group 6 doesn't touch single-turn synthesis).

## Next

Group 6 Accepted ⇒ D-scope behavioral work COMPLETE. Proceed to group-7 acceptance reckoning.
