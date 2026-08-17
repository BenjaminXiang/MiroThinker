# Design: deepening-turn-anchor-carryover

## Root-cause map (code evidence, HEAD `45d39dd`)

| # | Failure step | Code site |
|---|---|---|
| 1 | Deepening wording classified as fresh topic (no continuation, no referent marker) | `followup_referents.py` — `_CONTINUATION_*` requires 更/再; `SINGULAR_REFERENT_MARKERS` lacks generic institution nouns |
| 2 | No soft subject injected (fresh-leg derivation rejects referential phrase as query echo) | `canonical_v2_chat.py` `_soft_subject_name` guard `candidate == query` |
| 3 | Soft subject destroyed at commit (keep condition continuation-only) | `canonical_v2_chat.py` commit, keep branch `has_continuation_intent(...)` |
| 4 | Bare `它` over soft session clarifies instead of answering about the subject | `_referent_clarification_needed` soft exemption continuation-only |
| 5 | Leaked canonical handle takes over `active_anchor` on web-only turns | `knowledge_answer.py` `_commit_prose_scope` (`len(selected_handles) == 1 or state.active_anchor is None`) |
| 6 | Adapter commits the receipt as-is; later referents bind the junk anchor, which outranks the soft subject | `canonical_v2_chat.py` commit `context_receipt = turn_result.context_receipt`; `continuation_soft_subject` requires `not displayed_ids` |

## Mechanisms

### M1 — subject-carryover classification and binding

New predicates in `followup_referents.py`:

- `has_anaphoric_subject_reference(query)` — `(?:该|这个|此)(?:中心|机构|组织|平台|单位|项目|实验室|研究院|研究所|基地|联合体)` appears in the query. Domain-unconstrained by design (these nouns do not disclose the anchor's domain).
- `is_subject_carryover_reference(query)` — `not has_explicit_named_subject(query)` AND (continuation intent OR anaphoric subject reference OR singular referent with `referent_subject_domain(query) is None`). A typed person pronoun (他/她) is NOT a carryover reference; a typed company/paper/patent marker is NOT (domain disclosure).

Adapter legs that switch from continuation-only to carryover:

1. injection: `continuation_soft_subject` condition becomes `is_subject_carryover_reference(query)`;
2. commit keep: same predicate in the `soft_subject_name` keep branch;
3. clarification exemption: `_referent_clarification_needed` exempts carryover references over a soft session (and the gate's first condition additionally treats an anaphoric subject reference like a singular referent so a carryover with no anchor anywhere still clarifies rather than free-retrieves);
4. canonical binding: `_planning_displayed_ids` treats `has_anaphoric_subject_reference` like the singular-referent branch (bind the active anchor, same domain guard).

Ordering guarantees preserved: explicit named subject > canonical anchor binding > soft subject > clarification > free retrieval.

### M2 — anchor-capture guard at commit

`_sanitize_soft_turn_anchor(receipt, *, planned_displayed_ids, soft_context_subject)`:

- no-op unless the receipt has a canonical `active_anchor`, the turn planned no canonical displayed ids, and the turn carried a soft subject;
- the anchor survives only when its display name plausibly matches the subject: parenthetical/location qualifiers stripped, then containment either way or a shared contiguous run ≥ 3 CJK chars;
- otherwise the anchor is dropped (`model_copy(update={"active_anchor": None})`) and a journal line is logged.

Trade-off, accepted: a legitimate canonical anchor whose name shares nothing with the derived subject (rare abbreviation shapes) is dropped on soft-anchored turns; the session still holds the soft subject, and the canonical entity re-anchors the moment the user names it. Dropping is fail-safe toward the soft subject; keeping leaks is what produced trigger A.

Web handles are never dropped (they are the soft subject's own handle). Turns that planned canonical displayed ids (real canonical referent/entity turns) are never sanitized.

### M3 — view-pin invariant and tripwire observability

The planner already re-pins rewrite views that dropped the soft subject via the
protected-slot missing-append (`_serving_query_views`). This change:

- pins that behavior as a plan-level invariant: whenever `soft_context_subject` is present, every non-deterministic view text contains the subject;
- logs `_logger.info("serving view repin: soft subject re-appended ...")` when the append fires for the soft-subject slot, so production journals expose the tripwire rate (the register asked for exactly this observability).

## Verification surface

- Deterministic units: predicate truth table (positive/negative wordings, domain-typed exclusions), anchor-name overlap heuristic, view re-pin invariant + marker (miroflow-agent `tests/canonical_v2/test_followup_referents.py`, `test_knowledge_serving_isolated.py`).
- Adapter contract tests: injection/keep/exemption/binding legs, anchor-capture guard (leak dropped, matching anchor kept, web handle kept), regression guards (person pronoun still clarifies over org soft subject; explicit subject wins) (admin-console `tests/test_canonical_v2_chat_http_adapter.py`).
- Behavioral RED: trigger A (3-turn badcase) and trigger B (2-turn deepening) replayed through the real adapter with scripted web-only evidence — PASS = planning requests carry the org subject, no clarification, committed session keeps the subject, and a leaked canonical anchor does not bind.
- Regression oracle: `tests/canonical_v2/` suite (1 known pre-existing baseline failure), admin-console adapter/referent-history/anchor-clarification suites, chat UI node tests.
- Production smoke/deploy: NOT part of this slice; flagged for user decision after review (production 18188 is live).

## Mock boundaries

- Fake planner/read/answer at the adapter boundary (existing `_soft_anchor_*` harness); the answer fake returns receipts with chosen anchors to simulate both the leak and the legitimate capture.
- No mocks on the predicates or the planner's view assembly under test.
