# Verification Contract: contextual-query-interpretation

Created 2026-08-19 before production-code edits.

## Mode

- Interpreter is a pure module with injected LLM client — unit TDD applies.
- Wiring into `_answer_locked` is RAG/chat-level: GREEN additionally
  requires both-direction replay (ON and OFF) per the GO/NO-GO gate.

## RED definitions

### RED-1 (6.1): interpreter does not exist

- Import fails → module creation is the RED.

### RED-2 (6.1.2): validation checklist

- G1-T3 fixture: query "它有哪些布局和进展", session subject 国先中心,
  fake LLM returns subject_ref=国先中心 with confidence 0.8 → all checks
  pass → valid interpretation.
- Hallucination fixture: fake LLM returns subject_ref=张三 (not in session
  manifest) → check ① rejects → interpretation=None.
- Headline fixture: subject_ref=河套标题 → check ④ rejects.
- Enumeration fixture: query "深圳有哪些公司" → check ⑥ rejects.

### RED-3 (6.2): wiring consults interpretation

- Adapter-level fake with interpretation mocked → planning request carries
  the resolved subject. Without interpretation → unchanged Phase 3 path.

## GREEN gates

1. Unit suites green (interpreter + validation + wiring).
2. Replay OFF: 18/19 (baseline, G1-T3 known residual).
3. Replay ON: 19/19 (G1-T3 PASS — the target).
4. Latency: interpreter p95 <= 1.5s; e2e p95 degradation <= 1s.
5. Hallucination = 0 (all rejected interpretations traced).
