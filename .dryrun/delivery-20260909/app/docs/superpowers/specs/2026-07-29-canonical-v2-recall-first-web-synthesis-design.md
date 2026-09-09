# Canonical V2 Recall-First Web Synthesis - Design

> Status: approved for S12D implementation.
> Parent change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`.
> Runtime target: isolated read-only Candidate `candidate-s12c-20260726-r8`.

## Problem

The reported three-turn hotel-robot conversation reaches both Bocha and Serper, and the providers
return directly relevant evidence. Serper returns a PUDU Product result that explicitly says a
robotic hand can press elevator buttons. The answer nevertheless says that the input contains no
such evidence.

The failure is inside the serving pipeline:

1. The deterministic reranker treats Web as important only for a small query-marker allowlist.
2. The read path applies one global `max_candidates` limit after local-first reranking.
3. The answer selector applies another shared claim limit and, outside the marker allowlist, can
   select only preferred local objects.
4. The final LLM can judge only the claims that survive those deterministic gates.

This is a recall failure disguised as an evidence-sufficiency answer. Adding `机械臂` or `按电梯` to
the marker list would fix one sentence but preserve the defect class for the next capability.

## First Principles

1. Retrieval creates candidates; it does not decide the answer.
2. A final semantic judge cannot recover evidence deleted before its input boundary.
3. Recall and trust are different concerns. Broad bounded recall happens first; material factual
   claims remain evidence-bound at output time.
4. Model memory may help interpret evidence but cannot be cited as evidence.
5. Latency is a product constraint. The repair must not add a planner, reranker, and sufficiency LLM
   chain before the existing prose call.
6. Public display is stricter than internal answer input. A useful search result may inform semantic
   selection while remaining ineligible for the public citation list.

## Invariants

- Every normal information request still invokes Bocha and Serper concurrently.
- Local and current-Web evidence remain distinguishable and content-addressed.
- Product capability is confirmed only by evidence directly naming the Product and capability.
- No online result mutates Canonical V2, Milvus, identity, or active release state.
- Deterministic fallback remains limited to typed LLM provider/output failure.
- Public output contains no `/browse`, private-network URL, internal locator, trace, or raw evidence.
- Refusal, clarification-only, safety, and interface-control behavior remains unchanged.

## Considered Approaches

### A. Add more Web-gap keywords

Extend `_WEB_GAP_MARKERS` with Product and capability terms.

Rejected. It encodes a growing vocabulary of known failures, misses paraphrases and future domains,
and keeps evidence availability dependent on query wording.

### B. Implement the full multi-stage LLM orchestration now

Add structured LLM planning, reranking, sufficiency, and targeted retry to the Candidate path.

Deferred. This matches the complete long-term architecture but adds several serial model calls,
schema/retry behavior, and latency at the exact point where the user asked for a fast correction.
The existing dual Web call already retrieves the needed evidence.

### C. Lane-balanced retention plus one final LLM synthesis

Retain bounded local and Web capacity after fusion, pass a bounded mixed claim set to the existing
final LLM, and strengthen the prompt's relevance and direct-binding rules.

Chosen. It fixes the earliest shared cause, uses the LLM where semantic judgment is valuable, keeps
one model call on the critical path, and leaves deterministic trust/privacy controls intact.

## Detailed Design

### 1. Lane-balanced late selection

The serving reranker classifies fused candidates as:

- mixed: contains strong local evidence and current-Web evidence;
- local: contains strong local evidence only;
- Web: contains current-Web evidence only;
- other: vector-only or otherwise weak candidates.

Mixed candidates remain first because they already aggregate complementary evidence. Remaining
local and Web candidates are interleaved by score, followed by other candidates. Therefore the
existing global candidate cap contains both lanes whenever both are available. No query keyword
changes this ordering.

This is deliberately serving-private. The generic `KnowledgeRead` limit and public contracts remain
unchanged.

### 2. Bounded mixed claim input

The answer selector always considers current-Web items for normal information answers. It retains:

- up to the existing local candidate budget for list/enumeration questions;
- a smaller local subset for focused questions;
- up to the existing Web result budget for both question types.

Evidence is round-robin selected across source nature so a long local projection block cannot use the
complete claim budget. Duplicate local lane evidence for one object remains collapsed, while a Web
item is not discarded merely because the same canonical entity has local evidence.

The total input is bounded by `max_candidates + max_web_results` (currently 13). The final renderer
receives the complete selected set rather than applying an unrelated hardcoded 12-claim truncation.

### 3. One final LLM judgment

Prompt version `canonical-v2-prose-v3` receives:

- the current user question;
- active and displayed entities;
- bounded claims with text, predicate, status, source nature, and current-Web locator;
- relationship paths.

The prompt instructs the model to:

- treat claims as candidate evidence and discard irrelevant search results;
- answer the question directly before background detail;
- integrate local and Web evidence instead of copying fields/snippets;
- require Product plus capability to appear in the same evidence for a confirmed capability;
- distinguish physical button pressing from elevator IoT integration and general Company ability;
- say which displayed candidates are supported and qualify the rest as unverified when appropriate;
- never expose internal metadata or add factual content absent from the evidence.

This remains one non-thinking Qwen call. There is no new retry loop or model stage.

### 4. Official public citations

Search evidence remains usable by the LLM regardless of whether it qualifies for public display.
The public adapter emits a current-Web link only when either:

- the evidence is explicitly marked `official`; or
- the Web hostname equals or is a subdomain of an official hostname extracted from admitted local
  evidence on the same canonical handle.

This supports official Product pages discovered through ordinary Web search without trusting every
search result. It adds no Company-specific domain registry. Third-party news, aggregator, internal,
private, credential-bearing, localhost, and non-global IP links remain hidden.

### 5. Failure behavior

- Both Web providers fail: use supported local evidence and expose the existing freshness limit.
- Web succeeds but is irrelevant: the LLM ignores it; local answer remains available.
- LLM fails or returns invalid/empty output: deterministic evidence-bound fallback remains.
- Direct Product binding is absent: report that the candidate is not verified for the requested
  feature; do not infer it from Company capability.

## Expected Request Path

```text
HTTP/session context
  -> local lanes + Bocha + Serper concurrently
  -> identity fusion
  -> lane-balanced deterministic retention
  -> bounded mixed claim construction
  -> one Qwen synthesis call
  -> official-only public citation mapping
  -> sanitized JSON/UI
