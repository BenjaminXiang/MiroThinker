# Proposal: contextual-query-interpretation

> Phase 6 of Epic `fix-round-1-serving-pipeline` (opened 2026-08-19,
> agent-governed per AGENTS.md §3; design inputs from recon
> `.agents/runs/contextual-query-interpretation/design-input-2026-08-19.md`).
> Human docs: round plan + log (same line).
> Behavior-affecting: YES — behind a default-OFF env switch until the
> GO/NO-GO gate passes. Capability: `canonical-v2-chat`.

## Why

G1-T3 is the last replay failure: "它有哪些布局和进展" — the deep follow-up
needs LLM understanding to resolve "它" to the session subject and constrain
the answer framing. Phase 3's deterministic layer handles surface patterns;
the contextual layer resolves deeper anaphora and intent.

## What Changes

1. **`canonical_v2_query_interpreter.py`** (admin backend): LLM call with
   1.5s hard timeout (executor + future.result), default OFF
   (`CHAT_CONTEXTUAL_INTERPRETATION` env), mirror of
   `_ServingQueryRewriter` isolation pattern (lazy client, bounded
   executor, exception-swallowing).
2. **Interpretation output** (Pydantic): subject_ref (name + source +
   canonical_id), intent (profile/deepen/switch/expand/enumerate/relation/
   clarify_ambiguous), self_contained_query, confidence, referent_kind.
3. **Deterministic validation** (7 checks from design inputs): subject must
   hit session manifests; explicit-named-subject veto; domain mismatch
   rejection; headline-shaped rejection; protected-slot preservation;
   enumeration never single-subject; confidence >= 0.7. Any check fails →
   interpretation = None (fall through to Phase 3 deterministic path).
4. **Wiring**: 4 decision points in `_answer_locked` — clarification gate,
   displayed-ids binding, soft-subject derivation, expansion rewrite —
   each consults the interpretation first (if valid), falls back to
   deterministic if None.
5. **Trace**: interpretation outcome + degradation tokens
   (interpretation-off / interpretation-timeout / interpretation-rejected).

## Impact

- `apps/admin-console/backend/services/canonical_v2_query_interpreter.py`
  (new)
- `apps/admin-console/backend/services/canonical_v2_chat.py` (wiring)
- `apps/admin-console/backend/services/canonical_v2_turn_trace.py` (tokens)
- Tests: interpreter unit (fakes), validation checklist, wiring.

## GO/NO-GO gate (frozen)

- Seven-session replay: ON → all PASS including G1-T3; OFF → all PASS (18/19
  baseline, G1-T3 known). Both directions green.
- Latency: e2e p95 degradation ≤ 1s; interpreter p95 ≤ 1.5s; timeout rate
  ≤ 5%.
- Hallucination binding = 0 (all rejections traced and counted).
- Gate fails → stays behind the OFF switch; round closes without it.
