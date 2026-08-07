# Proposal: wire-professor-paper-list-traversal

> **Status correction (2026-07-10): Candidate.** The local traversal helper/wiring remains
> implemented evidence, but retrieval payloads are not yet guaranteed to enter canonical prompt
> evidence or a correct cited paper answer, and the current list path is not complete/predicate-aware
> pagination. Re-acceptance requires Slices A-C of
> `openspec/changes/close-retrieval-generation-contract/`. Do not archive this change before those
> linked end-to-end scenarios pass. After they pass, accept this record only as superseded history
> and archive with `openspec archive wire-professor-paper-list-traversal --skip-specs`, recording
> `superseded_by=close-retrieval-generation-contract`; default spec migration is forbidden.
>
> Behavior-affecting. Amends `agentic-rag-retrieval` (professor→paper list traversal on the
> A-professor path). Grounded in the paper-retrievability baseline (2026-07-09): Type2
> (professor→paper) recall was **1/9** — "X教授发表了哪些论文" routed to `A_prof_profile`,
> which showed only a paper COUNT ("已收录 N 篇论文"), not the papers.

## Why

The baseline measured Type2 (professor→paper) e2e recall at **1/9 (11%)**: a professor-paper-list
query ("X教授发表了哪些论文") classified `A_prof_profile` and returned the professor's profile,
which incidentally mentioned one paper in `profile_summary` at most. The professor's verified
papers (in `professor_paper_link`) were never listed.

The infrastructure already existed but was only wired for the **D multi-turn followup** path
(`D_prof_papers_followup`): `_lookup_verified_papers_for_prof(conn, professor_id)` (fetch) +
`_answer_prof_papers(prof, rows)` (render). The single-turn A-professor path did not reuse it.

## What Changes

1. **ADD** `_prof_paper_list_intent(query) -> bool` — pure predicate detecting paper-list intent
   over a professor-anchored query ("X教授发表了哪些论文" / "X的代表作" / "X的论文" → True;
   a bare profile query → False).
2. **ADD** `_professor_profile_or_papers_response(conn, query, prof, topics, n_papers)` — returns
   `A_prof_papers` (lists the professor's verified papers via `_lookup_verified_papers_for_prof` +
   `_answer_prof_papers`, reusing the existing D-path helpers) when paper-list intent is present
   AND the professor has verified papers; otherwise returns the existing `A_prof_profile`
   (unchanged, count-only). Falls back gracefully when the professor has 0 verified papers.
3. **WIRE** the helper into the two A-professor sites: the A+name LLM-dispatch professor branch
   (the single-turn path; `chat.py`) and the rule-based A-professor branch. Existing
   `_answer_prof_papers(prof, rows)` (2-arg) and `_lookup_verified_papers_for_prof` are reused
   unchanged (DRY with the D path).

### Non-goals
- **Type4 (topic→paper)**: had a separate local classifier repair but remains Candidate until the
  umbrella's paper-level precision, citation, semantic, and latency gates pass.
- **Type3 (company→paper)**: structurally dead (`professor_company_role` empty) — separate data
  workstream.
- **Q004/Q017 professor-ambiguity** ("X教授是谁" → G via the ambiguous-intro rule, should be A):
  pre-existing classifier bug, unrelated to paper-retrievability — separate follow-up.

## Capabilities

### Modified
- `agentic-rag-retrieval`: a professor-paper-list query SHALL list the professor's verified papers
  (`A_prof_papers`), reusing the professor→paper fetch/render helpers, instead of the count-only
  profile. (Capability in-flight via `fix-chat-retrieval-recall-gaps`.)

## Impact

- **Retrieval**: qid106-108 `A_prof_profile` → `A_prof_papers`; Type2 recall **1/9 → 8/9**;
  the stored 20-token paper slice recounts **8/20 → 15/20** (the historical 7/20 → 14/20 text
  omitted already-passing qid16); overall e2e **21/43 (49%) → 28/43 (65%)**.
  Zero regression on the 21 other oracle cases.
- **Code**: `backend/api/chat.py` — one pure helper + one response helper + two call-site rewires.
  No schema, no migration, no persisted column. Reuses existing `_lookup_verified_papers_for_prof`
  + `_answer_prof_papers` (no new fetch/render logic).
- **Invariant**: A-G classification semantics preserved — routing is still A→professor; the
  handler decides profile-vs-papers by intent. No new classifier type.

The impact numbers above are historical response-wide token/payload measurements. They do not prove
canonical ID retrieval, citation, or semantic answer stages and are not current acceptance evidence.
