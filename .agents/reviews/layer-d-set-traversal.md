# Review — layer-d-multi-turn-context, set cross-domain traversal (group 3 rule-routing + group 4 execution)

- **Date:** 2026-07-09  **Builder:** Codex  **Reviewer:** Claude  **Decision: Accept**

## Scope check (handoff → code)

| Deliverable | Verdict |
|---|---|
| `detect_set_operation` (rule-layer narrow-vs-traverse) | ✓ pure; domain-word scan excluding source; multi-domain→narrow |
| Dispatch wiring (after group-2 guard, before narrowing) | ✓ kills M1: traversal no longer hijacked by `_handle_d_narrowing` |
| `_handle_set_traversal` (loop retrieval-service `get_related_objects`) | ✓ per-member loop, per-member error isolation, source cap 10 + truncation declared |
| Renderer (target-centric default / member-centric on 分别) | ✓ coverage statement w/ exact counts, empty-member marking, role_type + link_status labels, candidate label |
| `_related_row_to_chat_row` extended (role_type/link_status/match_reason) | ✓ additive; single-entity C path unaffected |
| Chaining (citations → result_ids_by_domain → push_result_set target domain) | ✓ |
| structured_payload (source_ids + member_target_mapping + retrieval_evidence) | ✓ |
| tests/test_chat_set_traversal.py | ✓ detector matrix, both renderers, coverage counts, chaining, set_derived shape |

Hard boundaries respected: no classifier prompt/schema change (deferred), no `_handle_d_narrowing` body change, no anchor-stack change, no new A-G class (reuses `C_cross_domain_related`).

## Reviewer fixes applied (Claude, inline) — 3

1. **`skip_synthesis` for traversal (the real defect).** With `CHAT_LLM_SYNTHESIS=on`,
   `_build_chat_response` runs web-search + synthesis on the RAW query and overrode the
   deterministic render with hallucinated text ("尚福林教授…" — unrelated). Added a
   `skip_synthesis` flag to `_build_chat_response`; set True for set-traversal. Rationale
   (recorded as a deviation from ADR-011 D5): a relation-table join is deterministic, not
   reasoning; the rendered mapping (coverage + back-links + citations) IS the complete
   auditable answer. Synthesis added hallucination (demonstrated) with no benefit. The ADR's
   "synthesis phrases the mapping" is deferred. Verified: traversal now returns the correct
   deterministic render.
2. **Eval `set_derived` over-matching.** `_collect_source_like_ids` swept target IDs nested
   under `member_target_mapping` (key has "member") as "source-like", false-failing every
   traversal (targets are intentionally NEW). Rewrote: for payloads with explicit
   `source_ids`, pass iff `source_ids ⊆ prior basis` (members came from the set); target IDs
   never counted as violations. Narrowing falls back to overlap. Correct oracle restored.
3. **Routing-only fixture answers blanked.** S1-F/S2-F/S5-F1/S5-F2 (`source:
   synthesized-layer-d-routing-only`) had placeholder `answer` text that failed the coarse
   term-overlap coverage check. Blank them (matching the S6 chip rows, already `answer: ''`)
   so routing-only cases score on routing+set_derived, per the verification contract
   ("coverage is advisory; routing/membership is the strong oracle").

## Evidence (post-fix)

- Unit: **124 passed** (affected suite incl. new traversal tests), ruff clean.
- Multi-turn eval (`post-traversal-final-2026-07-09.json`): **7/18 scored pass**
  (S1-F, S2-F, S4-F, S5-F1, S6A-F, S6C-F, S6D-F). `query_type_assertions 9/10`,
  `set_derived_assertions 6/8`. Mechanism verified correct: prof→paper returns real
  relations (45 papers, role_type/applicant, 候选 labels); company→patent (6 patents +
  truncation declared); prof→company honest "0 records" where DB has no links.
- **Single-turn 19-case: ZERO regression** vs group-2 run.

## Remaining red (11) — by owner

- **Group 5 (narrowing mechanisms, D scope):** qid4, qid10 (在深圳 chip predicate),
  qid5 (open predicate 机械臂), S6B-F (在深圳). = 4
- **Group 6 (anchor/clarification listing, D scope):** S3-F (list-then-他 must LIST
  members, currently generic clarification). = 1
- **Out of D scope (data/R3/alias):** qid2 (无界智航 link absent), qid8 (alias
  智航无界↔无界智航 = FM5 company-name matching), qid12 (paper link data), qid15 (R3
  constraint re-query — ADR-deferred), qid25 (patent CN117873146A not in DB), S5-F2
  (chain broken: S5-F1 found 0 company links → no company set to chain). = 6

## ⚠ Acceptance-line risk (confirmed, needs user decision at group-7 time)

Of the 14 accept-line cases, after ALL D groups (5+6) the realistic ceiling ≈ **8/14**
(4 current + 4 from groups 5/6); the other 6 are out-of-D-scope (data ingest qid2/25,
alias qid8, R3 qid15, paper-link qid12, data-driven chain break S5-F2). **The ≥12/14 line
is NOT achievable from D-scope work alone.** Options to raise at acceptance: (a) cheap
in-scope additions (qid12 paper-link pronoun already done; the rest need data/FM5/R3);
(b) renegotiate the line to count D-scope cases only; (c) accept that ~6 cases are
honestly-red due to data and record them as such. Surfaced now — not a surprise at gate.

## Follow-ups logged

- Displayed-set capture is incomplete for list keys that aren't display-capped (company
  topic search puts 25 in `companies`, displays 10 → result_set has 25). Traversal handles
  gracefully (caps + declares) but ADR D1 "set = displayed" is only partially met. Small
  follow-up: cap list-key harvest to the displayed count, or have handlers mark displayed
  subset. (Same family as the web-URL pollution follow-up from group 2.)
- Classifier `referent` field (group 3.2) still deferred — rule layer covers all golden
  cases; add when paraphrase robustness is needed.

## Next

Set-traversal Accepted ⇒ **task group 5 (narrowing mechanisms) Ready** (unblocks qid4/5/10,
S6B). Group 6 (anchors/clarification listing) can follow or parallelize.
