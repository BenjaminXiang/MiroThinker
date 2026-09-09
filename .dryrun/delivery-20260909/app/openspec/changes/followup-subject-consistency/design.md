# Design: followup-subject-consistency

> Backfill design record. The authoritative phase-2 design is
> `docs/superpowers/specs/2026-08-12-web-answer-subject-consistency-phase2-design.md`
> (commit `04e01a3`); the implementation plan is
> `docs/superpowers/plans/2026-08-12-web-answer-subject-consistency-phase2.md`
> (amended by `367fd96` with Tasks 10-11). Phase 1 predates both; its decisions are
> summarized below from the shipped commit bodies and the follow-up record
> `.agents/runs/followups/2026-08-11-web-lane-subject-consistency.md`.

## Verification surface

- Deterministic units (identity forms, tier classifier, gate ordering, qualifier
  extraction, guidance/view builders, anti-echo guard, continuation predicates,
  soft-subject derivation guards): unit/contract tests as RED — per-task TDD in the plan
  (`apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`,
  `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`).
- End-to-end agentic behavior (multi-turn subject consistency, multi-branch guidance
  effect, stream correction in a live SSE flow): scenario eval — production-replica
  replay of fixed sessions against `/api/chat/stream` with per-turn PASS criteria
  (plan Task 8 Step 1), then production smoke. Unit tests alone were NOT accepted as
  GREEN for the behavior slices (openspec/config.yaml rules; AGENTS.md §11).
- Regression oracle: full `tests/canonical_v2/` suite + admin-console chat adapter /
  anchor-clarification / referent-history suites + chat UI node tests.
- Mock boundaries: OpenAI client fakes at the renderer boundary; page fetcher injected
  as a callable. No mocks on the retrieval/planning units under test.

## Phase-1 decisions (shipped `27d0231`, `a9b695b`, `50c4f3a`)

1. **Two-layer follow-up binding.** Continuation intent recognition in
   `followup_referents` (degree word must directly follow the opening hedge so
   enumeration/expansion stay excluded) + a session-persisted `soft_subject_name` for
   web-only subjects, injected as `soft_context_subject`. `_search_view` moved from
   `knowledge_serving_isolated` to `followup_referents` so the chat adapter can import it
   without pulling providers into the S11A quarantine boundary.
2. **Gate input discipline.** The soft context subject is merged into the consistency
   gate's bound names (so the gate covers the follow-up path) but kept OUT of
   `_matched_bound_entity`, so a soft anchor cannot mis-anchor the session to a lookalike
   canonical entity.
3. **Corroboration before consistency.** Dual-provider corroborated results rank first;
   the (then binary) gate filtered title+snippet identity-form hits with a FLOOR(3)
   backfill so single-channel niche subjects survive and the lane never errors out.
   Phase 2 replaced the binary hit/miss with the T0–T5 tier classifier because the binary
   form could not distinguish anchor-branch from other-branch content and still admitted
   shared-alias lookalikes.
4. **Correction scope.** Off-anchor correction shipped on the sync path only; the stream
   path was explicitly pinned as uncovered (chunks are irrevocable) — closed in phase 2
   Task 4 with the fail-open final-answer retry.
5. **Never-refuse.** Degradation strategy rewritten to answer from confirmed evidence
   (prompt_version v14→v15); refusal-shaped short answers rewritten; clarification
   untouched. Retained as an invariant across all phase-2 slices.
6. **Disclosure.** `web_items` added to `retrieval_done` (backward-compatible) so web
   evidence is user-auditable; later reused by the e2e PASS criteria as the observable
   retrieval-consistency signal.

## Phase-2 decisions (pointers)

- Tier semantics, gate ordering/backfill contract: spec §1 (plan Tasks 1-2).
- Qualified pinning, sync + stream fail-open correction: spec §2 (Tasks 3-4).
- Multi-branch prompt guidance (v16): spec §2b (Task 5).
- Authority-seeking views: spec §2c (Task 6).
- Correction-triggered tiered fetch with anti-echo guard: spec §3 (Task 7).
- Turn-1 soft-subject derivation and the subject-organization off-anchor check: plan
  amendment `367fd96` (Tasks 10-11), root-caused from the first Task-8 e2e run.
- Deliberate refinements recorded in-plan: stream retry failure returns the original
  streamed result instead of raising (`knowledge_answer.py` rollback constraint); the
  stream-path limitations marker was replaced by a log marker (no contract change).
