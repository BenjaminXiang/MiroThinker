# Synthesis fixes — eval findings & reusable lessons (2026-07-07)

> Workstream 1 (合成层 L3/L4) iteration. Outcome: Fix 1 + Fix 3 kept; Fix 2 reverted.
> True-accuracy eval went 47% → 37%, but the drop is variance-dominated, not a functional regression.

## What shipped (commits on `feat/professor-retrievability`)

- `e8c88fd` Fix 3 — `_call_gemma_synthesis` `temperature=0` (determinism). **Kept.**
- `7845acc` Fix 1 — list-entity enrichment: `_compact_prof_rich` / `_compact_company_rich` /
  `_enrich_list_entities` + extend render Path A (matched_professors) & Path B (matched_objects).
  Surfaced flagship product / top award / research summary for the top-3 list entities. **Kept.**
  → qid9 FAIL(0.57)→PASS(0.73); qid14/17/26 produced detailed, correct company answers.
- `452d77a` Fix 2 — LLM query reformulation. **Reverted** in `322cbd1` (see lesson 1-3 below).

## Lesson 1 — E-route bypasses `_build_chat_response`

`ctype == "E"` (knowledge QA) at chat.py:5156 calls `_answer_knowledge_qa_with_web_search`
and returns a `ChatResponse` **directly** — it never enters `_build_chat_response`. Any
synthesis-path change placed in `_build_chat_response` (intent templates, web block,
list-enrichment) is **invisible to E-route knowledge questions**.

**How to apply:** before adding logic "for knowledge questions", check the dispatch in
`chat()` (chat.py:5156 area): E-route, G-route, cross-domain, and the profile/list paths
each have their own builder. `_detect_answer_intent` returning `"qa"` does NOT mean the
query flows through `_build_chat_response` — E-route is handled earlier.

## Lesson 2 — context-fragment follow-ups are a multi-turn problem, not a reformulation problem

qid19/20 ("在真实数据采集路线中，有哪些具体方式") reference the domain ("具身智能") only
from the prior turn (qid18). Sent standalone in the eval:
- Bocha matches the raw query to **generic** data-collection results (traffic-flow sims, a
  quiz question, a .docx) — 5 results, all wrong-domain, never 0.
- An LLM reformulation can't reliably reconstruct the absent domain.

**How to apply:** standalone-reformulation (rewrite keywords, retry search) does not fix
follow-up questions whose meaning depends on prior turns. These need session context
(Workstream 2: carry the topic/domain from earlier turns into the search query). Don't
burn effort reformulating context-fragments.

## Lesson 3 — the true-accuracy eval is variance-dominated; judge harshness hides real gains

3-run-median pass count fluctuates **7-10** across runs (±3). Worse: genuinely good
synthesis answers get scored FAIL:
- qid14 (华力创科学): detailed, correct answer (founder 刘宏斌, Photon系列/SONATA, 光基多维力传感) → judged comp=0.3 → 0.67 FAIL.
- qid24 (优必选专利): 10 patents + technical summary, `llm_synthesized` → judged comp=0.1 → 0.40 FAIL.

**How to apply:** do not chase single-eval pass-count deltas smaller than the variance
band. Before more synthesis work, harden the metric (Workstream 4): 5-run median, or a
dimension/rationale scorer that resists penalizing correct-but-differently-worded answers.
Otherwise we optimize noise. The "47%→37%" this iteration is consistent with pure variance
on top of a real +qid9 gain from Fix 1.

## Remaining failure map (post-revert, for the next workstreams)

| Cluster | Cases | Root layer | Workstream |
|---|---|---|---|
| Multi-turn context-fragment follow-ups | 19, 20, 22, 23 | L2 (session context) | 2 |
| Classifier clarification (truncated/foreign title) | 11 | L2 (classifier) | 2 |
| Professor topic recall (wrong prof) | 27 | L2 (retrieval) | 2 |
| Cross-domain founder×alumni | 13 | L2 (graph) | 2 |
| Judge harshness on good answers | 14, 24 | L5 (eval) | 4 |

None of the remaining gaps are L3/L4 (synthesis presentation/generation) — Fix 1 closed
the list-depth gap. The path to 90% now runs through L2 (retrieval/multi-turn) and L5 (eval),
exactly as the first-principles framing predicted.
