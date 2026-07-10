# Verification + Review — wire-professor-paper-list-traversal (2026-07-10)

> Claude-owned. Behavior-affecting (new `A_prof_papers` path on the A-professor route). Closes the
> Type2 gap from the paper-retrievability baseline. GREEN is eval-first, backed by real evidence
> this session + 15 unit regression tests. Companion to `openspec/changes/wire-professor-paper-list-traversal/`.

## Change
- **change-id:** `wire-professor-paper-list-traversal` (OpenSpec Standard; behavior-affecting).
- **Capability delta:** `agentic-rag-retrieval` (ADDED: professor-paper-list → `A_prof_papers`).
- **Code:** `backend/api/chat.py` —
  - `_prof_paper_list_intent(query)` (pure predicate, extracted for testability).
  - `_professor_profile_or_papers_response(conn, query, prof, topics, n_papers)` (returns
    `A_prof_papers` or `A_prof_profile`).
  - Wired at the two A-professor sites (A+name LLM-dispatch branch + rule-based A-professor branch).
  - **Reuses** existing `_lookup_verified_papers_for_prof` + `_answer_prof_papers(prof, rows)`
    (the D-path helpers) — no new fetch/render logic. (Initial implementation re-invented these
    and hit a name collision with the existing 2-arg `_answer_prof_papers`; corrected to reuse.)

## RED (baseline, before fix — true)
- Type2 (professor→paper) e2e recall = **1/9 (11%)**. "X教授发表了哪些论文" → `A_prof_profile` →
  answer showed only "已收录 N 篇论文" (count); the professor's verified papers were never listed.

## GREEN (after fix — all required, verified this session)

1. **Routing + real retrieval (`eval_recall_chat.py`, synth off, backend cycled):**
   - qid106 常瑞华 → `A_prof_papers` **3/3** (VCSEL, Fabry-Perot, Grating; was 1/3).
   - qid107 刘江 → `A_prof_papers` **3/3** (Glaucoma, Retinal, SkrGAN; was 0/3).
   - qid108 陈勇勇 → `A_prof_papers` **2/3** (Mamba-Transformer, Snapshot Compressive; Quaternion
     not in top results; was 0/3).
   - Type2 recall **1/9 → 8/9**; paper-domain **7/20 (35%) → 14/20 (70%)**; overall e2e
     **21/43 (49%) → 28/43 (65%)**.
2. **Zero regression.** All 21 other oracle cases (qid1-51, 100-105, 109-110) classify + recall
   identically before/after.
3. **Unit regression tests (`tests/test_paper_retrievability.py`): 15 passed.** Guards Type4
   classification (5) + Type2 paper-list intent (10: 6 positive incl. parametrized, 4 negative).
4. **100-case classifier benchmark:** the Type4 broadening initially over-fired on Q050 ("论文 X
   的深圳作者有哪些" A→B); fixed by a `作者/团队/发明人` guard + a regression test. After the fix
   the benchmark is back to its **pre-existing** state — only Q004/Q017 ("X教授是谁" → G via the
   ambiguous-intro rule, expected A) remain red; those are NOT caused by this work (the rule is
   论文-gated; confirmed absent from this diff) and are filed as a separate professor-ambiguity
   follow-up.

## Honest scope
- qid108 misses "Quaternion" (1 paper not in the top verified-paper set) — a ranking/completeness
  detail, not a routing defect.
- Type4 oracle tokens remain over-specific (topic-recall substring measure is weak) — separate
  measurement follow-up.

## Decision

**Accept.** Contract scope met (professor→paper list traversal wired, reusing existing helpers),
evidence traceable (e2e 28/43 + 15 unit tests + benchmark back to pre-existing), zero new
regression, A-G semantics preserved (routing still A→professor; handler decides profile-vs-papers).
Slice state: Candidate → **Accepted** (not Archived; waits on parent `agentic-rag-retrieval`
settling).

## Verification commands (run this session)

```bash
cd apps/admin-console && unset <proxy vars>
set -a; source ../miroflow-agent/.env; set +a
export DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real UV_OFFLINE=1

# unit regression (pure, no DB/Milvus)
uv run pytest tests/test_paper_retrievability.py -q                       # 15 passed
uv run pytest tests/test_classifier_benchmark.py -k deterministic         # Q004/Q017 pre-existing only

# e2e (backend DOWN — in-process Milvus; codex-companion auto-restarts after)
DATABASE_URL=… MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
  uv run python scripts/eval_recall_chat.py        # 28/43 (65%); qid106-108 A_prof_papers
```