```

No new serial network call is introduced. CPU work is linear in the already bounded candidate set.

## Verification Strategy

- Unit RED/GREEN for local-heavy reranking with capability wording absent from the old marker list.
- Answer-selector RED/GREEN proving both local and Product-capability Web evidence reach the injected
  renderer under the real 8-local/5-Web budget.
- Prompt contract test for question, source metadata, direct Product binding, and complete bounded
  claim input.
- Public citation tests for same-entity official-host validation and third-party rejection.
- Sibling matrix for geography, current fact, role, link, and Product-capability follow-ups.
- Real three-turn replay through `/api/chat`, retaining the session cookie.
- Record HTTP total time, Web trace success, `llm_synthesized`, public citations, and privacy fields.

## Rollback

Revert the serving/prompt/public-citation commit and restart the same read-only Candidate. No data,
index, serving-bundle, or release rollback is required.

## Remaining Risks

- Search snippets can be incomplete. The output remains qualified and directly evidence-bound.
- Lane balancing can displace a low-ranked local candidate. The candidate and claim budgets remain
  explicit, and mixed candidates are preferred.
- A canonical object without a retained official URL cannot use an ordinary Web result as a public
  citation unless the result is explicitly authoritative. The answer can still use the evidence,
  but `查看依据` stays fail-closed.
