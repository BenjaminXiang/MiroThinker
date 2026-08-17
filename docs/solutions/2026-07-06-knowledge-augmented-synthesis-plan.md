# Plan — knowledge-augmented synthesis (fix the structural accuracy cap)

> First-principles fix for the 42% recall / 14% coverage ceiling. The system is a
> retrieval-summarizer whose synthesis rule ("only use evidence facts; if insufficient,
> say 证据不足以回答") makes it REFUSE knowledge/judgment questions it could answer. This
> plan turns it into a domain-expert that grounds entity claims but uses LLM + web
> knowledge for conceptual content. Behavior-affecting → OpenSpec change before code.

## 1. Problem (root cause, verified)

Test set = 3 intent classes; the architecture handles only one:

| Intent | Examples | DB-answerable? | Current behavior | Score |
|---|---|---|---|---|
| **entity-retrieval** | qid1/3/9/11/17/26/27 (profiles, lists) | yes | retrieve + summarize | 30–60% (capped by summary brevity) |
| **knowledge/conceptual** | qid18–23 ("几种技术路线", "有哪些具体方式", "几种实现方法") | **no** (no data-route taxonomy in DB) | **refuse** ("证据不足以回答") | 0–10% |
| **judgment** | qid16 ("是否属于大牛"), qid17 eval parts | partial | returns profile, no judgment | low |

The synthesis system-prompt rule (1) is the cap: `只使用证据中出现的事实，不要编造；证据不足以回答时直说"证据不足以回答"`. For qid18–23 the DB has no taxonomy → the LLM is *forbidden* from answering (it knows embodied-AI data routes, but can't say). 6 cases structurally 0.

## 2. Solution — intent-aware, knowledge-augmented synthesis

Three changes, one architectural shift (retrieval-summarizer → domain-expert-grounded-on-DB+web):

1. **Detect intent** (entity-retrieval / knowledge / judgment) per query.
2. **Pick a synthesis mode** per intent; lift the evidence-only restriction for knowledge/judgment.
3. **Augment web search** so knowledge answers are grounded in real web content (not just snippets).

Invariants preserved: specific entity claims (professor X / company Y / paper Z's attributes) MUST stay evidence-grounded (no hallucinated entities). Only *general/conceptual/methodology* content may use LLM knowledge.

## 3. Intent detection (lightweight, no new LLM call)

A keyword + query_type heuristic in chat.py (`_detect_answer_intent(query, query_type)`):

- **judgment** if query matches eval terms: `评价|大牛|怎么样|如何|竞争力|对比|优劣|排名|水平|属于.*吗|强不强`.
- **knowledge** if query matches conceptual terms AND is not a bare entity lookup:
  `几种|多少种|哪些.*方式|哪些.*方法|技术路线|路线|原理|分类|类型|区别|趋势|发展|什么是|如何实现|具体方式`.
  (Exclude when the query is dominated by a specific entity name — those are retrieval.)
- **retrieval** otherwise (default; entity profiles/lists).

Ambiguous → default retrieval (safe/grounded). Verify the mapping by logging the query_type + detected intent for qid1/16/18/19/3 once the backend is up (the grounding step the backend lock stalled).

## 4. Web search interface — YES, augment it (the decision)

**Decision: augment web search with article-content fetching for knowledge-intent queries.**

Why: knowledge answers need real content, not snippets. "具身智能 数据路线" taxonomy lives in articles; a Serper snippet is too shallow to ground the answer. Existing infra: `upload.py` already has `--serper-fetch-article-text` (article fetch capability exists, the chat path doesn't use it).

Mechanism:
- Add `WebSearchProvider.search_with_content(query, *, fetch_articles=0..3)` — runs the search, then fetches full text for the top N results (reuse the existing article-fetch helper).
- For **knowledge** intent: fetch top 2–3 articles → feed as rich evidence blocks (truncated to a per-article char budget, e.g. 1500). For **retrieval/judgment**: keep snippet-only (entity grounding doesn't need full articles; lower latency/cost).
- Guard: article fetch is best-effort + bounded (N, char budget, timeout) — never block the answer on a slow fetch.

(Defer: query reformulation for web — a refinement; the article-fetch is the primary augmentation.)

## 5. Synthesis modes (3 system prompts)

The intent selects the system prompt in `_call_gemma_synthesis` (pass intent → pick prompt). Evidence blocks are the same (DB + web); the *instructions* differ:

- **retrieval** (deepened current): "基于证据，给出结构完整、信息丰富的画像/列表(基本信息、履历、技术产品、亮点等)，尽量覆盖证据中的所有重要字段。每个事实用[N]标注。仅使用证据中的事实。"
- **knowledge**: "用户问的是概念/方法/分类问题。请结合(1)提供的证据(DB+网络文章)与(2)你的领域知识作答。**具体实体**（某教授/企业/论文及其属性）必须来自证据并用[N]标注，不得编造；**通用概念/方法/分类/趋势**可使用你的领域知识，并以'（行业一般认知）'标注。结构清晰、分类列举。"
- **judgment**: "用户要求评价/判断。基于证据(指标、奖项、规模、引用等)+你的推理给出**明确结论**(如'属于该领域大牛'/'竞争力较强')+结论依据。具体事实用[N]标注；推理结论明确写出。"

## 6. Grounding/citation + hallucination guard (the safety boundary)

The boundary that lets knowledge mode run safely:
- **Grounded (cited [N])**: any specific entity + its attributes (name, institution, award, product, metric, paper). The existing `_validate_and_strip_citations` already enforces citation markers.
- **LLM-knowledge (marked)**: general/conceptual content (taxonomies, method descriptions, trends, definitions). Marked `（行业一般认知）` so the user sees it's not DB-sourced.
- **Forbidden always**: inventing a specific entity that isn't in evidence (e.g., a fake professor or a fake award for a real professor). The prompt states this explicitly; the eval's forbidden_entities + a hallucination spot-check guard it.

Risk acceptance: conceptual LLM knowledge can be slightly imprecise, but it's clearly labeled + far better than refusing. Entity facts stay grounded (the real hallucination risk is controlled).

## 7. Code touch points

- `chat.py::_detect_answer_intent` (NEW): keyword + query_type → intent.
- `chat.py::_build_chat_response`: compute intent; pass to synthesis; for knowledge intent, call `search_with_content` (replace/augment the web step).
- `chat.py::_call_gemma_synthesis`: accept `intent`, select the system prompt (3 prompts).
- `web_search.py::search_with_content` (NEW): search + fetch top-N article text (reuse the existing article-fetch helper from upload.py's lane).
- `eval_full_testset.py`: log per-case intent; add a knowledge-case + judgment-case sensitivity check.

## 8. Verification

- **Knowledge cases (qid18–23)**: should ANSWER (not refuse) → coverage + recall up from ~0. Acceptance: ≥3 of 6 produce a substantive answer (even if not matching every standard entity).
- **Retrieval cases (qid1/3/9/11/17/26)**: must NOT regress; answer depth stays/improves. The retrieval prompt is deepened, not loosened.
- **Hallucination guard**: forbidden_entities still 0 violations; spot-check that knowledge answers don't invent specific entities (only conceptual content uses LLM knowledge).
- **Metric refinement**: add a semantic-similarity (or LLM-judge) coverage metric alongside keyword-overlap — keyword-overlap undercounts (the system summarizes, doesn't reproduce the ~1000-char standard).

## 9. Phasing

- **Phase 1 (MVP)**: intent detection + 3 synthesis prompts (no web article-fetch yet). Measure knowledge-case lift + retrieval non-regression. Lowest risk, biggest conceptual unlock (the 6 refused cases).
- **Phase 2**: web article-content fetch for knowledge intent (ground the LLM knowledge in real articles; reduces imprecision).
- **Phase 3**: query reformulation for web + judgment-mode refinement + semantic-coverage metric.

## 10. What this does NOT do (out of scope)

- Ingest FM1a-absent entities into the DB (qid3/9/13 caps remain until ingested — web recovers some).
- Fix the patent domain (qid24 — separate infer-patent-type work).
- Multi-turn coref (qid18–23 are sent standalone; even knowledge-mode answers them turn-by-turn, which is fine for single-turn knowledge).
- Remove the entity-grounding rule for retrieval intent (kept — that's the hallucination control).
