---
title: "M4: Chat routes use RetrievalService (B/D/E) + M5.1 Serper fallback"
type: feat
status: active
date: 2026-04-22
milestone: M4 + M5.1
origin:
  - docs/plans/2026-04-20-003-agentic-rag-execution-plan.md  # §M4, §M5.1
depends_on:
  - 3e49225  # M3 RetrievalService
  - 7534e11  # M0.1 RerankerClient
  - existing WebSearchProvider (providers/web_search.py)
---

# M4 — Chat routes use RetrievalService (+ M5.1 Serper fallback)

## Overview

Wire `RetrievalService` (M3) into the three chat routes that currently rely on SQL LIKE or rule-based fallbacks:
- **B-route** (semantic professor search): SQL LIKE → vector retrieve + rerank
- **D-route** (cross-domain): keep company SQL LIKE (company collection deferred) + add paper retrieve + professor retrieve; merge into single Evidence list for synthesis
- **E-route** (knowledge QA): paper retrieve first; low-confidence cascade to Serper Web Search (M5.1)

Plus two shared helpers:
- **Citation validator**: strip `[N]` markers in LLM output where `N > len(evidence)`
- **Low-confidence prefix**: prepend disclaimer when top-1 score < 0.3

Aims for the first chat response quality win from the Agentic RAG stack. Real demo-quality gains depend on M2.4 dogfood + M3 backfill populating the Milvus collection — those are operator actions, not this PR's scope.

## Problem Frame

Today's `chat.py` has a mature query classifier (A/B/D/E/F/G) but the retrieval path is impoverished:
- B-route: `SELECT ... FROM professor WHERE ... ILIKE '%topic%'` — misses professors whose expertise is described in the profile_summary but not literally named in research_directions.
- D-route: "找深圳做具身智能的教授和企业" returns whatever comes first from SQL LIKE on each domain, with no fusion signal.
- E-route: "大模型蒸馏原理" has no mechanism to retrieve paper abstracts; always falls through to general knowledge.

The infrastructure from M0.1 through M3 is ready: embedding + rerank clients, RetrievalService with concurrent ANN, paper_chunks collection, Postgres writers. M4 is the last mile — make chat use it.

## Requirements Trace

- **R1** (003 §M4.1): B-route SQL LIKE → `retrieval_service.retrieve(domains=("professor",), filters={"institution": inst}, final_top_k=5)`. Result count + rerank signal improve vs LIKE baseline.
- **R2** (003 §M4.2): D-route merges evidence from (prof retrieve) + (company SQL LIKE) + (paper retrieve). Keeps company SQL because company Milvus collection is not built yet (003 M3 narrowed to paper-first).
- **R3** (003 §M4.3): E-route retrieves from paper_chunks. If top-3 rerank score below 0.5 threshold, fall through to `WebSearchProvider.search(query)` → filter scholarly domains → treat top-3 organics as Evidence with `object_type="web"`.
- **R4** (003 §M4.4): Citation validator — regex match `\[(\d+)\]` in answer text, drop tokens with `N > len(evidence)`. Log dropped tokens.
- **R5** (003 §M4.4): Low-confidence prefix — if max evidence score < 0.3, prepend "根据检索结果置信度较低，以下仅供参考：" to `answer_text`.
- **R6** (derived): Singleton RetrievalService per FastAPI process — constructed at first `Depends()` hit with warm embed/rerank clients (HTTP conn pool) and shared Milvus client. Injected into B/D/E handlers.
- **R7** (derived): Feature flag `CHAT_USE_RETRIEVAL_SERVICE` env var (default `on`). `off` falls back to existing SQL LIKE paths. Matches 003 §9.4 rollback strategy.
- **R8** (derived): No frontend changes. Existing `/api/chat` endpoint signature unchanged.
- **R9** (derived): Never 500 on retrieval failure. Missing Milvus → log warning, fall back to SQL LIKE for B/D, to rule-based answer for E.
- **R10** (derived): `_build_evidence_blocks` (existing) must accept both legacy dict-evidence AND new `Evidence` dataclass. Thin adapter layer, not a rewrite of the synthesis code.

## Scope Boundaries

