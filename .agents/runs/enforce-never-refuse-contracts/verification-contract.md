# Verification Contract: enforce-never-refuse-contracts

Created 2026-08-18 before production-code edits.

## Mode

- Deterministic guards (fallback text, deflection rewrite, lane-failure
  rewrite) are pure functions over (answer_text, evidence signals) —
  unit-level TDD applies and is the RED surface.
- GREEN for replay-level requirements (V1/V2) additionally requires the
  fault-injection harness and the seven-session replay — a unit test alone is
  not sufficient (AGENTS.md §4).

## RED definitions

### RED-1: fallback is refusal-form (task 2.1.1)

- Current `_soft_fallback_answer_text("云迹科技")` returns "…暂未能确认您问
  的具体内容；可以换个角度继续提问。" — refusal family: no confirmed fact,
  no named gap. RED test asserts the contract form: first sentence contains
  云迹科技, contains a confirmed-fact or identity statement, contains a named
  coverage gap, contains no "换个角度"-only ending.

### RED-2: deflection ships unguarded (task 2.1.2)

- Feed the G4 verbatim form ("建议访问国家知识产权局查询…") through the
  response mapping with zero patent evidence → currently ships unchanged.
  RED asserts rewrite to gap-naming form with the anchor named and no
  external-database recommendation.

### RED-3: lane outage phrased as world claim (task 2.2.1)

- Simulate web-lane-unavailable evidence traces + answer text "未找到该
  机构的相关信息" → currently ships unchanged. RED asserts rewrite to
  网络检索暂不可用 wording.

### RED-4 (replay-level): fault injection over web-only subject (V1)

- Same harness as Phase 1 RED-4 (invalid BOCHA_API_KEY, both-provider
  outage variant optional): web-only subject turn answers carry
  网络检索暂不可用, never 未找到该机构; trace degradation token
  web-lane-unavailable.

## GREEN gates

1. New unit suites green (fallback form / deflection / lane-failure rewrites,
   subject-carrying).
2. V1 fault-injection replay evidence saved under
   `.agents/runs/enforce-never-refuse-contracts/`.
3. V2 full replay: no regression vs Phase 1 outcomes (stable lines
   unchanged; G2/G6 PASS).
4. acceptance.md evidence rows filled; Epic Phase 2 items ticked; human log
   + index updated.
