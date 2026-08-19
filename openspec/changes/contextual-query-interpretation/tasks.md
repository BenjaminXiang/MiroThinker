# Tasks: contextual-query-interpretation

## 6.1 Interpreter module

- [ ] 6.1.1 `canonical_v2_query_interpreter.py`: Interpretation Pydantic
       model, executor+timeout wrapper, env switch (default off), lazy LLM
       client via CHAT_LLM_PROFILE, exception-swallowing (None on any
       failure).
- [ ] 6.1.2 Deterministic validation checklist (7 checks); unit tests with
       G1-T3 fixture and hallucination fixture.

## 6.2 Wiring

- [ ] 6.2.1 Four decision points in `_answer_locked`: clarification gate,
       displayed-ids binding, soft-subject, expansion rewrite — each
       consults interpretation first, falls back to deterministic.
- [ ] 6.2.2 Trace: degradation tokens + interpretation record.
- [ ] 6.2.3 Unit tests: wiring with fakes (on/off/timeout/rejected paths).

## 6.3 Gate

- [ ] 6.3.1 Replay with switch ON: G1-T3 PASS; all other sessions PASS.
- [ ] 6.3.2 Replay with switch OFF: 18/19 baseline held.
- [ ] 6.3.3 Latency + hallucination audit from trace.
- [ ] 6.3.4 GO/NO-GO decision recorded; if GO → R3 prep.
