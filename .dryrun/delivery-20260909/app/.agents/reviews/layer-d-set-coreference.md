# Review — layer-d-multi-turn-context, task group 2 (displayed-set + set coreference)

- **Date:** 2026-07-09  **Builder:** Codex  **Reviewer:** Claude  **Decision: Accept**

## Scope check (handoff → code)

| Task | Delivered | Notes |
|---|---|---|
| 2.1 displayed-set capture | ✓ | `retrieval_evidence` harvesting loop removed from `result_ids_by_domain` (chat_context.py); primary ids + list keys + citations kept |
| 2.2 set-word detection | ✓ | pure `detect_set_referent` + `SetReferent` dataclass; bare + domain-worded (4 domains) tables; doesn't fire on singular pronouns |
| 2.3 empty-set clarification guard | ✓ | `resolve_set_referent` on SessionContext + pre-narrowing guard in chat() → `C_cross_domain_clarification` listing available domains |
| qid12 这论文 | ✓ | added 这论文/该篇论文 → paper in `_PRONOUN_DOMAIN_MAP` |
| 2.4 unit tests | ✓ | tests/test_chat_set_coreference.py — displayed-only capture, set-word table (+/-), clarification, resolver, pronoun rewrite |

Hard boundaries respected: no routing/traversal, `_handle_d_narrowing` body untouched, no anchor-stack change, no classifier prompt change, no fixture/eval edits, A-G unchanged.

## Reviewer fixes applied (Claude, inline)

1. **Bare-referent anchoring** — `detect_set_referent` matched bare 他们/这些/上述 via substring (`in text`), which would fire mid-sentence on **qid21** (`…灵巧手厂商，他们在数据层面…`) and route a single-turn query to the set path. Tightened bare referents to `text.startswith(surface)`. Verified: all 14 parametrized cases still pass AND qid21 single-turn stays correct (the exact false-positive that would have been a real regression).
2. **Pre-existing flaky test** — `test_independent_topic_switch_clears_previous_context` fails in this env because `_augment_rows_with_web` runs a real Serper search and leaks URL rows into `last_result_set["company"]`. This is the commit-535ed9e flaky class (it fixed 4 sibling tests, missed this one), NOT a group-2 defect (Codex's sandbox lacked network → it saw green). Mocked `_augment_rows_with_web` to a no-op there per the established pattern. With `CHAT_AUGMENT_WEB=0` the suite was already 106-green, confirming root cause.

## Evidence

- Unit: **106 passed** (affected chat suite + new file), ruff clean.
- Multi-turn eval (post-group2 vs RED baseline):
  - **S4-F (empty-set/domain-mismatch) FAIL → OK** — M5 fixed exactly as specced.
  - S1/S2/S3/S5/S6A/S6B/S6C unchanged-red — expected (routing/traversal/predicates = groups 3/4/5).
  - passed_cases 1 → 2; no new multi-turn regressions.
- **Single-turn 19-case: ZERO regressions** (per-qid required-hit diff vs 2026-07-05 baseline; several improved from Layer C, none dropped).

## Follow-up recorded (out of group-2 scope)

- **Web-URL pollution of last_result_set (pre-existing data-hygiene bug):** `_augment_rows_with_web` injects rows that can enter `last_result_set[domain]` as non-entity-ID URLs via citations. Pre-existing, surfaced by this env. Matters for Layer D (a web-augmented answer's set would contain garbage). Defer to a small follow-up — either filter citations to entity-ID-shaped ids in `result_ids_by_domain`, or type web rows out of the set. Not blocking group 2.

## Next

Group 2 Accepted ⇒ **task group 3 (hybrid routing) is Ready.**