**In scope:**
- `apps/admin-console/backend/deps.py` — add `get_retrieval_service()` + helper factories for MilvusClient, EmbeddingClient, RerankerClient. Singleton lifecycle.
- `apps/admin-console/backend/api/chat.py` — surgical edits in `_lookup_professors_by_topic`, `_lookup_companies_by_topic` caller (D-route `_answer_cross_domain`), `_answer_knowledge_qa`. Shared helpers added to same file OR to `backend/chat/` subpackage if it grows.
- New helpers (shared across routes):
  - `_validate_and_strip_citations(answer_text: str, evidence_count: int) -> str`
  - `_maybe_prefix_low_confidence(answer_text: str, evidence: list[Evidence]) -> str`
  - `_evidence_list_from_retrieval(results: list[Evidence]) -> list[dict]` — adapter into existing `_build_evidence_blocks` shape
- Feature flag `CHAT_USE_RETRIEVAL_SERVICE` read in the three route functions.
- Unit tests: mock RetrievalService; verify flag routing + adapter shape + citation validator + low-confidence prefix.
- Integration tests: none in this PR (need real populated Milvus; deferred to operator dogfood).

**Out of scope:**
- Company Milvus collection. Company remains SQL LIKE in D-route.
- Web Search result rerank via Qwen3-Reranker-8B (that's M5.2).
- New chat endpoints or frontend contract changes.
- LLM-eval set for retrieval quality regression checking (separate effort).
- Caching of retrieval results at the chat layer (cache hook in RetrievalService exists; not wired here).
- Multi-turn context propagation of Evidence (session context stays purely entity-based).
- Citations with URLs clickable in frontend (frontend work).
- Retrieval-time user personalization.
- Language-specific prompt tuning.
- New pipeline_issue types or monitoring hooks for chat-side retrieval failures.

## Context & Research

### Relevant Code and Patterns

- **`apps/admin-console/backend/api/chat.py`** (1368 lines) — target of edits. Existing functions:
  - `_lookup_professors_by_topic(conn, *, institutions, topic, limit)` at line ~462 — current SQL LIKE implementation. Replace body, keep signature.
  - `_lookup_companies_by_topic(conn, *, topic)` at line ~148 — keep as-is (company out of M3 scope).
  - `_answer_cross_domain(topic, profs, companies)` at line ~176 — add paper evidence to its rendering.
  - `_answer_knowledge_qa(query)` at line ~213 — rewrite as a retrieve-then-synthesize path.
  - `_build_evidence_blocks` at line ~644 — adapter target.
  - `_build_chat_response` at line ~858 — final assembly. Good place for citation validator + low-confidence prefix insertion.
  - Existing evidence shape: `list[dict]` with keys like `type`, `id`, `title`, `snippet`, `url`. Map Evidence → this.
- **`apps/admin-console/backend/deps.py`** — 40 lines; `get_pg_conn()` pattern. Mirror for singletons. FastAPI `Depends()` + `@lru_cache` on factories.
- **`apps/miroflow-agent/src/data_agents/service/retrieval.py`** (M3, 3e49225) — the service to inject. Constructor takes `(pg_conn_factory, milvus_client, embedding_client, reranker, cache=None)`.
- **`apps/miroflow-agent/src/data_agents/professor/vectorizer.py::EmbeddingClient`** — factory pattern.
- **`apps/miroflow-agent/src/data_agents/providers/rerank.py::RerankerClient`** (M0.1) — factory pattern.
- **`apps/miroflow-agent/src/data_agents/providers/web_search.py::WebSearchProvider`** — already exists with Serper key env + `trust_env=False`. Instantiate in deps.py.
- **`apps/miroflow-agent/src/data_agents/paper/title_resolver.py::_search_web_by_title`** (M2.2) — reference for `_SCHOLARLY_DOMAINS` filter logic. Reuse the constant or extract to a shared module if needed; DO NOT modify title_resolver.py.

### Institutional Learnings

- **`docs/solutions/best-practices/httpx-module-patch-spec-mock-gotcha-2026-04-21.md`** — test-side real-class capture for any httpx.Client mocking.
- **`memory/feedback_codex_deviations.md`** — Shapes 1-3. Anti-drift brief essential.
- **`memory/feedback_proxy_llm.md`** — `trust_env=False` on all HTTP (Milvus gRPC has its own; embedding and reranker clients already handle it).
- **`docs/solutions/best-practices/discipline-aware-professor-quality-gate-2026-04-14.md`** — quality-first philosophy. Low-confidence prefix honors this.

### External References

- FastAPI `Depends()` caching semantics: `dependencies` are per-request. To get process-lifetime singletons, wrap factory in `@lru_cache()`. Standard pattern.
- No external API docs needed — all infrastructure is in-repo.

## Key Technical Decisions

- **Feature flag default `on`.** Rationale: M3 shipped the service with hermetic tests; M2.4 + V011 ship-ready. Flag is for rollback, not gradual rollout. `CHAT_USE_RETRIEVAL_SERVICE=off` reverts to SQL LIKE for B/D and rule-based for E. Document in the deps.py docstring.
- **Singleton lifecycle via `@lru_cache()` on deps factories.** One MilvusClient, one EmbeddingClient, one RerankerClient per FastAPI process. Warm HTTP conn pools. Matches M0.1 / M2.2 / M2.3 / M3 HTTP client ownership pattern.
- **`RetrievalService` is injected, not globally imported** — test patches `get_retrieval_service` on deps.py.
- **Evidence adapter, not rewrite.** `_evidence_list_from_retrieval(list[Evidence]) -> list[dict]` maps each Evidence to the existing legacy dict shape used by `_build_evidence_blocks` + `_build_chat_response`. Keeps the giant synthesis codepath unchanged. This is the M0.1 / M2.2 / M2.3 pattern applied at M4 scale: small surgical integration, leave the surrounding code alone.
- **D-route stays hybrid for now.** `_answer_cross_domain` calls both SQL LIKE (companies) and RetrievalService (professors, papers). Merge in-memory; all three feed the same `_build_evidence_blocks` codepath. When company Milvus collection ships, D-route swaps company SQL for RetrievalService with zero other chat.py changes — clean seam.
- **E-route fallback threshold 0.5.** If paper retrieve's rerank top-1 score < 0.5, call `WebSearchProvider.search(query)`, filter by scholarly domains, take top-3 organics, wrap as `Evidence(object_type="web", source_url=link, snippet=snippet)`. Evidence mix in synthesis.
- **Web Search fallback threshold is configurable via env.** `CHAT_E_WEB_FALLBACK_THRESHOLD` env var, default `"0.5"`. Keeps tuning out of code.
- **Scholarly domains list copied** (verbatim) from `paper/title_resolver.py::_SCHOLARLY_DOMAINS`. Duplicate to avoid touching title_resolver.py (Shape 3 drift). If we end up with 3+ copies, factor to a shared module in a follow-up.
- **No retry on retrieval failure.** Log + SQL LIKE fallback for B/D, log + rule-based for E. Match the "never raise on external flakiness" pattern from M2.x.
- **Citation validator is `[N]` regex, not semantic.** Gemma4 output will emit `[1]`, `[2]`, etc. Validator: for each match group `\[(\d+)\]`, if `int(N) > evidence_count`, remove the match from the text (not just blank the number). Log the dropped token. Do NOT try to remap; Gemma4 should be trained to match evidence indices.
- **Low-confidence prefix threshold 0.3.** Top-1 Evidence score (post-rerank) < 0.3 → prepend. Threshold is the rerank scale, not ANN distance — rerank scores are comparable across domains.
- **Test isolation**: all tests mock `RetrievalService`, `WebSearchProvider`, `EmbeddingClient`, `RerankerClient`, `MilvusClient`. No live network. No Milvus-Lite (overkill for chat tests).
- **`test_chat.py` grows but stays one file.** Existing chat tests live there; new tests pile on. If it exceeds 2000 lines, split in a follow-up.

## Open Questions

### Resolved During Planning

- **Q: Replace `_lookup_professors_by_topic` body OR introduce a new function?** → Replace the body. Callers unchanged. Same signature.
- **Q: Is the feature flag on or off by default?** → On. Explicit opt-out if production issues appear.
- **Q: Is web search always attempted in E-route, or only on low confidence?** → Only on low confidence (< 0.5 top-1 score). Saves Serper quota.
- **Q: If retrieve returns 0 Evidence for E-route, do we still try Serper?** → Yes. Empty local result → low confidence by definition.
- **Q: Do we wire RetrievalCache now?** → No. Protocol exists; M4 defers concrete implementation. Retrieval latency (~1s) is acceptable without caching for v1.
- **Q: D-route merge ordering?** → Professor results first, paper results second, company results third. Gemma4 synthesis sees them in that order; it picks what's relevant.
- **Q: Final_top_k values per route?** → B: 10 professors. D: 5 each domain (15 total). E: 3 papers + up to 3 web.
- **Q: filters={"institution": ...} for B-route when user queries multiple institutions?** → Apply filter only when classifier resolved a single institution. If query spans "深圳" (generic), no institution filter.

### Deferred to Implementation

- **Exact signature of `_evidence_list_from_retrieval` adapter.** Inspect `_build_evidence_blocks` expected keys at implementation time, emit matching dicts.
- **Whether to deduplicate Evidence across domains** in D-route (same professor appearing in both professor collection and as author of a retrieved paper). Probably yes, keyed by (object_type, object_id). Pin at GREEN.
- **What to do when Web Search itself errors (Serper 429/down).** Likely just skip web results, log warning. Matches M2.2 cascade-fall-through philosophy.
- **Session context Evidence replay.** Currently chat session stack tracks entities, not retrieval results. Not needed for v1; may become useful for multi-turn follow-up ("tell me more about the third paper").

## High-Level Technical Design

> *Directional guidance, not implementation specification.*

```
                         POST /api/chat
                               │
                               ▼
                  classify query (A/B/D/E/F/G)
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
     B-route                D-route                E-route
        │                      │                      │
   retrieve(                retrieve(              retrieve(
     "professor",             "professor",            "paper",
     filters={inst}           "paper",              candidate_limit=30,
     top_k=5)                 top_k=5 each)          top_k=10)
        │                      │                      │
        │                  SQL LIKE                   │
        │                  companies                  │
        │                      │                      │
        │                   merge                     │ if top-1 score < 0.5
        │                      │                      │
        │                      │               Web Search (Serper)
        │                      │                      │
        │                      │               filter scholarly
        │                      │                      │
        │                      │               merge with local results
        │                      │                      │
        └───────────┬──────────┴──────────┬───────────┘
                    ▼                      ▼
           _evidence_list_from_retrieval (adapter)
                    ▼
           _build_evidence_blocks (existing)
                    ▼
           _call_gemma_synthesis (existing)
                    ▼
     _validate_and_strip_citations + _maybe_prefix_low_confidence
                    ▼
                ChatResponse
```

Feature flag `CHAT_USE_RETRIEVAL_SERVICE=off` short-circuits before the `retrieve()` call and uses existing SQL LIKE paths.

## Implementation Units

- [ ] **Unit 1: deps.py singletons + feature flag**

**Goal:** Wire up `get_retrieval_service()` + dependency factories. Read `CHAT_USE_RETRIEVAL_SERVICE` env.

**Requirements:** R6, R7

**Dependencies:** None.

**Files:**
- Modify: `apps/admin-console/backend/deps.py`
- Test: `apps/admin-console/backend/tests/test_deps.py` (new OR extend existing)

**Approach:**
- Add `_get_milvus_client()`, `_get_embedding_client()`, `_get_reranker_client()`, `_get_web_search_provider()` each wrapped in `functools.lru_cache(maxsize=1)` for process-lifetime singleton.
- `get_retrieval_service()` composes them.
- `chat_use_retrieval_service()` reads env var, returns bool. Called by chat route handlers to decide flag-on or flag-off path.
- `chat_e_web_fallback_threshold()` reads `CHAT_E_WEB_FALLBACK_THRESHOLD`, defaults to `0.5`.
- Milvus URI env: `MILVUS_URI` default `./milvus.db`.

**Execution note:** Test-first. Mock env vars via monkeypatch.

**Test scenarios:**
- Happy — `get_retrieval_service()` returns same instance across two calls (singleton via lru_cache).
- Happy — `chat_use_retrieval_service()` returns `True` when env unset (default on).
- Edge — env `CHAT_USE_RETRIEVAL_SERVICE=off` → returns `False`.
- Edge — env `CHAT_USE_RETRIEVAL_SERVICE=0` → returns `False`.
- Edge — env `CHAT_USE_RETRIEVAL_SERVICE=true` → returns `True`.
- Happy — `chat_e_web_fallback_threshold()` returns 0.5 default.
- Happy — `CHAT_E_WEB_FALLBACK_THRESHOLD=0.3` → returns 0.3.
- Edge — malformed threshold string → falls back to default, logs warning.

**Verification:**
- Tests pass. Lint clean. Import path resolves: `from backend.deps import get_retrieval_service`.

---

- [ ] **Unit 2: Evidence adapter + citation validator + low-confidence prefix**

**Goal:** Shared helpers used by all three routes.

**Requirements:** R4, R5, R10

**Dependencies:** None.

**Files:**
- Modify: `apps/admin-console/backend/api/chat.py` — add helpers near the existing `_build_evidence_blocks`.
- Test: `apps/admin-console/backend/tests/test_chat_retrieval_helpers.py` (new)

**Approach:**
- `_evidence_list_from_retrieval(results: list[Evidence]) -> list[dict]` — maps each Evidence to a dict matching what `_build_evidence_blocks` expects. Fields: `type`, `id`, `title`, `snippet`, `url`, optional `score`. Professor Evidence → `type="professor"`, `title=metadata["name"]`, `url=metadata.get("homepage_url")`. Paper Evidence → `type="paper"`, `title=metadata["paper_id"]` (temporary; real title join deferred), `snippet=content_text`, `url=source_url`.
- `_validate_and_strip_citations(answer_text: str, evidence_count: int) -> str` — regex `r"\[(\d+)\]"`, for each match if `int(N) > evidence_count` remove the match (including brackets). Log each dropped citation. Return cleaned text.
- `_maybe_prefix_low_confidence(answer_text: str, evidence: list[Evidence], threshold: float = 0.3) -> str` — if `evidence and max(e.score for e in evidence) < threshold`, prepend the Chinese disclaimer. Else return unchanged.

**Execution note:** Test-first.

**Test scenarios:**

*Evidence adapter:*
- Happy — single professor Evidence → dict with `type="professor"`, correct title/id/url.
- Happy — single paper Evidence → dict with `type="paper"`, snippet = chunk content_text.
- Happy — mixed list: 2 prof + 3 paper → 5 dicts, correct order preserved.
- Edge — empty list → empty list.
- Edge — Evidence with `metadata=None` → adapter handles (uses empty dict).

*Citation validator:*
- Happy — `"Prof Doe [1] is at 南科大 [2]"` with 2 evidence → unchanged.
- Happy — `"Prof Doe [1] and [99] are experts"` with 2 evidence → `"Prof Doe [1] and  are experts"` (or similar; pin behavior to strip out-of-range brackets; preserve surrounding text).
- Edge — no citations → unchanged.
- Edge — 0 evidence + answer with `[1]` → `[1]` stripped.
- Edge — `[1,2]` multi-citation → depends on policy. For v1 treat as two separate checks via regex iteration; pin behavior.
- Edge — answer with `[0]` → always dropped (0 is never valid; citations are 1-indexed).
- Contract — dropped citation logged via `logging.getLogger`.

*Low-confidence prefix:*
- Happy — max evidence score 0.9 → no prefix.
- Happy — max score 0.2 → prefix prepended.
- Happy — max score exactly 0.3 (threshold) → no prefix (strict `<`).
- Edge — empty evidence → no prefix (nothing to be unconfident about).
- Edge — all scores negative (shouldn't happen but defensive) → prefix prepended.

**Verification:**
- All helper tests pass.
- Logs show dropped citations where expected.

---

- [ ] **Unit 3: B-route retrieval path + flag gate**

**Goal:** Replace `_lookup_professors_by_topic` body with RetrievalService call, gated by feature flag.

**Requirements:** R1, R7, R9

**Dependencies:** Units 1, 2.

**Files:**
- Modify: `apps/admin-console/backend/api/chat.py::_lookup_professors_by_topic`
- Test: `apps/admin-console/backend/tests/test_chat_b_route.py` (new)

**Approach:**
- Same signature: `_lookup_professors_by_topic(conn, *, institutions, topic, limit)`.
- New body:
  1. If `chat_use_retrieval_service()` returns False → fall back to existing SQL LIKE logic (preserve current behavior as a helper `_lookup_professors_by_topic_sql`).
  2. Else: resolve `RetrievalService = get_retrieval_service()`; build filters dict (institution when a single institution resolved); call `retrieve(query=topic, domains=("professor",), filters=filters, final_top_k=limit)`.
  3. Adapt via `_evidence_list_from_retrieval`; return dict list matching legacy shape.
  4. On any exception inside retrieve: log warning, fall back to SQL LIKE.
- `limit` from caller: use as `final_top_k`. `candidate_limit` hardcoded 30.

**Execution note:** Test-first. Mock `get_retrieval_service` via `monkeypatch.setattr`.

**Test scenarios:**
- Happy — flag on, retrieve returns 3 Evidence → returns 3 dicts with `type="professor"`.
- Happy — flag off → SQL LIKE path invoked (spy on `conn.execute`).
- Happy — institution resolved → retrieve called with `filters={"institution": "南方科技大学"}`.
- Happy — multiple institutions → retrieve called without institution filter (generic 深圳 query).
- Edge — retrieve returns empty → returns empty list.
- Edge — retrieve raises → falls back to SQL LIKE.
- Edge — flag on but retrieve 5xx → falls back to SQL LIKE, logs warning.

**Verification:**
- All B-route tests pass.
- Existing B-route integration tests (if any) still pass.

---

- [ ] **Unit 4: D-route cross-domain evidence merge**

**Goal:** Augment `_answer_cross_domain` / its upstream fetcher to include professor + paper Evidence from RetrievalService alongside existing company SQL LIKE.

**Requirements:** R2, R7, R9, R10

**Dependencies:** Units 1, 2, 3.

**Files:**
- Modify: `apps/admin-console/backend/api/chat.py` — touch the D-route dispatch (where `_lookup_companies_by_topic` is called) to also call RetrievalService for professor + paper domains; merge results into a single Evidence list; pass that to the Gemma synthesis step.
- Test: `apps/admin-console/backend/tests/test_chat_d_route.py` (new)

**Approach:**
- Identify the existing D-route dispatch site (where the chat classifier lands on `"D"`).
- Flag-gated: if `chat_use_retrieval_service()` is True:
  1. `retrieve(domains=("professor", "paper"), final_top_k=5)` — note top_k is per-merged, not per-domain; RetrievalService already merges and reranks.
  2. Existing `_lookup_companies_by_topic` for company SQL LIKE.
  3. Adapt Evidence list + append legacy company dicts.
  4. Deduplicate by `(type, id)` — first occurrence wins.
- Flag off: current behavior unchanged.
- `_answer_cross_domain` text template already handles mixed evidence; no change needed there.

**Execution note:** Test-first.

**Test scenarios:**
- Happy — flag on + retrieve returns 3 prof + 2 paper + SQL returns 2 companies → synthesis sees 7 evidence items.
- Happy — flag on + retrieve fails mid-call → synthesis sees only company results (graceful degradation).
- Happy — flag off → only company SQL path (existing behavior).
- Edge — duplicate professor across retrieve and some future fallback → deduped.
- Edge — all three sources empty → synthesis invoked with empty evidence; answer template handles "未找到相关结果".

**Verification:**
- D-route tests pass.

---

- [ ] **Unit 5: E-route paper retrieve + Serper fallback**

**Goal:** Knowledge QA route uses paper_chunks retrieval; on low-confidence, cascade to Serper Web Search.

**Requirements:** R3, R7, R9

**Dependencies:** Units 1, 2.

**Files:**
- Modify: `apps/admin-console/backend/api/chat.py::_answer_knowledge_qa`
- Test: `apps/admin-console/backend/tests/test_chat_e_route.py` (new)

**Approach:**
- Flag gate. If off → current rule-based / FAQ behavior unchanged.
- If on:
  1. `retrieve(domains=("paper",), final_top_k=10)`.
  2. Check rerank top-1 score: if `< threshold` (default 0.5) OR empty → trigger Serper fallback.
  3. Fallback: `WebSearchProvider.search(query)` → filter organic entries by `_SCHOLARLY_DOMAINS`. Take up to 3 top-matching entries. Wrap each as `Evidence(object_type="web", object_id=<link>, score=0.0, snippet=organic["snippet"][:500], source_url=organic["link"], metadata={"title": organic["title"]})`. Merge with any local retrieve results.
  4. Pass merged Evidence list to Gemma synthesis via the adapter.
- If both local retrieve AND Serper return empty → current rule-based answer as final fallback.
- `_SCHOLARLY_DOMAINS` list is duplicated from title_resolver (do NOT import or modify that file).

**Execution note:** Test-first.

**Test scenarios:**
- Happy — retrieve top-1 score 0.8 → no Serper; answer synthesized from paper chunks.
- Happy — retrieve top-1 score 0.3 (below threshold) → Serper invoked, organic hits merged.
- Happy — retrieve empty → Serper invoked.
- Happy — Serper organic list → scholarly domain filter keeps arxiv.org, drops github.com.
- Edge — Serper returns HTTP 429 → log warning, use local results if any else empty Evidence list.
- Edge — Both local empty + Serper empty → rule-based fallback invoked (legacy path).
- Edge — flag off → rule-based FAQ only (existing behavior).
- Edge — custom `CHAT_E_WEB_FALLBACK_THRESHOLD=0.3` env → threshold applied at that value.

**Verification:**
- E-route tests pass.
- No Serper call when confident retrieve (spy on `WebSearchProvider.search`).

---

- [ ] **Unit 6: Wire citation validator + low-confidence prefix into chat response**

**Goal:** Apply Unit 2 helpers to the final `ChatResponse.answer_text`.

**Requirements:** R4, R5

**Dependencies:** Units 2, 3, 4, 5.

**Files:**
- Modify: `apps/admin-console/backend/api/chat.py::_build_chat_response` (or wherever the final answer assembly happens).
- Test: extend `apps/admin-console/backend/tests/test_chat_retrieval_helpers.py` with integration cases through `_build_chat_response`.

**Approach:**
- After Gemma synthesis returns `answer_text`, run `_validate_and_strip_citations(answer_text, len(evidence))`.
- Then run `_maybe_prefix_low_confidence(cleaned_text, evidence)`.
- Return `ChatResponse(answer_text=prefixed_text, citations=[...])`.
- Do NOT apply to FAQ / refuse / rule-based paths — those don't have evidence indices.

**Test scenarios:**
- Happy — answer with valid citations → passes through unchanged.
- Happy — answer with `[99]` and 3 evidence → `[99]` stripped.
- Happy — top evidence score 0.2 → prefixed with disclaimer.
- Edge — refuse path (query_type="F") → no citation or prefix logic applied.
- Edge — rule-based FAQ (query_type="E" but retrieve path skipped) → no validator.

**Verification:**
- All chain-level tests pass.
- Lint clean. No existing tests break.

## System-Wide Impact

- **Interaction graph:** New call path: chat route → `get_retrieval_service()` → RetrievalService → EmbeddingClient + MilvusClient + RerankerClient. Plus E-route → WebSearchProvider. No changes to synthesis pipeline or frontend.
- **Error propagation:** All retrieve calls wrapped in try/except; failure falls back to SQL LIKE or rule-based answer. Chat never 500s on retrieval errors.
- **State lifecycle risks:** `lru_cache`-backed singletons live for the process. In tests, `lru_cache` must be cleared between test cases OR factories monkey-patched before first use. Document this in the deps test fixture.
- **API surface parity:** `/api/chat` request/response schema unchanged. Clients see improved quality (hopefully), not new fields.
- **Integration coverage:** Unit tests mock everything. Real end-to-end waits for operator dogfood post-M2.4 + M3 backfill. Document in deps.py that flag-on without backfilled Milvus will result in empty retrieves → SQL fallback → same as flag-off (safe degradation).
- **Unchanged invariants:** `chat.py` session context, classifier, A/F/G routes, `_build_evidence_blocks`, `_call_gemma_synthesis` are all UNCHANGED. `vectorizer.py`, `rerank.py`, `web_search.py`, `title_resolver.py`, `retrieval.py` are all UNMODIFIED. Verified via `git diff --stat`.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| RetrievalService constructor takes wrong args | Deps unit test asserts singleton instantiates without error. |
| Milvus empty (no backfill run) → retrieve always empty → every B-route call silently degrades | `chat_use_retrieval_service()` can be flipped off via env. Operator dogfood runs M3 backfill before demoing M4 to end users. |
| Serper quota exhaustion from E-route traffic | Threshold 0.5 + scholarly filter limit invocations. `CHAT_E_WEB_FALLBACK_THRESHOLD` env raises bar when needed. |
| Citation validator over-strips (drops valid `[1]` because of parse bug) | Unit tests cover happy path, out-of-range, and multi-citation cases. |
| Shared `_SCHOLARLY_DOMAINS` duplication drifts from title_resolver version | Accepted Shape-3 tradeoff. If a third caller appears, factor to `data_agents/paper/scholarly_domains.py` in a follow-up. |
| Feature flag accidentally defaults off in production | Default is on. Operator must explicitly `CHAT_USE_RETRIEVAL_SERVICE=off` to revert. |
| Codex rewrites chat.py beyond the 3 functions | Anti-drift brief explicit: modify only `_lookup_professors_by_topic`, `_answer_cross_domain` dispatch, `_answer_knowledge_qa`, `_build_chat_response`; ADD new helpers. NO other functions touched. `git diff --stat` cross-validates. |
| Codex imports from or modifies `title_resolver.py` for `_SCHOLARLY_DOMAINS` | Brief explicitly forbids. Copy the constant into chat.py or a new small module. |
| Tests patch `RetrievalService` poorly (e.g., class-level attribute pollution) | Tests use `monkeypatch.setattr(deps_module, "get_retrieval_service", lambda: mock)`. Per-test isolation via pytest fixture. |
| `lru_cache` persists across tests, leaking state | Test fixture explicitly calls `_get_*_client.cache_clear()` in teardown. |
| E-route Serper enabled in CI → network call | WebSearchProvider factory in deps.py reads env `SERPER_API_KEY`. If unset → provider disabled; E-route falls through to rule-based. |
| D-route dedupe key collision between types | Key tuple is `(type, id)`; types are distinct (professor/paper/company), collisions impossible at this level. |

## Documentation / Operational Notes

- Update `CLAUDE.md` § "Tech Stack" with a note: "Chat retrieval layer uses `RetrievalService` (M3); controlled by `CHAT_USE_RETRIEVAL_SERVICE` env, default on."
- Follow-up doc: `docs/solutions/integration-issues/m4-chat-retrieval-rollout-observations-YYYY-MM-DD.md` — populate after first real user-facing run.
- New env vars: `CHAT_USE_RETRIEVAL_SERVICE` (default on), `CHAT_E_WEB_FALLBACK_THRESHOLD` (default 0.5), `MILVUS_URI` (default ./milvus.db). Document in deps.py module docstring.
- Rollback: set `CHAT_USE_RETRIEVAL_SERVICE=off`. Instant revert to pre-M4 SQL LIKE paths.

## Sources & References

- **Origin:** `docs/plans/2026-04-20-003-agentic-rag-execution-plan.md` §M4 + §M5.1
- **Upstream:**
  - M3: `docs/plans/2026-04-22-001-m3-retrieval-service-paper-first.md` (3e49225)
  - M2.4: `docs/plans/2026-04-21-004-m2.4-homepage-paper-ingest-orchestrator.md` (4ff72c2)
  - M0.1: `docs/plans/2026-04-20-004-m0.1-reranker-client.md` (7534e11)
- **Patterns:**
  - `apps/admin-console/backend/api/chat.py` — existing route handlers, evidence blocks, synthesis
  - `apps/admin-console/backend/deps.py` — dependency factory pattern
  - `apps/miroflow-agent/src/data_agents/service/retrieval.py` — service contract
  - `apps/miroflow-agent/src/data_agents/providers/web_search.py` — Serper wrapper
- **Learnings:**
  - `docs/solutions/best-practices/httpx-module-patch-spec-mock-gotcha-2026-04-21.md`
  - `memory/feedback_codex_deviations.md` (Shapes 1-3, Shape 3 anti-drift essential here)
  - `memory/feedback_proxy_llm.md`
