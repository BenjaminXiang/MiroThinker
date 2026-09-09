# Handoff — layer-d-multi-turn-context, task group 6: anchor discipline (lock) + member-listing clarification

> Claude → Codex. One Ready slice (small). Groups 2/3+4/5 Accepted. This is the last
> behavioral slice before the group-7 acceptance reckoning.

## Contract

- OpenSpec: `openspec/changes/layer-d-multi-turn-context/` — spec requirement "List answers
  do not create single-entity anchors" + scenario "Singular pronoun after a bare list
  clarifies" (must LIST members, not a generic clarification).
- RED evidence: `red-notes.md` **M6** (S3-F: list-then-他 gives a generic C clarification that
  does NOT list members → user can't resolve in one turn).
- ADR-011 D2; glossary root `CONTEXT.md` (anchor).

## Code-verified finding (corrects the grilling assumption)

`_record_and_return` (api/chat.py ~4900) pushes anchors ONLY from single primary ids
(`sp.get("professor_id")` / `company_id` / `paper_id` / `patent_id`). List answers set
`matched_professors` (etc.), NOT a single primary id, so they do NOT push anchors today.
**Task 6.1 is already satisfied** — do NOT change push behavior; instead ADD a regression
test that locks it (a list answer leaves `session.entities` without a same-domain anchor).
S3-F proving this: "他的论文是哪些" after a list currently reaches the generic
`C_cross_domain_clarification` ("请先确认要查询哪一个实体") at chat.py:4124 — because
`latest_for("professor")` returns None (no anchor), exactly the no-anchor state.

## Scope

### A. Member-listing clarification (6.2) — the real fix
When a singular pronoun (他/她/这位/这家公司/这篇论文/该教授 … i.e. anything in
`_PRONOUN_DOMAIN_MAP` OR matched by `_CLASSIFIER_CONTEXT_RE` singular forms) is present, the
pronoun's domain has NO anchor, BUT `session.last_result_set[domain]` is non-empty → return a
deterministic clarification that LISTS the set members (by label), so the user can pick in one
turn. Reuse the existing clarification `query_type` values already accepted for S3/S4
(`G_ambiguous_clarification` or `C_cross_domain_clarification` — pick one; S3-F's
`expected_query_type` accepts both).

Implementation seam (suggested, verify against dispatch order): after `_rewrite_query_with_context`
runs (chat.py ~4915) and BEFORE the query proceeds to C-routing, detect:
- a singular pronoun for domain D is in the raw query (`_SESSION_PRONOUNS_RE.search`),
- `session.latest_for(D) is None` (no anchor), AND
- `session.last_result_set.get(D)` is non-empty
→ build + return a clarification listing up to ~10 member labels.

Member labels: the result set stores IDs only. Fetch labels by ID via the retrieval service
`get_object(domain=D, object_id=...)` (already used in `_source_member_label`) or the by-id
helpers; best-effort (fall back to the ID if a label fetch fails). Cap 10; if more, note
"等共 N 个".

Answer shape example: "您指的是上轮列表中的哪一位？1. 张三（清华大学深圳国际研究生院）
2. 李四（南方科技大学）… 等共 9 位。" structured_payload: `{referent_domain, candidate_ids,
clarification_reason: "singular_pronoun_no_anchor_live_set"}`.

Guard: profile-then-他 MUST stay unchanged (anchor exists → resolves normally). Add the check
explicitly so the clarification only fires in the no-anchor + live-set case.

### B. Lock anchor discipline (6.1 regression test)
New test: a list answer (e.g. A_prof_list_by_topic) leaves `session.entities` with NO
professor anchor (assert `latest_for("professor") is None` after the list turn), while a
profile answer DOES push one. This locks the current correct behavior so a future change
can't silently regress it. No production change.

### C. Tests (new tests/test_chat_anchor_clarification.py, env off)
- Member-listing clarification: list head → "他的论文是哪些" → clarification that LISTS member
  labels (assert the member names appear in answer_text; query_type in the accepted set);
  structured_payload carries candidate_ids.
- Profile-then-他 unchanged: profile head → "他的论文" → resolves to that professor (NOT a
  clarification). Use a mocked retrieval/profile path.
- Anchor-discipline lock (B): list head leaves no anchor; profile head pushes one.
- No live set + singular pronoun → existing generic clarification behavior (don't list
  nonexistent members).

## Non-goals (hard boundaries)

- NO change to anchor PUSH behavior (6.1 is already correct — only test it).
- NO classifier/traversal/narrowing changes.
- NO fixture / eval-runner edits.
- Do NOT run the multi-turn eval or restart the backend (Claude runs eval at review; backend
  on :18188 live — leave it).

## Environment

`cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy
ALL_PROXY no_proxy NO_PROXY && CHAT_AUGMENT_WEB=0 UV_CACHE_DIR=/tmp/mirothinker-uv-cache uv run
--no-sync pytest tests/test_chat_anchor_clarification.py tests/test_chat_set_coreference.py
tests/test_chat_set_traversal.py tests/test_chat_narrowing_mechanisms.py tests/test_chat_d_narrowing.py
tests/test_chat_session_persistence.py tests/test_chat_multi_domain_entity_stack.py -q`

## Candidate criteria

- All listed unit tests green; full chat suite no new failures; ruff clean.
- Diff confined to: api/chat.py (the clarification seam) + new test file. NO production change
  to push_entity / _record_and_return.
- Report: exact commands + output, files changed, any spec-vs-code discrepancy.

## Next owner

Claude review → eval (expect S3-F → member-listing clarification, PASS; single-turn zero
regression) → Accept ⇒ group 7 (GREEN + acceptance reckoning).
