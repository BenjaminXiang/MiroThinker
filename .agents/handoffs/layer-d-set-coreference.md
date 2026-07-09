# Handoff — layer-d-multi-turn-context, task group 2: displayed-set semantics + set coreference

> Claude → Codex. One Ready slice (tasks 2.1–2.4). Group 1 (eval runner + RED baseline)
> is Accepted; this is the first production-code slice.

## Contract

- OpenSpec: `openspec/changes/layer-d-multi-turn-context/` — specs
  `specs/chat-multi-turn-context/spec.md`, requirements: "Result set captures displayed
  entities only", "Set coreference resolves to the prior result set" (this slice), plus
  groundwork consumed by later groups.
- Verification contract: `.agents/runs/layer-d-multi-turn-context/verification-contract.md`.
- RED evidence this slice attacks: `.agents/runs/layer-d-multi-turn-context/red-notes.md`
  failure modes **M2 (partial: set discipline), M3 (partial: resolution), M5** — plus the
  qid12 pronoun-variant cheap fix. Routing/traversal/predicates (M1/M2-exec/M4/M7) are
  LATER groups — do NOT implement them here.
- ADR-011 decisions D1 (displayed set), D2 (partial — clarification shape), D3 (partial —
  set-word detection only, no routing changes); glossary root `CONTEXT.md`.

## Scope (tasks 2.1–2.4)

1. **2.1 Displayed-set capture** — `result_ids_by_domain` (services/chat_context.py:41)
   currently harvests: primary ids, list keys, ALL `retrieval_evidence`, citations.
   Change: **drop the `retrieval_evidence` loop entirely**; keep primary ids + list keys +
   citations (these are what answers render). Sole call site: chat.py:4941
   (`_record_and_return`) — no signature change needed. Update/extend affected tests
   (grep hits: test_chat_retrieval.py, test_chat_e_web_search.py,
   test_chat_suggested_followups.py — fix expectations, do not delete assertions).
   NOTE: list keys in `structured_payload` are what the answer displays (e.g.
   `matched_professors` is already display-capped by the handlers); if you find a payload
   key that is NOT rendered in the answer text, leave a code comment and keep it out of
   scope — do not chase render-payload sync in this slice.
2. **2.2 Set-word detection** — new pure helper in services/chat_context.py:
   `detect_set_referent(query) -> SetReferent | None` where SetReferent carries
   `domain: str | None` (explicit domain word) and the matched surface form. Detect:
   bare 他们/这些/上述/上面这些; domain-worded 上述教授/这些公司/上述企业/这些教授/
   上述论文/这些专利 etc. (all 4 domains, 上述/这些 × domain-word table; include 企业/公司
   both). Must NOT fire on single-entity pronouns (他/她/这位/这家公司/这篇论文 —
   existing `_PRONOUN_DOMAIN_MAP` territory). Pure function + table, unit-test heavy.
3. **2.3 Resolution + clarification guard** — in chat.py, BEFORE the existing
   `looks_like_narrowing_query` dispatch (chat.py:5063):
   - If `detect_set_referent` fires with an explicit domain and
     `session.last_result_set.get(domain)` is empty → return a deterministic clarification
     (`query_type="C_cross_domain_clarification"`, text states 当前上下文没有可指代的
     {domain label}列表，请先检索; include the domains that DO have sets). This kills M5
     (S4-F must stop running D_narrowing).
   - If it fires with a bare referent and `latest_result_domain()` is None → same
     clarification (no sets at all).
   - If a set EXISTS for the referent: this slice does NOT yet route to traversal
     (group 3/4). Fall through to existing behavior UNCHANGED. (S1/S5 stay red — expected;
     do not try to make them pass.)
   - Expose the resolved (domain, ids) via a small helper on SessionContext
     (e.g. `resolve_set_referent(ref) -> tuple[str, list[str]] | None`) for groups 3-5.
4. **qid12 cheap fix** — add 这论文/该篇论文 variants to `_PRONOUN_DOMAIN_MAP`
   (chat.py:1892) mapping to paper (这论文 currently misses; 这篇论文 exists).
5. **2.4 Unit tests** — new test file (e.g. tests/test_chat_set_coreference.py), style of
   test_chat_d_narrowing.py (`_FakeSessionStore`, env off):
   `CHAT_LLM_SYNTHESIS=off CHAT_QUERY_CLASSIFIER=off`. Cover: displayed-only capture
   (payload with retrieval_evidence extras → NOT in last_result_set), set-word table
   (positive + negative incl. singular pronouns), empty-set clarification (S4 shape:
   company head → 上述教授… → clarification, not D_narrowing), bare-referent-no-sets
   clarification, 这论文 rewrite.

## Non-goals (hard boundaries)

- NO routing changes for set+operation (no traversal, no narrow-vs-traverse splitter, no
  classifier prompt/schema changes) — groups 3/4.
- NO narrowing mechanism changes (`_handle_d_narrowing` body untouched except that the new
  guard runs before it) — group 5.
- NO anchor-stack changes (`entities` push behavior stays as-is) — group 6.
- NO edits to fixtures/test_cases.yaml/multi_turn_cases.yaml or the eval runner.
- A-G query_type taxonomy unchanged (reuse `C_cross_domain_clarification`).

## Environment

- Unit tests: `cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY
  HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY && uv run --no-sync pytest tests/ -x -q`
  (at minimum: the new file + test_chat_d_narrowing.py + test_chat_session_persistence.py +
  test_chat_retrieval.py + test_chat_e_web_search.py + test_chat_suggested_followups.py).
- Do NOT run the multi-turn eval or restart the backend (Claude runs the eval at review
  time; backend on :18188 is live and must stay untouched).

## Candidate criteria (for this slice)

- All listed unit tests green (new + affected), full chat test suite no new failures.
- Diff confined to: services/chat_context.py, api/chat.py (the two insertion points +
  pronoun map), new/updated test files.
- Report: exact commands + output, files changed, any spec-vs-code discrepancy found.

## Next owner

Claude review → eval spot-check (S4-F flips to clarification; S6B/S1 unchanged-red
expected; single-turn 19-case no regression) → Accept ⇒ group 3 Ready.
